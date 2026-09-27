# Vera Compass
### Evidence-backed next actions for the magicpin Vera challenge

**A runnable candidate, not a claimed winning submission.** Start with [START_HERE.md](START_HERE.md) for setup, test, deployment and submission steps.

Vera Compass checks whether outreach is appropriate, selects a useful signal, compiles a message from supplied facts, and remembers the action it promised. When the recipient says “yes,” it delivers that action using the **latest** context—not an old price or another merchant's offer.

## Design

The default is a deterministic Python fact compiler with a FastAPI HTTP adapter and SQLite state. It requires **no API key**. Optional model assistance classifies otherwise-unrecognized replies into a closed intent catalog; it does not author business facts or execute tools. Optional model mode has not been live-provider benchmarked.

The differentiators are source-field evidence records, recipient-specific consent/STOP state independent of snapshots, offer-ID-bound follow-through, and an admin-only decision studio for counterfactual previews. Its templates are context-driven strategies, not seed-ID lookups. Unknown or sparse inputs can produce a grounded fallback or a justified abstention.

## Run

```bash
python -m venv .venv
# Activate .venv using the instructions in START_HERE.md.
python -m pip install -r requirements-dev.txt -c requirements-lock.txt
python -m pytest -q
python -m scripts.run
```

In another terminal: `python -m scripts.demo --reset`. This wipes **local test state**, sends synthetic contexts, changes ₹499 to ₹599, accepts the pending draft, then verifies STOP. Do not run it during judging.

## HTTP contract

| Endpoint | Purpose |
|---|---|
| `POST /v1/context` | Versioned, atomic snapshot replacement; same version is a no-op |
| `POST /v1/tick` | Eligible actions, at most 20, with recipient-level deduplication |
| `POST /v1/reply` | Send, wait or end; durable conversation state |
| `GET /v1/healthz` | Liveness and loaded-context counts |
| `GET /v1/metadata` | Honest identity, model mode and approach |
| `POST /v1/teardown` | Erase local evaluator state |

`bot.compose(category, merchant, trigger, customer=None, now=...)` is a pure **content** function. `/v1/tick` is the sending-policy boundary. Four-argument offline clock behavior is documented in [COMPATIBILITY](docs/COMPATIBILITY.md).

## Evidence and limits

Actual test logs, historical dataset replay, local HTTP load measurements, and the changed-price transcript are in `reports/`. They are **not** official quality scores, engagement measurements or selection predictions. See [TESTING](docs/TESTING.md).

English, Hindi and Hinglish have controlled realization; other languages currently fall back to English, and some detailed follow-through remains English. One process and one replica are supported. No real messaging, booking, payment, campaign publishing or medicine dispensing integrations exist. The bot says so instead of pretending to execute them.

Read [DEPLOYMENT](docs/DEPLOYMENT.md), [SECURITY](docs/SECURITY.md), [RESEARCH](docs/RESEARCH.md) and [LIMITATIONS](docs/LIMITATIONS.md) before submission. Replace metadata placeholders and understand/customize the code before presenting it as your work.
