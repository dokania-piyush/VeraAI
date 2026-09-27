# Deeper research and implementation decisions

**Checked 27 September 2026.** Public primary sources and the user-supplied starter kit informed the design. This is an engineering interpretation, not organizer endorsement, a private-judge audit or a novelty claim.

## 1. Optimize changing decisions, not a gallery of memorized messages

The live challenge asks for a deterministic composer and a stateful public API. It emphasizes fresh contexts and replay scenarios. Therefore the server starts empty; it uses pushed snapshots, stable IDs, independent consent state, and a remembered next action. The demo changes a price after an invitation and before acceptance to test adaptation.

Source: https://partners.magicpin.com/vera/ai-challenge

## 2. Structured model output is not a factuality guarantee

OpenAI's structured-output guidance distinguishes schema compliance from correctness and notes that outputs can still contain mistakes. A valid JSON price can still belong to the wrong merchant. Default Compass instead compiles facts from scoped fields. Optional model use is limited to uncertain reply intent, and JSON is validated even then.

Source: https://developers.openai.com/api/docs/guides/structured-outputs

This choice sacrifices some open-ended language flexibility. It needs empirical copy-quality evaluation rather than a claim that rules automatically beat an LLM.

## 3. Limit authority, not just prompt wording

OWASP describes instruction/data confusion and recommends layered defenses. The model here cannot execute business tools, change suppression state, choose arbitrary external URLs or invent a message body. Even a wrong intent only selects one of the app's bounded response behaviors. Heuristic suspicious-text detection is not treated as a proof of safety.

Source: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html

## 4. A timeout needs to cover the whole operation

HTTPX documents separate connect/read/write/pool timeouts. A per-phase value is not the same as an end-to-end response deadline. The optional intent request therefore uses an outer async deadline as well as HTTPX timeouts, has no automatic retry loop, and falls back to deterministic handling. The included slow-provider mock verifies cancellation.

Source: https://www.python-httpx.org/advanced/timeouts/

## 5. Prefer simple local transactions to unnecessary distributed machinery

SQLite serializes writers; explicit short transactions can safely bind a chosen action to its suppression receipt and pending state on one host. The implementation avoids holding this transaction while waiting for a provider. One process/replica is the supported operating model, not a hidden horizontal-scaling promise.

Sources: https://www.sqlite.org/lang_transaction.html and https://sqlite.org/isolation.html

A current SQLite WAL document also records a WAL-reset bug fixed in 3.51.3, with specified backports. The authoring runtime's SQLite was older. Rather than depending on unspecified host patch levels, this candidate deliberately uses rollback-journal mode. This is a scoped deployment decision, not a general statement that WAL is unsafe or slower.

Source: https://sqlite.org/wal.html

## 6. Availability and retention can pull in opposite directions

Render documents straightforward FastAPI deployment, but free-instance idle behavior can introduce startup delays and erase ephemeral state. Persistent disks solve restart loss but add automatic retained snapshots. A code-level `teardown()` cannot delete copies retained by the host. Deployment recipes expose that tradeoff rather than silently picking one and claiming both perfect durability and immediate deletion.

Sources:
- https://render.com/docs/deploy-fastapi
- https://render.com/docs/free
- https://render.com/docs/disks
- https://render.com/docs/blueprint-spec

## 7. The starter is training material, not a ground-truth oracle

The previous audit found missing checks in the default local harness, inconsistent equal-version examples, old fixture dates, sparse generated triggers and unsupported details in “good” example messages. The original files are retained unchanged in `vendor/magicpin`. The independent suite tests actual HTTP and state behavior; the optional quality reviewer fails on malformed scores instead of synthesizing a neutral number.

Important distinction: this does not establish how the private evaluation will behave. No private judge access, hidden tests or organizer score were available.

## 8. What would most improve the next iteration?

The strongest next evidence is an honest evaluation of copy quality on unfamiliar contexts, not more UI features. Review messages with actual merchants or a clearly labeled independent judge, classify each failure, and add holdout cases before changing wording. Prioritize better category-specific follow-through, ambiguous intent, regional languages, nuanced offer eligibility and useful opportunity recall.

No claim is made that the present entry is globally unique, the highest scoring, or certain to be selected. Its differentiator is inspectable behavior: facts, restraint and follow-through shown by executable tests.
