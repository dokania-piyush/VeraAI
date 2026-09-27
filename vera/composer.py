"""Public deterministic composer and traceable candidate selection."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from .evidence import Book, digest, suspicious
from .strategies import Candidate, build_candidates
from .timeutil import timestamp, iso


@dataclass
class Composition:
    chosen: Candidate | None
    alternatives: list[Candidate]
    book: Book
    reason: str = ""

    def trace(self) -> dict:
        return {
            "selected": self.chosen.key if self.chosen else None,
            "reason": self.reason,
            "candidates": [{"key": c.key, "utility_priority": c.priority, "family": c.family,
                            "rationale": c.rationale, "body": c.body} for c in self.alternatives],
            "evidence": self.book.report(),
        }


def plan(category: dict, merchant: dict, trigger: dict, customer: dict | None,
         now: datetime, versions: dict | None = None, last_family: str = "") -> Composition:
    book = Book({"category": category, "merchant": merchant, "trigger": trigger, "customer": customer or {}}, versions or {})
    options = build_candidates(book, now)
    voice = category.get("voice", {})
    taboo = voice.get("vocab_taboo", voice.get("taboos", []))
    taboo = [x.lower() for x in taboo if isinstance(x, str)] if isinstance(taboo, list) else []
    safe = [c for c in options if c.body.strip() and len(c.body) <= 4000 and not suspicious(c.body)
            and not any(t in c.body.lower() for t in taboo if t)]
    # Small diversity adjustment never overrules safety/explicit-action priorities.
    safe.sort(key=lambda c: (-(c.priority - (4 if c.family == last_family else 0)), c.key))
    chosen = safe[0] if safe else None
    return Composition(chosen, safe, book, "selected_highest_eligible_utility" if chosen else "insufficient_safe_evidence")


def offline_reference_time(trigger: dict) -> datetime:
    """Four-argument compatibility only: derive a reproducible fixture clock.

    This is NOT wall time or an eligibility decision. HTTP always supplies tick.now.
    Explicit now= is recommended for evaluation and required for meaningful schedules.
    """
    p = trigger.get("payload", {})
    for value in (trigger.get("observed_at"), trigger.get("created_at"), p.get("match_time_iso"), p.get("due_date"), p.get("stock_runs_out_iso"), p.get("date")):
        dt = timestamp(value)
        if dt:
            return dt
    end = timestamp(trigger.get("expires_at"))
    if not end:
        raise ValueError("Supply now= or a dated trigger; a clock cannot be invented")
    return end - timedelta(days=1)


def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None,
            *, now: str | datetime | None = None) -> dict:
    """Side-effect-free content API from the brief, NOT a sending/consent API.

    For sending decisions use /v1/tick (eligibility, suppression, cooldown, state).
    Four arguments alone use a derived fixture clock documented above.
    """
    clock = timestamp(now) if now is not None else offline_reference_time(trigger)
    if clock is None:
        raise ValueError("now must be an ISO timestamp or datetime")
    result = plan(category, merchant, trigger, customer, clock)
    choice = result.chosen
    note = f" Composition clock: {iso(clock)}" + (" (derived offline fixture clock)." if now is None else ".")
    return {
        "body": choice.body if choice else "",
        "cta": choice.cta if choice else "none",
        "send_as": "merchant_on_behalf" if customer else "vera",
        "suppression_key": trigger.get("suppression_key") or "trigger:" + str(trigger.get("id", digest(trigger)[:16])),
        "rationale": (choice.rationale if choice else result.reason) + note,
    }
