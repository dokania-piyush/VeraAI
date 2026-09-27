# Deployment and submission operations

No cloud service has been created by this package. No billing, repository push or application submission has been performed.

## Recommended shape

One always-on web process, a writable local SQLite path, a public HTTPS endpoint, no automatic redeploy during the judging run, and a host retention/backups policy you can explain. The default compiler needs no external API key. This is a small single-instance challenge service, not a multi-tenant customer-messaging platform.

## Managed Python web service (Render example)

1. Create a GitHub repository you control. Copy this codebase into it, excluding `.env`, runtime databases and newly generated sensitive reports. Review the staged diff before pushing. The vendor files are provided for this challenge, not relicensed for unrelated publication.
2. In Render, create a **Web Service**, not a Static Site. Connect that repository and select Python.
3. Set build command `pip install -r requirements.txt -c requirements-lock.txt` and start command `python -m scripts.run --host 0.0.0.0`. The script reads the provider's `PORT`; do not hardcode 8080 in the provider setting.
4. Set health-check path `/v1/healthz`, Python 3.13.5, and exactly one instance. The included `render.yaml` is an optional paid-service recipe; inspect billing before using it.
5. Add your real identity metadata and private `VERA_ADMIN_TOKEN` in the dashboard. Leave `VERA_SEMANTIC_ENABLED=false` initially. Do not expose admin credentials in the README. Configure the public judge token only if agreed with organizers.
6. Choose storage deliberately using the section below. Deploy, inspect logs, verify HTTPS and run the read-only submission preflight.
7. Test on staging, then clear only your own synthetic test state before the judging window. Do not deploy or run reset/load scripts during evaluation.

Official setup reference: https://render.com/docs/deploy-fastapi

## Why not a sleeping free instance?

Render's documented free service spins down after idle time and needs startup time to resume; its local files are lost on restarts/spindown. This can break both the challenge's response deadline and conversation continuity. Use free hosting only for an exploratory preview, not as proof of judging readiness. Check your provider's current behavior and billing before deciding.

Source: https://render.com/docs/free (checked 27 September 2026).

## Persistence and data retention are separate questions

By default Render's filesystem is ephemeral. A persistent disk preserves the SQLite file across app restarts, but Render documents automatic daily disk snapshots retained for at least seven days. Application teardown cannot delete those snapshots. Adding a disk also changes deployment availability behavior and prevents multi-instance scaling.

Therefore the provided recipe **does not silently attach a persistent disk**. It is a working stateless-host deployment recipe with the explicit limitation that restarts lose state. Before final judging, choose one of these operational configurations:

- A single container/VM host with local persistent storage and backups disabled or governed by an acceptable, documented retention policy. This gives restart persistence without silently opting into provider snapshots.
- A paid managed service with an attached disk only after the organizer and host retention requirements are resolved. On Render, mount `/var/data` and set `VERA_DB_PATH=/var/data/vera.sqlite3`. Do not claim teardown removes the provider's retained snapshots.

An ephemeral-only deployment can be a smoke test, but it is not restart-resilient. The code has restart tests; those do not make an ephemeral hosting plan persistent. Do not change to an external database by environment variable alone: this application implements SQLite, not a PostgreSQL adapter.

Source: https://render.com/docs/disks

## Docker / Compose

Docker was unavailable in the authoring environment, so these recipes still require a real image build and host smoke test.

From the source folder, after creating `.env`:

```bash
docker compose up --build -d
docker compose logs --tail=100 vera
python -m scripts.preflight
```

Compose binds to loopback for local safety and stores SQLite in a named volume. For public hosting, place a correctly configured HTTPS reverse proxy in front of it; do not expose a bare development port to real customer traffic. The container runs as a non-root user. Host bind mounts must be writable by UID/GID 10001. Do not mount a network/shared filesystem for this single-instance design.

The image copies only runtime modules and local studio assets, not seeds or reports. It uses the provider's `PORT`. It does not include certificates for a custom public domain; your host/proxy supplies TLS. Validate the health check and graceful shutdown on the actual host.

## Monitoring without collecting extra data

Use status codes, health checks, uptime and latency. Access logging is disabled in the supplied runner; application errors do not echo request bodies. Do not turn on full request-body tracing in your hosting platform. Debug records contain supplied facts, so guard `/debug/*` with the admin token and clear them with the rest of test state.

Idle cleanup is four hours by default, with a minute maintenance cadence. It is based on last activity, not per-row age. Explicit teardown is immediate local deletion. Review hosting backups, filesystem snapshots, telemetry and optional LLM provider retention separately.

## Final read-only check

```bash
python -m scripts.preflight --url https://YOUR-REAL-HOST --submission
```

The placeholder URL must be replaced. Review the printed identity, not just the exit code. The command checks health, metadata and HTTPS; it does not test all writes or certify private-judge quality. Submit the base URL to the challenge page, not a subpath. Keep it live until the organizer is finished.
