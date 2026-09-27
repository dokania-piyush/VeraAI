"""Atomic application workflows. Side effects are only local SQLite writes."""
from datetime import timedelta
from typing import Any
from . import __version__
from .config import Settings
from .models import ContextPush, Tick, Reply, Action, ReplyResult
from .store import Store, context_key, recipient_key, canonical
from .evidence import Book, digest, suspicious
from .policy import known_shapes, eligible, resolve_recipients, is_opted_out
from .composer import plan
from .conversation import classify, delay_seconds, execute, normalize
from .language import language, choose
from .semantic import SemanticClassifier
from .timeutil import timestamp, iso, wall_now, plus_seconds


class Fault(Exception):
    def __init__(self, status: int, reason: str, **extra: Any):
        self.status, self.body = status, {"reason": reason, **extra}
        super().__init__(reason)


class Service:
    def __init__(self, store: Store, settings: Settings):
        self.store, self.settings = store, settings
        self.semantic = SemanticClassifier(settings)

    def _context(self, scope: str, cid: str | None) -> dict | None:
        return self.store.get("contexts", context_key(scope, cid)) if cid else None

    def push(self, req: ContextPush) -> dict:
        p = dict(req.payload)
        reason = known_shapes(req.scope, p, req.context_id)
        if reason:
            raise Fault(400, reason, accepted=False)
        key = context_key(req.scope, req.context_id)
        with self.store.transaction() as db:
            old = db.get("contexts", key)
            if old and old["version"] > req.version:
                raise Fault(409, "stale_version", accepted=False, current_version=old["version"])
            if old and old["version"] == req.version:
                return old["ack"]
            if not old and db.size("contexts") >= self.settings.max_contexts:
                raise Fault(429, "context_capacity", accepted=False)
            identity = {"category": "slug", "merchant": "merchant_id", "customer": "customer_id", "trigger": "id"}[req.scope]
            p.setdefault(identity, req.context_id)
            ack = {"accepted": True, "ack_id": "ack_" + digest([req.scope, req.context_id, req.version])[:24], "stored_at": iso(wall_now())}
            db.put("contexts", key, {"version": req.version, "payload": p, "delivered_at": iso(req.delivered_at), "ack": ack})
            if req.scope == "customer" and is_opted_out(p) and p.get("merchant_id"):
                self._block(p["merchant_id"], req.context_id, "context_opt_out", iso(req.delivered_at))
            if req.scope == "merchant":
                history = p.get("conversation_history", [])
                if isinstance(history, dict):
                    history = history.get("turns", [])
                for turn in history if isinstance(history, list) else []:
                    if isinstance(turn, dict) and turn.get("from", turn.get("role")) == "merchant" and classify(str(turn.get("body", ""))) == "opt_out":
                        self._block(req.context_id, None, "historical_opt_out", str(turn.get("ts", iso(req.delivered_at))))
                        break
            return ack

    def _block(self, mid: str, cid: str | None, reason: str, at: str) -> None:
        key = recipient_key(mid, cid)
        state = self.store.get("recipients", key, {})
        state.update({"opted_out": True, "opted_out_at": at, "opt_out_reason": reason})
        self.store.put("recipients", key, state)

    def _trace(self, entry: dict) -> None:
        seq = int(self.store.get("meta", "trace_seq", 0)) + 1
        self.store.put("meta", "trace_seq", seq)
        entry["sequence"] = seq
        self.store.put("traces", f"{seq:010d}", entry)
        if seq > 1000:
            self.store.delete("traces", f"{seq - 1000:010d}")

    def _receipt(self, key: str | None, body: dict) -> dict | None:
        if not key:
            return None
        item = self.store.get("receipts", key)
        if item:
            if item["request_hash"] != digest(body):
                raise Fault(409, "idempotency_key_reused_with_different_request")
            return item["response"]
        return None

    def tick(self, req: Tick, idempotency_key: str | None = None) -> dict:
        now = req.now
        request_json = req.model_dump(mode="json")
        rk = "tick:" + idempotency_key if idempotency_key else None
        with self.store.transaction() as db:
            cached = self._receipt(rk, request_json)
            if cached is not None:
                return cached
            prepared = []
            skipped = []
            for tid in sorted(set(req.available_triggers)):
                trigger_row = self._context("trigger", tid)
                if not trigger_row:
                    skipped.append({"trigger_id": tid, "reason": "unknown_trigger"})
                    continue
                t = trigger_row["payload"]
                mid, cid, reason = resolve_recipients(t)
                merchant_row = self._context("merchant", mid)
                if reason or not merchant_row:
                    skipped.append({"trigger_id": tid, "reason": reason or "missing_merchant"})
                    continue
                m = merchant_row["payload"]
                cat_row = self._context("category", m.get("category_slug"))
                c_row = self._context("customer", cid)
                if not cat_row:
                    skipped.append({"trigger_id": tid, "reason": "missing_category"})
                    continue
                cat, c = cat_row["payload"], c_row["payload"] if c_row else None
                reason = eligible(cat, m, t, c, now)
                recip = recipient_key(mid, cid)
                state = db.get("recipients", recip, {})
                skey = str(t.get("suppression_key") or f"trigger:{tid}")
                suppression_id = canonical([mid, cid, skey])
                if state.get("opted_out"):
                    reason = "recipient_opted_out"
                elif db.get("suppression", suppression_id):
                    reason = "already_sent_suppression_key"
                elif timestamp(state.get("paused_until")) and now < timestamp(state["paused_until"]):
                    reason = "recipient_paused"
                elif timestamp(state.get("last_interaction")) and now < timestamp(state["last_interaction"]):
                    reason = "out_of_order_clock"
                elif timestamp(state.get("last_send")):
                    cooldown = self.settings.customer_cooldown_seconds if cid else self.settings.merchant_cooldown_seconds
                    # High-urgency operational notices bypass cadence, not consent/pause/STOP.
                    operational = t.get("kind") in {"supply_alert", "regulation_change", "appointment_tomorrow", "chronic_refill_due"} and t.get("urgency", 1) >= 4
                    if not operational and (now - timestamp(state["last_send"])).total_seconds() < cooldown:
                        reason = "recipient_cooldown"
                if reason:
                    skipped.append({"trigger_id": tid, "reason": reason})
                    continue
                versions = {"category": cat_row["version"], "merchant": merchant_row["version"], "trigger": trigger_row["version"]}
                if c_row:
                    versions["customer"] = c_row["version"]
                composition = plan(cat, m, t, c, now, versions, state.get("last_family", ""))
                if not composition.chosen:
                    skipped.append({"trigger_id": tid, "reason": composition.reason})
                    continue
                prepared.append((composition, t, mid, cid, recip, suppression_id, skey, versions))
            prepared.sort(key=lambda x: (-x[0].chosen.priority, str(x[2]), str(x[3] or ""), x[1]["id"]))
            actions, selected_recipients = [], set()
            for composition, t, mid, cid, recip, suppression_id, skey, versions in prepared:
                if len(actions) >= 20 or recip in selected_recipients:
                    skipped.append({"trigger_id": t["id"], "reason": "lower_priority_or_tick_cap"})
                    continue
                chosen = composition.chosen
                conv_id = "conv_" + digest([mid, cid, skey, versions, iso(now)])[:28]
                action = Action(
                    conversation_id=conv_id, merchant_id=mid, customer_id=cid,
                    send_as="merchant_on_behalf" if cid else "vera", trigger_id=t["id"],
                    template_name=f"compass_{chosen.family}_v1", template_params=chosen.parts,
                    body=chosen.body, cta=chosen.cta, suppression_key=skey,
                    rationale=chosen.rationale + f" Context versions: {canonical(versions)}.",
                ).model_dump()
                db.put("conversations", conv_id, {"merchant_id": mid, "customer_id": cid, "trigger_id": t["id"], "pending": chosen.pending,
                    "last_turn": 0, "incoming_count": 0, "last_message": "", "last_output": chosen.body,
                    "sent_bodies": [chosen.body], "created_at": iso(now), "last_at": iso(now), "state": "awaiting_reply"})
                state = db.get("recipients", recip, {})
                state.update({"last_send": iso(now), "last_interaction": iso(now), "last_family": chosen.family})
                db.put("recipients", recip, state)
                db.put("suppression", suppression_id, {"conversation_id": conv_id, "sent_at": iso(now)})
                self._trace({"type": "send", "at": iso(now), "conversation_id": conv_id, "trigger_id": t["id"], "action": action, **composition.trace()})
                actions.append(action)
                selected_recipients.add(recip)
            if skipped:
                self._trace({"type": "skips", "at": iso(now), "decisions": skipped})
            result = {"actions": actions}
            if rk:
                db.put("receipts", rk, {"request_hash": digest(request_json), "response": result})
            return result

    def _reply_identity(self, req: Reply) -> tuple[dict, dict, dict | None, dict, str, str | None]:
        conv = self.store.get("conversations", req.conversation_id)
        mid = req.merchant_id or (conv.get("merchant_id") if conv else None)
        cid = req.customer_id if req.customer_id is not None else conv.get("customer_id") if conv else None
        if conv and ((req.merchant_id and req.merchant_id != conv["merchant_id"]) or (req.customer_id and req.customer_id != conv.get("customer_id"))):
            raise Fault(409, "conversation_recipient_mismatch")
        if (req.from_role == "merchant" and cid is not None) or (req.from_role == "customer" and cid is None):
            raise Fault(400, "role_recipient_mismatch")
        merchant = self._context("merchant", mid)
        if not merchant:
            raise Fault(400, "unknown_merchant")
        customer = self._context("customer", cid)
        if cid and (not customer or customer["payload"].get("merchant_id") != mid):
            raise Fault(400, "unknown_or_mismatched_customer")
        cat = self._context("category", merchant["payload"].get("category_slug"))
        if not cat:
            raise Fault(400, "unknown_category")
        return conv or {}, merchant, customer, cat, mid, cid

    def reply(self, req: Reply) -> dict:
        # Cheap duplicate/identity check before any optional provider request.
        key = canonical([req.conversation_id, req.turn_number])
        request_hash = digest({"message": req.message, "role": req.from_role, "merchant_id": req.merchant_id, "customer_id": req.customer_id})
        intent = classify(req.message)
        semantic_status = "not_used"
        with self.store.transaction() as db:
            conv, merchant, customer, cat, mid, cid = self._reply_identity(req)
            previous = db.get("replies", key)
            if previous:
                if previous["request_hash"] != request_hash:
                    raise Fault(409, "turn_conflict")
                return previous["response"]
            state = db.get("recipients", recipient_key(mid, cid), {})
            if state.get("opted_out"):
                intent = "already_opted_out"
            if req.turn_number <= conv.get("last_turn", 0) and intent not in {"opt_out", "already_opted_out"}:
                raise Fault(409, "stale_turn")
            semkey = digest(["classifier-v1", self.settings.llm_model, req.message])
            if intent == "unknown" and self.settings.semantic_enabled:
                sem = db.get("semantic", semkey)
                if sem:
                    intent, semantic_status = sem["intent"], "cache"
                elif int(db.get("meta", "llm_calls", 0)) < self.settings.llm_max_calls:
                    db.put("meta", "llm_calls", int(db.get("meta", "llm_calls", 0)) + 1)
                    semantic_status = "call"
        # Crucial: no SQLite transaction or service lock during a network call.
        if semantic_status == "call":
            sem = self.semantic.classify(req.message)
            intent, semantic_status = sem["intent"], sem["status"]
        with self.store.transaction() as db:
            # Re-read current contexts/state after network latency.
            conv, merchant, customer, cat, mid, cid = self._reply_identity(req)
            previous = db.get("replies", key)
            if previous:
                if previous["request_hash"] != request_hash:
                    raise Fault(409, "turn_conflict")
                return previous["response"]
            if semantic_status in {"model", "provider_error", "invalid_or_uncertain", "busy"}:
                db.put("semantic", semkey, {"intent": intent, "status": semantic_status})
            recip = recipient_key(mid, cid)
            state = db.get("recipients", recip, {})
            if state.get("opted_out"):
                intent = "already_opted_out"
            if req.turn_number <= conv.get("last_turn", 0) and intent not in {"opt_out", "already_opted_out"}:
                raise Fault(409, "stale_turn")
            if conv.get("last_at") and req.received_at < timestamp(conv["last_at"]) and intent not in {"opt_out", "already_opted_out"}:
                raise Fault(409, "stale_reply_time")
            if not conv:
                conv = {"merchant_id": mid, "customer_id": cid, "trigger_id": None, "pending": {"kind": "recall_request" if cid else "offer_draft"}, "last_turn": 0, "incoming_count": 0, "sent_bodies": [], "state": "new", "created_at": iso(req.received_at)}
            trow = self._context("trigger", conv.get("trigger_id"))
            t = trow["payload"] if trow else {"payload": {}, "scope": "customer" if cid else "merchant"}
            versions = {"merchant": merchant["version"], "category": cat["version"]}
            if customer:
                versions["customer"] = customer["version"]
            if trow:
                versions["trigger"] = trow["version"]
            book = Book({"category": cat["payload"], "merchant": merchant["payload"], "trigger": t, "customer": customer["payload"] if customer else {}, "reply": {"message": req.message}}, versions)
            lang = language(book)
            response = self._respond(intent, req, conv, state, book, mid, cid)
            # New inbound messages open the 24h free-form window. Never advertise a
            # real Meta approval: templates are only the challenge's simulated contract.
            if response.action == "send":
                if not response.body or suspicious(response.body):
                    response = ReplyResult(action="end", rationale="unsafe_or_empty_output")
                elif response.body in conv.get("sent_bodies", []):
                    response = ReplyResult(action="end", rationale="No new supported information; avoid repeating the prior message.")
                else:
                    conv.setdefault("sent_bodies", []).append(response.body)
                    conv["sent_bodies"] = conv["sent_bodies"][-20:]
            conv.update({"last_turn": max(req.turn_number, conv.get("last_turn", 0)), "incoming_count": conv.get("incoming_count", 0) + 1,
                         "last_message": req.message, "last_at": iso(req.received_at), "last_output": response.body,
                         "state": "ended" if response.action == "end" else "waiting" if response.action == "wait" else "awaiting_reply"})
            state = db.get("recipients", recip, state)  # preserve a STOP written by _respond
            prior = timestamp(state.get("last_interaction"))
            if prior is None or req.received_at >= prior:
                state["last_interaction"] = iso(req.received_at)
            db.put("recipients", recip, state)
            db.put("conversations", req.conversation_id, conv)
            result = response.model_dump(exclude_none=True)
            db.put("replies", key, {"request_hash": request_hash, "response": result})
            self._trace({"type": "reply", "conversation_id": req.conversation_id, "at": iso(req.received_at), "intent": intent,
                         "semantic_status": semantic_status, "action": result, "evidence": book.report()})
            return result

    def _respond(self, intent: str, req: Reply, conv: dict, state: dict, book: Book, mid: str, cid: str | None) -> ReplyResult:
        now, pending = req.received_at, conv.get("pending", {"kind": "plan"})
        lang = language(book)
        if intent in {"opt_out", "already_opted_out"}:
            self._block(mid, cid, "explicit_stop", iso(now))
            return ReplyResult(action="end", rationale="Opt-out persisted for this recipient; future proactive outreach is blocked.")
        if intent == "auto_reply":
            state["paused_until"] = plus_seconds(now, 86400)
            self.store.put("recipients", recipient_key(mid, cid), state)
            return ReplyResult(action="end", rationale="Recognized a business auto-response; no bot-to-bot loop. Pause proactive outreach for 24 hours.")
        if intent == "delay":
            seconds = delay_seconds(req.message)
            state["paused_until"] = plus_seconds(now, seconds)
            self.store.put("recipients", recipient_key(mid, cid), state)
            return ReplyResult(action="wait", wait_seconds=seconds, rationale="Requested delay honored; no unsolicited message is scheduled outside the judge's ticks.")
        if intent in {"decline", "hostile"}:
            state["paused_until"] = plus_seconds(now, 86400)
            self.store.put("recipients", recipient_key(mid, cid), state)
            return ReplyResult(action="end", rationale="Conversation ended respectfully; no persuasion loop. Pause outreach for 24 hours.")
        if conv.get("incoming_count", 0) >= self.settings.max_turns:
            return ReplyResult(action="end", rationale="Conversation safety budget reached; no further qualification loop.")
        if customer := book.roots.get("customer"):
            if is_opted_out(customer):
                return ReplyResult(action="end", rationale="Customer consent was revoked in the latest context.")
        if intent in {"injection", "offtopic"}:
            body = choose(lang, "I can help with your business messages, listing checks and the supplied appointment or offer details. I can't access other accounts, reveal private data, or carry out unrelated tasks.", "Business messages, listing checks aur di hui appointment/offer details mein madad kar sakta hoon; doosre accounts ya private data access nahi kar sakta.", "मैं व्यवसाय के संदेश, लिस्टिंग की जाँच और दी गई अपॉइंटमेंट या ऑफ़र जानकारी में मदद कर सकता हूँ। दूसरे खातों या निजी डेटा तक पहुँच नहीं है।")
            return ReplyResult(action="send", body=body, cta="none", rationale="Stay on mission without following instructions embedded in untrusted content.")
        if intent in {"price", "source", "schedule", "metrics"}:
            request_pending = {**pending, "kind": intent}
            if intent == "schedule":
                request_pending["kind"] = "recall_request" if cid else "plan"
            return ReplyResult(action="send", body=execute(book, request_pending, now, question=req.message), cta="none", rationale="Answer the actual question from latest context; no invented external action.")
        if intent == "objection":
            return ReplyResult(action="send", body=choose(lang, "Let's avoid unapproved discounts or extra spend. A listing check and a price-free draft are available without inventing a new offer. I haven't changed any price or subscription.", "Bina approved discount ya extra spend ke listing check aur price-free draft se shuru karte hain. Koi price ya subscription change nahi hua.", "बिना स्वीकृति के डिस्काउंट या अतिरिक्त खर्च नहीं करेंगे। पहले लिस्टिंग जाँच और बिना दाम का मसौदा बनाएं; कोई दाम या सब्सक्रिप्शन नहीं बदला है।"), cta="none", rationale="Respect budget objection without claiming a free paid service or guaranteed ROI.")
        if intent in {"commit", "ack"}:
            if conv.get("fulfilled") and intent == "ack":
                return ReplyResult(action="end", rationale="Acknowledgement after completed draft; no extra question.")
            conv["fulfilled"] = True
            return ReplyResult(action="send", body=execute(book, pending, now, question=req.message), cta="none", rationale="Deliver the pending next action immediately using latest facts; no re-qualification.")
        if pending.get("kind") == "curiosity" and not suspicious(req.message):
            topic = book.string("reply", "message", limit=120)
            conv["pending"] = {"kind": "plan", "topic": topic}
            conv["fulfilled"] = True
            return ReplyResult(action="send", body=execute(book, conv["pending"], now), cta="none", rationale="Use merchant-reported topic as a proposal, not an independently verified demand statistic.")
        # Useful bounded fallback, then stop rather than repeat it.
        return ReplyResult(action="send", body=choose(lang, "I don't have enough confirmed detail to answer that precisely. Here is what I can do with the supplied account: prepare a draft or explain its recorded offer, appointment or performance figures. I won't invent missing details.", "Iska precise jawab dene ke liye confirmed detail nahi hai. Diye gaye account se draft ya recorded offer, appointment aur performance explain kar sakta hoon; missing facts invent nahi karunga.", "सटीक उत्तर के लिए पक्की जानकारी पर्याप्त नहीं है। दिए गए रिकॉर्ड से मसौदा या ऑफ़र, अपॉइंटमेंट और प्रदर्शन की जानकारी समझा सकता हूँ; गायब तथ्य नहीं बनाऊँगा।"), cta="none", rationale="Unrecognized request handled honestly within supported capabilities.")

    def health(self) -> dict:
        with self.store.lock:
            self.store._expire_if_needed()
            counts = {k: 0 for k in ("category", "merchant", "customer", "trigger")}
            for key in self.store.keys("contexts"):
                import json
                counts[json.loads(key)[0]] += 1
            return {"status": "ok", "contexts_loaded": counts}

    def metadata(self) -> dict:
        return {"team_name": self.settings.team_name, "team_members": list(self.settings.team_members),
                "model": ("deterministic fact compiler + optional semantic classifier: " + self.settings.llm_model) if self.settings.semantic_enabled else "deterministic fact compiler (no LLM calls)",
                "approach": "Evidence-backed next actions; independent consent/cadence policy; persistent pending actions and replay traces.",
                "contact_email": self.settings.contact_email, "version": __version__, "submitted_at": self.settings.submitted_at}
