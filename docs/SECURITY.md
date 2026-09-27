# Security and privacy boundaries

## Threat model

Inputs include arbitrary supplied merchant/customer snapshots and reply text. They may be malformed, contradictory, malicious or contain instruction-like strings. An unknown sender may reach an unauthenticated public challenge endpoint. Optional model providers can fail, delay responses or return a wrong intent.

The application is designed for **synthetic challenge data**. Do not use it with real customer records or real messaging without authentication, authorization, tenant isolation, a delivery adapter, security review and a lawful data-handling design.

## Implemented controls

HTTP envelopes reject unknown keys and wrong types; nested JSON depth, finite numbers and body size are constrained. Recipient identities must agree across contexts and known conversations. SQLite uses bound parameters. Customer consent scope, revocation, delay, cooldown, expiry and offer restrictions are checked before proactive output. STOP is durable independently of replaceable context.

Untrusted factual fragments are not executable prompts in default mode. The optional classifier receives a closed task, validates its output and cannot call tools, author facts or remove suppressions. Regex filters are only an extra check; **there is no claim of complete prompt-injection detection**. Source text can still be wrong, and a model can misclassify a cleverly phrased reply.

Debug APIs require a separate bearer secret, disabled when unset. Studio credentials live only in the current browser tab; no browser local storage or analytics SDK is used. Dynamic DOM values use `textContent`, not HTML interpolation. Studio uses only local assets. Swagger's `/docs` uses FastAPI's standard external assets and a separately relaxed CSP; it does not embed loaded customer contexts.

The network client does not follow redirects or inherit proxy settings. LLM calls have a total deadline, a small concurrency limit and a session call budget; no retry storm occurs. The whole-model callback is outside database transactions. There is no runtime browsing, messaging, shell execution or file-upload tool for the model.

## Explicit gaps and tradeoffs

The challenge's public contract does not specify authentication negotiation. Leaving `VERA_API_TOKEN` blank means strangers can alter synthetic contexts, consume resources and call teardown. A random/unguessable URL is not authentication. Enable bearer authentication only when the judge can supply it, or obtain an approved network access-control arrangement. Do not silently lock the judge out or pretend the public mode is production-secure.

There is a context-count cap and a rolling trace cap, but conversation/suppression/reply tables are retained for the session and do not implement a global byte quota. The host must constrain CPU, memory, storage and request floods. SQL serialization supports the specified small workload, not arbitrary hostile traffic. Health/read paths and large batches can still consume work.

SQLite is not application-encrypted. `secure_delete`, table clearing and VACUUM reduce local residual data but are not forensic-erasure guarantees. Provider snapshots, filesystem history, external monitoring, crash dumps and model-provider retention are outside the database's control. Never use an automatic-backup configuration while claiming immediate end-to-end deletion.

Optional classification sends reply text to the configured commercial provider. A reply may itself contain personal information even though full account snapshots are not sent. The separate quality-review script sends complete synthetic case context and is explicitly opt-in. Use appropriate provider controls before either mode sees non-synthetic data.

There is no automatic re-opt-in workflow: STOP remains until a test teardown/new run. A production reconsent flow needs explicit evidence, policy and tests; a newer snapshot alone must not override it.

Primary guidance reviewed: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
