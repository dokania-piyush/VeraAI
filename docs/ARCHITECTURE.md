# Architecture and code walkthrough

## One request, four contexts, one useful action

```text
Judge HTTP request
    |
    v
api.py: body limit, authentication policy, schema validation
    |
    v
service.py: current snapshot + separate recipient/conversation state
    |
    +--> policy.py: identity, consent, expiry, quiet hours, offer restrictions
    |
    +--> composer.py / strategies.py: candidate actions + deterministic ranking
    |       |
    |       +--> evidence.py: supplied source paths and derived calculations
    |       +--> language.py: category-aware greeting and controlled realization
    |
    v
Atomic SQLite write: suppression receipt, pending action, conversation, trace
    |
    v
JSON action returned to the judge (NOT sent to WhatsApp)
```

## Modules

`api.py` owns the HTTP boundary. It limits actual received bytes, returns validation errors without echoing payloads, exposes the five required routes and teardown, and protects the debug API separately. `/debug/preview` runs on supplied what-if context without modifying real state.

`service.py` is the orchestration layer. A context update replaces one full snapshot at a strictly higher version. Repeated versions return the prior acknowledgement; stale versions return 409. The API fills the primary ID from the context envelope when omitted, but rejects conflicting IDs.

`policy.py` applies rules before message generation. A customer must belong to the merchant, have usable consent for the trigger, use a supported channel and not be revoked. Offer titles and explicit fields constrain validity. A category offer catalog is never treated as that merchant's approved price.

`strategies.py` builds deterministic candidate next actions. Critical operational notices, a requested plan, review-service problems, performance checks, growth offers, knowledge and curiosity have different documented utility priorities. These are hand-written product heuristics, **not learned engagement probabilities or judge scores**. One recipient gets at most one selected action per tick; the global cap is 20. Small within-composition diversity adjustments do not overrule high-priority needs. These tradeoffs can miss useful opportunities and need quality review.

`evidence.py` records source scope, field path, value and available version. Derived values record their input paths. Deep copies prevent later in-memory mutations from silently changing recorded evidence. Its verification checks value correspondence, not whether a source was truthful or whether every possible semantic implication of the final sentence is valid. The ledger can include evidence for considered alternatives, not only the selected sentence.

`conversation.py` separates a reply's intent from the action to fulfill. A price question does not destroy a previously promised draft. A subsequent “yes” fulfills it. Pending offer actions bind the offer's ID, not its list position; a new price under the same ID is used, but a removed offer is not replaced with an unrelated offer. Drafting is real; booking, dispensing, payment and publication are not capabilities.

`semantic.py` is optional. It receives only an otherwise-unrecognized reply, asks an explicitly configured LLM for a closed intent label, and validates confidence and an exact evidence substring. It has no tools, no access to arbitrary URLs, no authority to clear STOP, and no power to author business facts. The reply itself can contain personal information: enabling this mode is a data-sharing decision. It is off by default.

## Durable state versus replaceable context

SQLite tables separate `contexts`, `conversations`, `recipients`, `suppression`, `replies`, `receipts`, `traces`, `semantic` and `meta`. This prevents a merchant snapshot replacement from erasing a previously observed STOP. Opt-out is scoped to a merchant/customer pair; a customer's STOP does not block unrelated customers.

Writes use a local SQLite rollback journal, `synchronous=FULL` and short serialized `BEGIN IMMEDIATE` transactions. Network/model calls are deliberately outside the transaction. After an optional model request, current contexts and recipient state are read again before writing a reply.

This design supports **one process and one replica on local storage**. It is not a distributed database architecture. Scaling out requires a proper shared transactional store, leases/idempotency decisions and new concurrent integration tests—not increasing Uvicorn worker count blindly.

## Retry and exactly-once boundaries

Ordinary repeated ticks are suppressed by recipient + suppression key. An explicit `Idempotency-Key` extension returns the original response for the same request and rejects reuse with different request content. A delivery adapter must deduplicate that repeated response by conversation ID; no HTTP service alone guarantees exactly-once delivery to WhatsApp.

A repeated conversation turn with the same message/identity returns the stored response. A conflicting reuse of that turn number returns 409. STOP is honored even if its turn number is older, unless it conflicts with an already recorded different message at that exact turn. This is a deliberate safety preference.

## Clocks

Wall clock measures local retention, liveness and uptime. Judge-supplied timestamps determine campaign applicability, offer validity, cooldown and conversation chronology. Dates and slot weekdays are rendered from ISO values in `Asia/Kolkata`, not trusted text labels.

A standalone four-argument `compose()` needs a deterministic reference clock even though the old interface omits `now`. It derives one from dated fixture fields as documented in COMPATIBILITY. That convenience function does not decide permission to send. Use `/v1/tick` for scheduling decisions.

## Retention

Explicit teardown clears all tables and vacuums the SQLite file. Idle cleanup also clears test state after the configured interval. It runs on startup, health checks, requests and a minute-interval maintenance task. Active traffic keeps the session alive. This is idle-session retention, **not a per-row maximum age** or guaranteed forensic erasure. Host snapshots, provider logs and external model retention need separate controls.
