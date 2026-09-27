from copy import deepcopy
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from vera.api import create_app
from vera.config import Settings

NOW = "2026-04-26T10:00:00Z"


@pytest.fixture
def data():
    return {
        "category": {"slug": "salons", "voice": {"tone": "warm_practical", "vocab_taboo": ["guaranteed glow"]}, "peer_stats": {"avg_ctr": .04}, "digest": [{"id": "d1", "title": "Colour service enquiries increase 18%", "source": "Synthetic category bulletin", "summary": "Supplied sample: enquiries rose 18% in the measured group."}]},
        "merchant": {"merchant_id": "m1", "category_slug": "salons", "identity": {"name": "Mira Studio", "owner_first_name": "Mira", "languages": ["en"], "verified": True}, "performance": {"window_days": 30, "views": 1500, "calls": 25, "ctr": .025, "delta_7d": {"calls_pct": -.2}}, "offers": [{"id": "offer1", "title": "Hair Spa @ ₹499", "status": "active", "started": "2026-01-01"}], "subscription": {"plan": "Pro", "days_remaining": 10}, "conversation_history": []},
        "customer": {"customer_id": "c1", "merchant_id": "m1", "identity": {"name": "Dev", "language_pref": "en"}, "relationship": {"last_visit": "2026-01-10", "visits_total": 3}, "preferences": {"channel": "whatsapp", "reminder_opt_in": True}, "consent": {"opted_in_at": "2025-01-01", "scope": ["recall_reminders", "appointment_reminders", "promotional_offers", "winback_offers", "refill_reminders", "bridal_package_followup", "program_updates"]}},
        "trigger": {"id": "t1", "kind": "perf_dip", "scope": "merchant", "merchant_id": "m1", "customer_id": None, "payload": {"metric": "calls", "delta_pct": -.2, "window": "7d"}, "urgency": 3, "suppression_key": "dip:m1:w1", "expires_at": "2026-05-10T00:00:00Z"},
    }


@pytest.fixture
def client():
    with TestClient(create_app(Settings(db_path=":memory:", admin_token="test-admin"))) as c:
        yield c


def push(client, scope, payload, version=1, cid=None):
    field = {"category": "slug", "merchant": "merchant_id", "customer": "customer_id", "trigger": "id"}[scope]
    return client.post("/v1/context", json={"scope": scope, "context_id": cid or payload[field], "version": version, "payload": payload, "delivered_at": NOW})


def load(client, data):
    for scope in ("category", "merchant", "customer", "trigger"):
        assert push(client, scope, data[scope]).status_code == 200


def tick(client, ids=None, now=NOW, headers=None):
    return client.post("/v1/tick", json={"now": now, "available_triggers": ["t1"] if ids is None else ids}, headers=headers)


def reply(client, conv_id, message="yes", turn=2, now="2026-04-26T10:05:00Z", **overrides):
    body = {"conversation_id": conv_id, "merchant_id": "m1", "customer_id": None, "from_role": "merchant", "message": message, "received_at": now, "turn_number": turn}
    body.update(overrides)
    return client.post("/v1/reply", json=body)
