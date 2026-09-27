# Known limitations and what remains before final submission

**This is a working candidate codebase—not a certified production service or guaranteed winning entry.**

## Measured versus unmeasured

Unit/integration tests, source-data replay, local HTTP requests and offline UI interactions were executed. Live model-assisted classification, paid quality evaluation, public cloud hosting, GitHub-hosted CI, Docker image builds and the organizer's private evaluation were not executed. A fresh virtual-environment dependency download was attempted but did not complete because index requests timed out; tests used the preinstalled dependency versions recorded in the lock file. The release archive is separately checked after extraction.

## Product quality

A deterministic strategy library can produce generic fallback copy, overly cautious wording, awkward language or irrelevant facts. Factual restraint alone does not establish engagement. Decision priorities are heuristics, not optimized weights. The supplied dataset is sparse and inconsistent; a few send/skip decisions need subjective review. A provenance match does not prove the message is entirely factually or semantically correct.

English, Hindi and Hinglish are covered at a controlled-template level; some detailed follow-through paths remain English. Other requested languages fall back to English. That is a real limitation, not full multilingual support. Ambiguous replies can remain unknown with optional semantic assistance disabled. Unknown trigger kinds do not gain arbitrary new capabilities merely because the API accepts their fields.

Offer restrictions in arbitrary prose are not completely understood. Normalized fields and additional tests are needed beyond the handled weekday/date/audience forms. An offer without a stable ID cannot receive the same robust pending-ID binding as an identified offer. External claims, synthetic clinical studies and regulatory notices are not independently verified.

Imported conversation histories are used for historical STOP, but the code does not semantically understand all prior turns or reconstruct every prior promise. Maximum conversation turns and duplicate-output prevention are blunt controls, not a learned conversation policy.

## Models and evaluation

Optional semantic mode is a Chat Completions JSON-compatible adapter, not guaranteed compatible with every model/provider. Model availability and API behavior must be checked in your account. It has only mock-provider tests so far. Cached classifications stabilize repeat requests, but an empty new cache can yield a different model classification; use default mode for strict fresh-run determinism.

The optional quality script covers outbound messages with full context. It is an independent developmental evaluator, not a replacement for conversation testing, human review, the official simulator or the private judge. No score is included because no real paid judge call was made. It caps calls, not provider billing in currency; configure provider-side spending limits too.

## Operations and security

The app supports one process/replica with a local SQLite file. It is not multi-tenant, does not have a distributed lock service, and lacks global storage quotas or a production rate limiter. Public mode allows untrusted callers to mutate synthetic test state. Host restart resilience depends on actually persistent storage. Idle cleanup cannot remove provider backups or model-provider retention.

The studio's isolated preview does not consult durable recipient STOP/cadence; it labels that limitation. Real delivery decisions must go through `/v1/tick`. Returned actions are instructions to the simulator, not actual WhatsApp delivery. Nothing is booked, paid, dispensed, published or sent externally.

## Before calling the entry ready

Run the package on your own machine; inspect cases; improve weak messages with regression tests; perform a real quality evaluation; test the final public host; resolve storage/retention/authentication with the organizer; fill genuine metadata; and understand the source well enough to explain it honestly.
