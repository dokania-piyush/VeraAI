"""Non-model eligibility, recipient isolation, consent and offer validity."""
from datetime import datetime, time
import re
from typing import Any
from .timeutil import timestamp, IST, days_until

CONSENT = {
    "recall_due": {"recall_reminders"},
    "customer_lapsed_soft": {"winback_offers", "promotional_offers"},
    "customer_lapsed_hard": {"winback_offers", "promotional_offers"},
    "appointment_tomorrow": {"appointment_reminders"},
    "chronic_refill_due": {"refill_reminders"},
    "wedding_package_followup": {"bridal_package_followup"},
    "trial_followup": {"program_updates", "kids_program_updates", "trial_followup", "appointment_reminders"},
    "renewal_due": {"renewal_reminders"},
    "supply_alert": {"recall_alerts"},
    "ipl_match_today": {"match_night_specials", "promotional_offers"},
    "festival_upcoming": {"promotional_offers"},
    "category_seasonal": {"seasonal_health_content", "promotional_offers"},
}


def resolve_recipients(trigger: dict) -> tuple[str | None, str | None, str | None]:
    p = trigger.get("payload", {})
    p = p if isinstance(p, dict) else {}
    for field in ("merchant_id", "customer_id"):
        if trigger.get(field) and p.get(field) and trigger[field] != p[field]:
            return None, None, "recipient_conflict"
    mid = trigger.get("merchant_id") or p.get("merchant_id")
    cid = trigger.get("customer_id") or p.get("customer_id")
    if not isinstance(mid, str) or (cid is not None and not isinstance(cid, str)):
        return None, None, "missing_recipient"
    return mid, cid, None


def known_shapes(scope: str, payload: dict, cid: str) -> str | None:
    id_field = {"category": "slug", "merchant": "merchant_id", "customer": "customer_id", "trigger": "id"}[scope]
    if id_field in payload and payload[id_field] != cid:
        return "context_identity_mismatch"
    for field in ("identity", "performance", "subscription", "preferences", "consent", "relationship", "payload", "voice", "peer_stats"):
        if field in payload and not isinstance(payload[field], dict):
            return f"invalid_{field}"
    for field in ("offers", "digest", "review_themes", "trend_signals", "patient_content_library"):
        if field in payload and (not isinstance(payload[field], list) or any(not isinstance(x, dict) for x in payload[field])):
            return f"invalid_{field}"
    if "conversation_history" in payload and not isinstance(payload["conversation_history"], (dict, list)):
        return "invalid_conversation_history"
    if "signals" in payload and not isinstance(payload["signals"], list):
        return "invalid_signals"
    performance = payload.get("performance", {})
    if "delta_7d" in performance and not isinstance(performance["delta_7d"], dict):
        return "invalid_delta_7d"
    for field in ("views", "calls", "ctr", "reviews_count", "avg_rating"):
        value = performance.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            return "invalid_performance_number"
    relation = payload.get("relationship", {})
    if "visits_total" in relation and (type(relation["visits_total"]) is not int or relation["visits_total"] < 0):
        return "invalid_visits_total"
    cons = payload.get("consent", {})
    if "scope" in cons and (not isinstance(cons["scope"], list) or any(not isinstance(x, str) for x in cons["scope"])):
        return "invalid_consent_scope"
    if scope == "trigger":
        for field in ("kind", "suppression_key"):
            if field in payload and not isinstance(payload[field], str):
                return f"invalid_{field}"
        if payload.get("scope", "merchant") not in ("merchant", "customer"):
            return "invalid_trigger_scope"
        for field in ("expires_at", "not_before", "created_at"):
            if payload.get(field) and not timestamp(payload[field]):
                return f"invalid_{field}"
        if "urgency" in payload and (not isinstance(payload["urgency"], int) or isinstance(payload["urgency"], bool) or not 1 <= payload["urgency"] <= 5):
            return "invalid_urgency"
    return None


def is_opted_out(customer: dict) -> bool:
    c = customer.get("consent", {})
    return bool(c.get("opted_out_at") or c.get("revoked_at") or c.get("revoked") or c.get("opted_in") is False)


def eligible(category: dict, merchant: dict, trigger: dict, customer: dict | None, now: datetime) -> str | None:
    mid, cid, err = resolve_recipients(trigger)
    if err:
        return err
    if merchant.get("merchant_id") != mid:
        return "merchant_mismatch"
    if category.get("slug") != merchant.get("category_slug"):
        return "category_mismatch"
    p = trigger.get("payload", {})
    if p.get("category") and p["category"] != category.get("slug"):
        return "trigger_category_mismatch"
    end = timestamp(trigger.get("expires_at"))
    if not end:
        return "missing_expiry"
    if now >= end:
        return "expired_trigger"
    start = timestamp(trigger.get("not_before") or p.get("not_before"))
    if start and now < start:
        return "not_yet_due"
    if trigger.get("scope") == "customer":
        if not customer or not cid:
            return "missing_customer"
        if customer.get("customer_id") != cid or customer.get("merchant_id") != mid:
            return "customer_mismatch"
        if is_opted_out(customer):
            return "consent_revoked"
        cons = customer.get("consent", {})
        granted = timestamp(cons.get("opted_in_at"))
        if not granted or granted > now:
            return "missing_or_future_consent"
        scopes = cons.get("scope", [])
        if not isinstance(scopes, list) or any(not isinstance(x, str) for x in scopes):
            return "invalid_consent_scope"
        required = CONSENT.get(trigger.get("kind"), set())
        if not required or not set(scopes).intersection(required):
            return "consent_scope_mismatch"
        pref = customer.get("preferences", {})
        if pref.get("reminder_opt_in") is False:
            return "preference_opt_out"
        channel = pref.get("channel", "")
        if channel not in {"whatsapp", "whatsapp_via_parent", "whatsapp_via_son"}:
            return "unsupported_channel"
        quiet = pref.get("quiet_hours")
        if isinstance(quiet, dict):
            try:
                a, b = (time.fromisoformat(quiet[x]) for x in ("start", "end"))
                local = now.astimezone(IST).time().replace(tzinfo=None)
                if (a <= local < b) if a <= b else (local >= a or local < b):
                    return "quiet_hours"
            except (KeyError, TypeError, ValueError):
                return "invalid_quiet_hours"
        kind = trigger.get("kind", "")
        field, horizon = {"recall_due": ("due_date", 30), "wedding_package_followup": ("wedding_date", 45), "chronic_refill_due": ("stock_runs_out_iso", 7)}.get(kind, ("", 0))
        d = days_until(p.get(field), now)
        if d is not None and d > horizon:
            return "outside_useful_window"
    elif cid is not None:
        return "unexpected_customer"
    return None


DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def active_offer_indices(merchant: dict, now: datetime, *, customer: dict | None = None) -> list[int]:
    eligible_offers = []
    for i, offer in enumerate(merchant.get("offers", [])):
        if offer.get("status") != "active" or not offer.get("title"):
            continue
        raw_start = offer.get("started") or offer.get("starts_at") or offer.get("valid_from")
        raw_end = offer.get("expires_at") or offer.get("valid_until") or offer.get("ends_at")
        start, end = timestamp(raw_start), timestamp(raw_end)
        if (raw_start and not start) or (raw_end and not end):
            continue  # Invalid restrictions must not silently become unrestricted.
        if (start and now < start) or (end and now >= end):
            continue
        title = str(offer["title"]).lower()
        valid_days = offer.get("valid_days") or offer.get("days_of_week")
        if valid_days:
            if not isinstance(valid_days, list):
                continue
            allowed = {DAYS.get(str(d).lower()[:3], d if isinstance(d, int) else -1) for d in valid_days}
            if now.astimezone(IST).weekday() not in allowed:
                continue
        match = re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)(?:day|sday|nesday|rsday|urday)?\s*(?:[-–]|to)\s*(mon|tue|wed|thu|fri|sat|sun)", title)
        if match:
            a, b = DAYS[match[1]], DAYS[match[2]]
            allowed = {(a + n) % 7 for n in range((b - a) % 7 + 1)}
            if now.astimezone(IST).weekday() not in allowed:
                continue
        if not match:
            single_days = re.findall(r"\b(mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b", title)
            if single_days and now.astimezone(IST).weekday() not in {DAYS[d[:3]] for d in single_days}:
                continue
        if "weekday" in title and now.astimezone(IST).weekday() >= 5:
            continue
        if "weekend" in title and now.astimezone(IST).weekday() < 5:
            continue
        visits = customer.get("relationship", {}).get("visits_total", 0) if customer else 0
        if not isinstance(visits, (int, float)) or isinstance(visits, bool):
            continue
        if customer and visits > 0:
            if offer.get("audience") == "new_user" or re.search(r"first month|new (?:user|customer)|trial", title):
                continue
        eligible_offers.append(i)
    return eligible_offers
