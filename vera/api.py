"""HTTP boundary. Public judge surface + optional token-protected replay studio."""
import asyncio
from contextlib import asynccontextmanager
import contextlib
import secrets
import sqlite3
import time
from pathlib import Path
from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from .config import Settings
from .models import ContextPush, Tick, Reply, Preview
from .composer import plan
from .policy import eligible, known_shapes
from .service import Service, Fault
from .store import Store


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                response = JSONResponse({"reason": "payload_too_large"}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(body)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    started = time.monotonic()
    store = Store(settings)
    service = Service(store, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def cleanup():
            while True:
                await asyncio.sleep(60)
                # Health's expiry check is read-only unless inactivity is exceeded.
                await asyncio.to_thread(service.health)
        task = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            store.close()

    app = FastAPI(title="Vera Compass", version="1.0.0", lifespan=lifespan, docs_url="/docs", redoc_url=None)
    app.state.service, app.state.store, app.state.settings = service, store, settings
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        start = time.perf_counter()
        protected = request.url.path.startswith("/v1/") and request.url.path not in {"/v1/healthz", "/v1/metadata"}
        if protected and settings.api_token and not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + settings.api_token):
            return JSONResponse({"reason": "unauthorized"}, status_code=401)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        if request.url.path == "/docs":
            # FastAPI's Swagger renderer uses inline initialization + its documented CDN.
            # Studio keeps the stricter, local-assets-only policy above.
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; frame-ancestors 'none'"
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - start) * 1000:.2f}"
        return response

    @app.exception_handler(Fault)
    async def fault_handler(request: Request, error: Fault):
        return JSONResponse(error.body, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, error: RequestValidationError):
        fields = [".".join(str(x) for x in e["loc"]) for e in error.errors()][:10]
        reason = "invalid_scope" if "body.scope" in fields else "malformed_request"
        return JSONResponse({"accepted": False, "reason": reason, "fields": fields}, status_code=400)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request: Request, error: sqlite3.OperationalError):
        # Do not expose paths, payloads or SQL. Fail closed; client can retry.
        return JSONResponse({"reason": "storage_temporarily_unavailable"}, status_code=503, headers={"Retry-After": "1"})

    @app.post("/v1/context")
    def push(req: ContextPush):
        return service.push(req)

    @app.post("/v1/tick")
    def tick(req: Tick, request: Request):
        key = request.headers.get("idempotency-key")
        if key and len(key) > 256:
            raise Fault(400, "invalid_idempotency_key")
        return service.tick(req, key)

    @app.post("/v1/reply")
    def reply(req: Reply):
        return service.reply(req)

    @app.get("/v1/healthz")
    def health():
        return {**service.health(), "uptime_seconds": int(time.monotonic() - started)}

    @app.get("/v1/metadata")
    def metadata():
        return service.metadata()

    @app.post("/v1/teardown")
    def teardown():
        store.wipe()
        return {"wiped": True}

    def admin(request: Request):
        if not settings.admin_token:
            raise Fault(404, "not_found")
        if not secrets.compare_digest(request.headers.get("authorization", ""), "Bearer " + settings.admin_token):
            raise Fault(401, "unauthorized")

    @app.get("/debug/traces", dependencies=[Depends(admin)])
    def traces(limit: int = 50):
        if not 1 <= limit <= 200:
            raise Fault(400, "invalid_limit")
        with store.lock:
            return {"traces": [v for _, v in store.items("traces")[-limit:]]}

    @app.post("/debug/preview", dependencies=[Depends(admin)])
    def preview(req: Preview):
        # Isolated what-if preview: never stores contexts or changes actual opt-outs.
        for scope, obj, field in (("category", req.category, "slug"), ("merchant", req.merchant, "merchant_id"), ("trigger", req.trigger, "id"), ("customer", req.customer, "customer_id")):
            if obj is not None:
                reason = known_shapes(scope, obj, str(obj.get(field, "")))
                if reason:
                    raise Fault(400, reason)
        reason = eligible(req.category, req.merchant, req.trigger, req.customer, req.now)
        composition = plan(req.category, req.merchant, req.trigger, req.customer, req.now) if not reason else None
        choice = composition.chosen if composition else None
        return {"mode": "isolated_preview_not_a_send", "decision": "send" if choice else "skip",
                "reason": reason or (choice.rationale if choice else composition.reason),
                "body": choice.body if choice else None, "cta": choice.cta if choice else None,
                "pending_action": choice.pending if choice else None,
                "trace": composition.trace() if composition else None,
                "note": "Preview checks supplied contexts only. Real tick also checks durable STOP, deduplication, cooldown and capacity."}

    @app.get("/debug/state", dependencies=[Depends(admin)])
    def state():
        with store.lock:
            return {"counts": {t: store.size(t) for t in ("contexts", "conversations", "recipients", "suppression", "traces")},
                    "llm_calls": store.get("meta", "llm_calls", 0)}

    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(web_dir)), name="assets")

        @app.get("/studio", include_in_schema=False)
        def studio():
            if not settings.admin_token and not settings.public_studio:
                raise Fault(404, "not_found")
            return FileResponse(web_dir / "index.html")

    @app.get("/", include_in_schema=False)
    def index():
        return {"service": "Vera Compass", "health": "/v1/healthz", "documentation": "/docs", "studio": "/studio" if settings.admin_token or settings.public_studio else None}
    return app
