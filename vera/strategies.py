"""Fact-compiled next-action candidates. No seed IDs or memorized merchants.

Each strategy combines a trigger with current merchant/category/customer facts.
Unrelated category examples are never promoted to merchant-approved offers.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import re
from .evidence import Book, percent, text, suspicious
from .language import language, salutation, choose, ask, service_name
from .policy import active_offer_indices
from .timeutil import timestamp, date_text, days_until, IST

KNOWN_KINDS = {
    "research_digest", "regulation_change", "recall_due", "perf_dip", "renewal_due",
    "festival_upcoming", "wedding_package_followup", "curious_ask_due", "winback_eligible",
    "ipl_match_today", "review_theme_emerged", "milestone_reached", "active_planning_intent",
    "seasonal_perf_dip", "customer_lapsed_hard", "trial_followup", "supply_alert",
    "chronic_refill_due", "category_seasonal", "gbp_unverified", "cde_opportunity",
    "competitor_opened", "perf_spike", "dormant_with_vera", "customer_lapsed_soft",
    "appointment_tomorrow",
}
ALIASES = {"category_research_digest_release": "research_digest", "scheduled_recurring": "curious_ask_due", "category_trend_movement": "category_seasonal"}


@dataclass
class Candidate:
    key: str
    body: str
    cta: str
    pending: dict
    priority: int
    family: str
    rationale: str
    parts: list[str] = field(default_factory=list)


def metric_name(raw: str) -> str:
    return {"ctr": "click-through rate", "calls": "calls", "views": "profile views", "leads": "leads", "directions": "direction requests", "review_count": "reviews"}.get(raw, service_name(raw))


def find_digest(book: Book) -> tuple[str, dict] | tuple[None, None]:
    p = book.roots["trigger"].get("payload", {})
    item_id = p.get("top_item_id") or p.get("digest_item_id") or p.get("alert_id")
    if isinstance(p.get("top_item"), dict):
        return "trigger.payload.top_item", p["top_item"]
    for i, item in enumerate(book.roots["category"].get("digest", [])):
        if item_id and item.get("id") == item_id:
            return f"category.digest.{i}", item
    if item_id:
        return None, None  # Never silently substitute an unrelated item.
    items = book.roots["category"].get("digest", [])
    if items:
        # Newly pushed items generally have dates; IDs only provide deterministic ties.
        order = sorted(enumerate(items), key=lambda x: (str(x[1].get("published_at", x[1].get("date", ""))), str(x[1].get("id", ""))), reverse=True)
        i, item = order[0]
        return f"category.digest.{i}", item
    return None, None


def read_path(book: Book, path: str, field: str, default: str = "", limit: int = 400) -> str:
    scope, rest = path.split(".", 1)
    return book.string(scope, f"{rest}.{field}", default, limit)


def slot_options(book: Book, now: datetime) -> list[str]:
    p = book.roots["trigger"].get("payload", {})
    field = "available_slots" if "available_slots" in p else "next_session_options"
    slots = p.get(field, [])
    if not isinstance(slots, list):
        return []
    valid = []
    for i, slot in enumerate(slots):
        if isinstance(slot, dict):
            dt = timestamp(slot.get("iso"))
            if dt and dt > now:
                raw = book.get("trigger", f"payload.{field}.{i}.iso")
                rendered = date_text(raw, with_time=True)
                book.derived("render_iso_slot_in_Asia/Kolkata_ignore_unreliable_label", [f"trigger.payload.{field}.{i}.iso"], rendered)
                valid.append((dt, rendered))
    return [label for _, label in sorted(valid)[:2]]


def build_candidates(book: Book, now: datetime) -> list[Candidate]:
    t, m, c = book.roots["trigger"], book.roots["merchant"], book.roots.get("customer", {})
    raw_kind = str(t.get("kind", ""))
    kind = ALIASES.get(raw_kind, raw_kind)
    book.get("trigger", "kind")
    lang = language(book)
    customer = t.get("scope") == "customer"
    name = salutation(book, customer)
    brand = book.string("merchant", "identity.name", "the business", 100)
    candidates: list[Candidate] = []
    urgency = int(t.get("urgency", 1))
    category = book.string("category", "slug")

    def add(key: str, lead: str, action: str | None, priority: int, family: str, why: str,
            pending: dict | None = None, cta_text: str | None = None, prefix: bool = True) -> None:
        if not lead or suspicious(lead):
            return
        question = cta_text if cta_text is not None else ask(action, lang) if action else ""
        intro = f"{name}, {lead}" if prefix else lead
        body = " ".join(x for x in (intro, question) if x)
        cta = "binary_yes_stop" if customer and question else "open_ended" if question else "none"
        remembered = dict(pending or {"kind": action or "info"})
        if remembered.get("kind") == "offer_draft" and offers:
            oid = book.string("merchant", f"offers.{offers[0]}.id")
            if oid:
                remembered["offer_id"] = oid
        candidates.append(Candidate(key, body, cta, remembered, priority + urgency, family, why, [intro, question]))

    offers = active_offer_indices(m, now, customer=c if customer else None)

    def offer_title() -> str:
        return book.string("merchant", f"offers.{offers[0]}.title", limit=180) if offers else ""

    def perf_summary() -> str:
        calls = book.number("merchant", "performance.calls")
        views = book.number("merchant", "performance.views")
        window = book.number("merchant", "performance.window_days")
        if views is None or calls is None:
            return ""
        period = f"{window:g}-day" if window is not None else "latest"
        return choose(lang,
            f"your {period} snapshot shows {views:g} profile views and {calls:g} calls.",
            f"Aapke {period} snapshot mein {views:g} profile views aur {calls:g} calls hain.",
            f"आपके {period} रिकॉर्ड में {views:g} प्रोफ़ाइल व्यू और {calls:g} कॉल हैं।")

    if customer:
        if kind == "recall_due":
            due = book.string("trigger", "payload.due_date")
            service = service_name(book.string("trigger", "payload.service_due", "check-up"))
            if not timestamp(due):
                return []
            slots = slot_options(book, now)
            lead = choose(lang,
                f"{brand}'s reminder lists your {service} for {date_text(due)}.",
                f"{brand} ke reminder mein aapka {service} {date_text(due)} ko due hai.",
                f"{brand} के रिकॉर्ड के अनुसार आपके {service} का रिमाइंडर {date_text(due)} के लिए है।")
            if slots:
                lead += choose(lang, f" Listed option: {slots[0]} (not booked).", f" Listed option: {slots[0]} — booking confirm nahi hai.", f" दिया गया विकल्प: {slots[0]} — बुकिंग की पुष्टि नहीं हुई है।")
            add("recall", lead, "recall_request", 70, "service", "Reminder consent only; no promotion or medical recommendation added.", {"kind": "recall_request"})
        elif kind == "chronic_refill_due":
            due = book.string("trigger", "payload.stock_runs_out_iso")
            if not timestamp(due):
                return []
            lead = choose(lang,
                f"{brand}'s refill reminder lists {date_text(due)} as your next supply-check date. Please confirm the refill with the pharmacist; this is not a dispensing confirmation.",
                f"{brand} ke refill reminder ki date {date_text(due)} hai. Refill pharmacist se confirm karein; medicines abhi dispense nahi hui hain.",
                f"{brand} का अगला रिफिल रिमाइंडर {date_text(due)} के लिए है। दवा की उपलब्धता फ़ार्मासिस्ट से पक्की करें; यह दवा भेजे जाने की पुष्टि नहीं है।")
            add("refill", lead, "refill_request", 85, "service", "Scoped refill consent; no drug list, diagnosis, prepared stock, price or dispatch invented.")
        elif kind == "wedding_package_followup":
            wedding = book.string("trigger", "payload.wedding_date") or book.string("customer", "preferences.wedding_date")
            trial = book.string("trigger", "payload.trial_completed")
            if not timestamp(wedding):
                return []
            lead = choose(lang,
                f"your wedding date with {brand} is noted as {date_text(wedding)}. We can draft the next consultation enquiry without assuming a package price or reserved slot.",
                f"{brand} ke record mein wedding date {date_text(wedding)} hai. Bina package price ya slot assume kiye consultation enquiry draft kar sakte hain.",
                f"{brand} के रिकॉर्ड में शादी की तारीख {date_text(wedding)} है। पैकेज का दाम या बुकिंग मानकर चले बिना अगली परामर्श-पूछताछ तैयार कर सकते हैं।")
            if trial:
                book.get("trigger", "payload.trial_completed")
            add("bridal", lead, "recall_request", 65, "service", "Bridal follow-up permission, actual wedding date; no invented package.")
        elif kind in {"customer_lapsed_soft", "customer_lapsed_hard"}:
            last = book.string("customer", "relationship.last_visit")
            if not timestamp(last) or timestamp(last) > now:
                return []
            lead = choose(lang,
                f"your last recorded visit to {brand} was {date_text(last)}. A return can start at your own pace—no pressure to make up missed visits.",
                f"{brand} mein aapki last recorded visit {date_text(last)} thi. Apne pace par wapas shuru kar sakte hain—missed visits ka pressure nahi.",
                f"{brand} में आपकी पिछली दर्ज विज़िट {date_text(last)} की है। अपनी सुविधा से लौटें; छूटी विज़िट पूरी करने का दबाव नहीं है।")
            add("return", lead, "return_request", 45, "retention", "Permissioned winback without body shaming or an unverified returning-customer offer.")
        elif kind == "trial_followup":
            trial = book.string("trigger", "payload.trial_date")
            if not timestamp(trial) or timestamp(trial) > now:
                return []
            slots = slot_options(book, now)
            lead = choose(lang,
                f"following the {date_text(trial)} trial at {brand}, you can enquire about the next session.",
                f"{brand} mein {date_text(trial)} ke trial ke baad next session ke liye enquiry kar sakte hain.",
                f"{brand} में {date_text(trial)} के ट्रायल के बाद अगले सत्र की पूछताछ कर सकते हैं।")
            if slots:
                lead += f" Listed option: {slots[0]} (subject to confirmation)."
            add("trial", lead, "recall_request", 60, "service", "Address guardian when supplied; ISO slot date wins over inconsistent weekday labels.")
        elif kind == "appointment_tomorrow":
            dt = book.string("trigger", "payload.appointment_at") or book.string("trigger", "payload.appointment_iso") or book.string("trigger", "payload.booking_time")
            if not timestamp(dt) or timestamp(dt) <= now:
                return []
            d = days_until(dt, now)
            if d is not None and d > 2:
                return []
            lead = choose(lang, f"your appointment record at {brand} lists {date_text(dt, with_time=True)}.", f"{brand} ke appointment record mein {date_text(dt, with_time=True)} listed hai.", f"{brand} में अपॉइंटमेंट रिकॉर्ड में {date_text(dt, with_time=True)} दर्ज है।")
            add("appointment", lead, "recall_request", 80, "service", "Existing appointment timestamp required; trigger name alone is not proof of a booking.")
        elif kind in {"festival_upcoming", "ipl_match_today", "category_seasonal"}:
            title = offer_title()
            if title:
                add("customer_offer", choose(lang, f"{brand} currently lists {title}. Eligibility and availability still need the team's confirmation.", f"{brand} par {title} listed hai. Eligibility aur availability team confirm karegi.", f"{brand} में {title} दर्ज है। पात्रता और उपलब्धता टीम से पक्की करें।"), "return_request", 40, "growth", "Only active merchant-owned offer and explicit promotional consent.")
        return candidates

    # Merchant strategies: priority is a documented utility heuristic, NOT a judge score.
    if kind in {"research_digest", "regulation_change", "cde_opportunity", "supply_alert"}:
        path, item = find_digest(book)
        if path and item:
            title = read_path(book, path, "title", limit=240)
            source = read_path(book, path, "source", limit=160)
            published = timestamp(item.get("published_at"))
            if title and source and not (published and published > now):
                lead = choose(lang, f"your supplied digest cites {source}: “{title}”.", f"{source} mein update hai: “{title}”.", f"{source} से मिली जानकारी: “{title}”।")
                pending = {"kind": "research_summary", "digest_path": path, "digest_id": item.get("id"), "sensitive": kind in {"regulation_change", "supply_alert"} or category in {"dentists", "pharmacies"}}
                if kind == "regulation_change":
                    deadline = book.string("trigger", "payload.deadline_iso")
                    if timestamp(deadline):
                        lead += choose(lang, f" The supplied deadline is {date_text(deadline)}; verify the notice before changing practice.", f" Di hui deadline {date_text(deadline)} hai; practice badalne se pehle notice verify karein.", f" दी गई अंतिम तारीख {date_text(deadline)} है; बदलाव से पहले नोटिस की पुष्टि करें।")
                    pending["kind"] = "checklist"
                    add("compliance", lead, "checklist", 96, "safety", "Attributes the supplied notice rather than claiming independently verified legal/clinical guidance.", pending)
                elif kind == "supply_alert":
                    batches = book.get("trigger", "payload.affected_batches", [])
                    if isinstance(batches, list) and batches:
                        lead += " Supplied batch IDs: " + ", ".join(text(x, 45) for x in batches[:5]) + "."
                    pending["kind"] = "checklist"
                    add("supply", lead, "checklist", 98, "safety", "Verify inventory/batches with responsible pharmacist; affected customer count is unknown.", pending)
                elif kind == "cde_opportunity":
                    dt = read_path(book, path, "date")
                    if timestamp(dt) and timestamp(dt) <= now:
                        return []
                    if timestamp(dt):
                        lead += f" Listed for {date_text(dt, with_time='T' in dt)}."
                    add("learning", lead, "research_summary", 52, "knowledge", "Use supplied event date and source, without claiming enrollment.", pending)
                else:
                    # Actual merchant metric ties category knowledge to this business.
                    own = book.number("merchant", "performance.ctr")
                    peer = book.number("category", "peer_stats.avg_ctr")
                    if own is not None and peer is not None and own < peer:
                        lead += f" Your click-through rate is {percent(own)}; the supplied category average is {percent(peer)}."
                    add("digest", lead, "research_summary", 55, "knowledge", "Cited current digest, honest category-average label; no fabricated local demand or patient cohort.", pending)
    elif kind in {"perf_dip", "perf_spike", "seasonal_perf_dip"}:
        metric = book.string("trigger", "payload.metric")
        delta = book.number("trigger", "payload.delta_pct")
        window = book.string("trigger", "payload.window", "latest comparison")
        if delta is None:
            delta_map = m.get("performance", {}).get("delta_7d", {})
            delta_map = delta_map if isinstance(delta_map, dict) else {}
            options = [(key[:-4], val) for key, val in delta_map.items() if key.endswith("_pct") and isinstance(val, (int, float)) and not isinstance(val, bool)]
            options = [x for x in options if x[1] < 0] if kind != "perf_spike" else [x for x in options if x[1] > 0]
            if options:
                metric, delta = max(options, key=lambda x: (abs(x[1]), x[0]))
                book.get("merchant", f"performance.delta_7d.{metric}_pct")
                window = "7-day comparison"
        if metric and delta is not None:
            direction = "down" if delta < 0 else "up" if delta > 0 else "unchanged at"
            change = percent(abs(delta))
            lead = choose(lang, f"your {metric_name(metric)} are {direction} {change} in the {window}.", f"{window} mein aapke {metric_name(metric)} {change} {'kam' if delta < 0 else 'zyada'} hain.", f"{window} में आपके {metric_name(metric)} में {change} {'की कमी' if delta < 0 else 'की बढ़ोतरी'} दर्ज है।")
            if kind == "seasonal_perf_dip" and book.get("trigger", "payload.is_expected_seasonal") is True:
                lead += " The supplied context flags a seasonal pattern, not proof that service quality fell."
            title = offer_title()
            if title:
                lead += f" Your listed offer is {title}."
            add("performance", lead, "performance_audit", 65 if delta < 0 else 50, "functional", "Uses actual signed change; seasonality/likely driver is not asserted as proven causation.")
        else:
            summary = perf_summary()
            if summary:
                add("snapshot", summary, "performance_audit", 42, "functional", "Missing comparison data: reports the snapshot without inventing a decline/spike.")
    elif kind == "review_theme_emerged":
        theme = book.string("trigger", "payload.theme")
        count = book.number("trigger", "payload.occurrences_30d")
        if not theme or count is None:
            reviews = m.get("review_themes", [])
            neg = [(i, r) for i, r in enumerate(reviews) if r.get("sentiment") == "neg" and type(r.get("occurrences_30d")) in (int, float)]
            if neg:
                i, r = max(neg, key=lambda x: (x[1].get("occurrences_30d", 0), str(x[1].get("theme", ""))))
                theme = book.string("merchant", f"review_themes.{i}.theme")
                count = book.number("merchant", f"review_themes.{i}.occurrences_30d")
        if theme and count is not None and count > 0:
            human = "late delivery" if theme == "delivery_late" else service_name(theme)
            lead = choose(lang, f"{count:g} reviews in the supplied 30-day window mention {human}. Addressing that is more useful than adding another discount.", f"Diye gaye 30-day window mein {count:g} reviews mein {human} ka zikr hai. Naya discount dene se pehle isko address karein.", f"दिए गए 30-दिन के रिकॉर्ड में {count:g} समीक्षाओं में {human} का ज़िक्र है। नया डिस्काउंट देने से पहले इसे समझना बेहतर होगा।")
            add("review", lead, "review_reply" if theme == "delivery_late" else "review_general", 82, "service", "Review mentions are not a defect rate or count of all affected customers.", {"kind": "review_reply", "theme": theme})
    elif kind == "milestone_reached":
        current = book.number("trigger", "payload.value_now")
        target = book.number("trigger", "payload.milestone_value")
        metric = metric_name(book.string("trigger", "payload.metric", "reviews"))
        if current is not None and target is not None:
            gap = target - current
            book.derived("target_minus_current", ["trigger.payload.milestone_value", "trigger.payload.value_now"], gap)
            lead = f"you're at {current:g} {metric}—{gap:g} away from {target:g}." if gap > 0 else f"you've reached {current:g} {metric}, passing the {target:g} mark."
            add("milestone", lead, "plan", 48, "recognition", "Does not celebrate an imminent milestone as already achieved.", {"kind": "review_request"})
        else:
            value = book.number("merchant", "performance.calls")
            if value is not None:
                add("milestone_check", f"the supplied snapshot records {value:g} calls, but doesn't establish which milestone was reached.", "performance_audit", 25, "functional", "Missing milestone values are acknowledged, not invented.")
    elif kind == "renewal_due":
        days = book.number("trigger", "payload.days_remaining")
        if days is None:
            days = book.number("merchant", "subscription.days_remaining")
        plan = book.string("merchant", "subscription.plan", "current")
        if days is not None:
            amount = book.number("trigger", "payload.renewal_amount")
            lead = choose(lang, f"your supplied {plan} subscription snapshot has {days:g} days remaining.", f"Aapke diye gaye {plan} snapshot mein {days:g} din remaining hain.", f"आपके दिए गए {plan} सब्सक्रिप्शन रिकॉर्ड में {days:g} दिन बाकी हैं।")
            if amount is not None:
                lead += f" The renewal quote supplied is ₹{amount:g}; I cannot process payments."
            add("renewal", lead, "plan", 80 if days <= 14 else 45, "functional", "Reports days as a snapshot rather than silently assuming an as-of date; no payment claim.", {"kind": "renewal_plan"})
    elif kind == "ipl_match_today":
        match = book.string("trigger", "payload.match")
        when = book.string("trigger", "payload.match_time_iso")
        if match and timestamp(when):
            lead = f"{match} is listed for {date_text(when, with_time=True)}."
            negs = [(i, r) for i, r in enumerate(m.get("review_themes", [])) if r.get("theme") == "delivery_late" and r.get("sentiment") == "neg"]
            if negs:
                i, _ = negs[0]
                count = book.number("merchant", f"review_themes.{i}.occurrences_30d")
                if count is not None:
                    lead += f" Your recent 30-day review summary has {count:g} late-delivery mentions."
                add("match_operations", lead, "review_reply", 78, "service", "Match-specific operations before promotion; no invalid weekday offer or projected order lift.", {"kind": "review_reply", "theme": "delivery_late"})
            title = offer_title()
            if title:
                add("match_offer", f"{lead} Your valid listed offer is {title}.", "offer_draft", 56, "growth", "Match date and merchant-owned offer checked against the evaluation clock.")
            elif not negs:
                add("match_plan", lead + " No approved offer is available for this date.", "plan", 35, "growth", "Propose planning, not a fabricated match-night discount.")
    elif kind == "festival_upcoming":
        festival = book.string("trigger", "payload.festival")
        when = book.string("trigger", "payload.date")
        d = days_until(when, now)
        if festival and d is not None and 0 <= d <= 45:
            book.derived("calendar_date_difference_Asia/Kolkata", ["trigger.payload.date", "evaluation_clock"], d)
            lead = f"the supplied {festival} date is {date_text(when)}, {d} days away."
            title = offer_title()
            if title:
                lead += f" Your approved offer is {title}."
            add("festival", lead, "offer_draft" if title else "plan", 48, "growth", "Recomputes days until festival; no assumed surge or fabricated festival price.")
    elif kind == "competitor_opened":
        competitor = book.string("trigger", "payload.competitor_name")
        distance = book.number("trigger", "payload.distance_km")
        if competitor:
            lead = f"the supplied update lists {competitor}"
            lead += f" {distance:g} km away." if distance is not None else " as a new competitor."
            their = book.string("trigger", "payload.their_offer")
            if their:
                lead += f" Their offer—not yours—is {their}."
            own = offer_title()
            if own:
                lead += f" Your approved option is {own}; no need to assume a price match."
            add("competitor", lead, "offer_draft" if own else "plan", 55, "growth", "Competitor price remains attributed to competitor; no claim of superior treatment/outcomes.")
    elif kind == "gbp_unverified":
        verified = book.get("merchant", "identity.verified")
        if verified is False:
            add("verification", f"{brand}'s supplied listing is marked unverified. Let's check that before promising more calls.", "checklist", 75, "functional", "No guaranteed uplift or automated verification claim.", {"kind": "verification_checklist"})
    elif kind == "active_planning_intent":
        topic = service_name(book.string("trigger", "payload.intent_topic", "your next campaign"))
        title = offer_title()
        lead = f"here's a draft structure for {topic}: confirm the audience, delivery format and capacity first."
        if title:
            lead += f" Existing approved offer: {title}. Any new bundle price still needs your approval."
        else:
            lead += " Price, schedule and capacity remain unconfirmed."
        add("planning", lead, None, 93, "action", "Explicit planning intent gets a tangible draft now, not another qualifying loop.", {"kind": "plan", "topic": topic})
    elif kind in {"dormant_with_vera", "winback_eligible"}:
        summary = perf_summary()
        if summary:
            lead = summary + choose(lang, " Let's start with a useful listing review, not a subscription pitch.", " Subscription pitch ke bajaye useful listing review se shuru karein.", " सब्सक्रिप्शन की बात से पहले उपयोगी लिस्टिंग समीक्षा से शुरू करें।")
            add("reconnect", lead, "performance_audit", 36, "retention", "Re-engagement gives concrete account value without causal revenue-loss claims.")
    elif kind == "curious_ask_due":
        question = {
            "salons": "Which service did customers ask about most this week?",
            "dentists": "Which patient question has come up most in your consultations this week?",
            "restaurants": "Which dish did customers ask for most this week?",
            "gyms": "What is the main thing stopping trial members from returning this week?",
            "pharmacies": "Which availability question came up most at the counter this week?",
        }.get(category, "What did customers ask you about most this week?")
        if lang in {"hi", "hi-en"}:
            question = "Is hafte customers ne sabse zyada kis service ke baare mein poochha?" if lang == "hi-en" else "इस हफ़्ते ग्राहकों ने सबसे ज़्यादा किस सेवा के बारे में पूछा?"
        lead = perf_summary() or "a practical check-in for your next business update."
        add("curiosity", lead, None, 30, "curiosity", "One category-specific question; answer becomes a draftable next action, not a fabricated demand claim.", {"kind": "curiosity"}, question)
    elif kind == "category_seasonal":
        trends = book.roots["category"].get("trend_signals", [])
        if trends:
            valid = [(i, d) for i, d in enumerate(trends) if type(d.get("delta_yoy")) in (int, float) and d.get("query")]
            if valid:
                i, _ = max(valid, key=lambda x: (x[1]["delta_yoy"], str(x[1]["query"])))
                q = book.string("category", f"trend_signals.{i}.query")
                delta = book.number("category", f"trend_signals.{i}.delta_yoy")
                lead = f"the supplied category trend for “{q}” is {percent(abs(delta))} {'up' if delta >= 0 else 'down'} year-on-year. This is a category signal, not measured demand at {brand}."
                add("trend", lead, "plan", 44, "knowledge", "Category evidence labeled as such; no forecast for this merchant.")
        if not candidates:
            season = book.string("trigger", "payload.season")
            trends = book.get("trigger", "payload.trends", [])
            if season and isinstance(trends, list) and trends:
                detail = "; ".join(text(x, 100).replace("_", " ") for x in trends[:2])
                add("season", f"the supplied {service_name(season)} update lists {detail}. These are category indicators, not your inventory levels.", "checklist", 45, "knowledge", "No invented stock quantities or medication substitution.", {"kind": "stock_checklist"})

    # Graceful merchant-only fallback: use a real account fact, never invent the missing event.
    if not candidates and kind not in {"festival_upcoming", "regulation_change", "supply_alert", "cde_opportunity", "research_digest"}:
        summary = perf_summary()
        if summary:
            add("account_review", summary, "performance_audit", 15, "functional", f"The {raw_kind or 'unknown'} event lacks actionable detail; use a current account snapshot without inventing event specifics.")
    return candidates
