# Challenge contract interpretations

Sources: the live challenge page and the unchanged testing brief under `vendor/magicpin`. The starter examples disagree in several places; these choices are explicit, not organizer confirmation.

| Topic | Implemented behavior |
|---|---|
| Submission | Public base URL exposing five `/v1` endpoints; pure composer retained internally |
| Equal version | Successful no-op with prior acknowledgement; only lower versions conflict |
| Context updates | Higher version replaces full snapshot atomically, rather than merging stale fields |
| Primary IDs | Envelope fills an omitted root ID; conflicting root/envelope IDs fail |
| Trigger recipients | Top-level or payload IDs accepted; conflicting duplicates fail |
| Reply IDs | May be resolved from a known conversation; unknown conversation needs explicit identity |
| Reply timestamps | `received_at` remains required by the formal contract despite shortened webpage examples |
| Time budget | Default engine is local; optional semantic call has a three-second total deadline and fallback |
| Tick response | At most 20 actions; one per recipient; zero is legitimate when no action is eligible |
| Template fields | Logical template name/parameters are returned; this does not claim Meta approval or sending |
| URLs | No invented links; source references can be textual. Source lookup currently does not browse externally |
| New payload fields | Preserved. Known wrong shapes fail closed; unfamiliar semantics are not automatically understood |
| Teardown | Optional extra `/v1/teardown`, implemented as complete local test-state clearing |
| Identity | Solo applicant metadata must be filled by the user; placeholder defaults prevent accidental impersonation |

## `compose()` versus `/v1/tick`

The pure function returns `body`, `cta`, `send_as`, `suppression_key`, `rationale`. Pass `now=` for reproducible time-sensitive composition. Without it, the compatibility function uses observed/created time, a dated payload event, or expiry minus one day. This is a documented historical-fixture convention, not an assertion of the current date. It raises when no deterministic clock is possible.

Pure composition does **not** apply durable suppression, recipient STOP or cadence. The real judging route `/v1/tick` applies those and uses its supplied `now`. Do not expose the pure composer as an alternative delivery API.

## Concurrency, histories and fresh data

The runtime does not import vendor data or memorize its IDs. Sources pushed mid-run are used by subsequent ticks and replies. Pending actions refer to current offers by ID where available. Historical merchant STOP turns are read when pushed; more general imported history is not a full semantic memory system. Customer settings, channel and consent govern outreach independently.

Some restrictions in free-text offer titles are recognized (weekday ranges, named days, weekends, new-customer language). Arbitrary natural-language contracts are not fully parsed. Production use should require normalized validity fields and structured offer eligibility.

## Local simulator caution

The supplied simulator's default combined scenario omits outbound quality scoring. Some checks print a failure but still return success, customer contexts are omitted from its full path, and malformed score responses can yield heuristic scores. Its current-wall-clock ticks also conflict with old fixture dates. These observations were established in the preceding audit and can be inspected directly in `vendor/magicpin/judge_simulator.py`.

This is not a claim that the private judge shares every defect. Use real quality review and independent behavioral tests. Never intentionally exploit a scorer's missing context or fallback behavior.
