# Test evidence and reproduction

## Actual execution

The final suite executed **190 tests with 0 failures and 0 errors** on Linux / Python 3.13.5. Combined statement-and-branch coverage reported by coverage.py is **85.2%**. Coverage is not a correctness or security guarantee.

| Check | Observed result |
|---|---|
| Automated suite | 190 passed |
| Expanded dataset | 5 categories, 50 merchants, 200 customers, 100 triggers across 26 kinds |
| Independent scenario replay | 74 sends; 26 abstentions |
| Recorded source-value mismatches | 0 |
| Local mixed HTTP workload | 120 requests, target 10 requests/sec, all HTTP 200 |
| Local HTTP p95 / maximum | 5.179 ms / 91.580 ms |
| Real paid model calls | 0 |
| Original starter files preserved | 16, byte-for-byte |

The dataset replay evaluates each trigger independently at an explicit historical time. It does not mean the bot sends 74 messages in one stateful test window, and abstentions are not scored as automatic successes. Pure-compiler microsecond/millisecond timings exclude HTTP and database overhead. The HTTP workload is small, local, default mode, and not a capacity test or public-host SLA.

## What the suite checks

HTTP version replacement, same-version no-op and stale-version conflict; body/schema limits; concurrent duplicate prevention; recipient ownership; future/expired triggers; explicit consent, STOP and cooldown; delayed/automatic/hostile replies; commitment-to-action transitions; up-to-date prices; removed/reordered offer IDs; changed digests; basic injection-like content; date labels derived from ISO; English/Hindi/Hinglish examples; recorded evidence snapshots; strict quality-score parsing; optional-provider timeout/failure behavior; protected preview; and original seed cases exercised through HTTP with follow-through and retries.

Some original seed cases correctly abstain. Tests assert explicit skip traces and response consistency; they do not confer a writing score. See `tests/test_seed_roundtrips.py` for the exact assertions.

## Reproduce

```bash
python -m pytest --cov=vera --cov-report=term-missing --cov-report=json:reports/coverage.json
python vendor/magicpin/dataset/generate_dataset.py --seed-dir vendor/magicpin/dataset --out expanded
python -m scripts.evaluate --dataset expanded
```

With a separate local server running:

```bash
python -m scripts.demo --reset
python -m scripts.preflight
python -m scripts.load_test --requests 120 --rate 10
```

Do not run reset or load scripts against an active judge session. The recorded HTTP run used local port 8765 because port 8080 was already occupied; pass the matching `--url` to reproduce on that port.

## Browser verification

Chromium/Playwright executed the actual studio JavaScript with a mocked `fetch` transport connected to the real FastAPI TestClient. It checked price changes, revoked consent, operational messaging, protected traces and mobile overflow; no JavaScript errors occurred. Screenshots are in `reports/studio-desktop.png` and `reports/studio-mobile.png`.

Direct browser navigation to localhost was blocked by the authoring environment, so this was an **offline browser interaction test**, not a deployed-browser-network test. Local HTTP behavior was tested independently with HTTPX. `scripts/browser_check.py` reproduces the offline test with an explicitly installed Playwright and Chromium; they are optional and not server dependencies.

## Raw reports

`tests-final.txt` and `pytest.xml`: actual assertions and results. `coverage.json`: measured source coverage. `dataset-evaluation.json`: every case, reason, body and source ledger. `http-load.json`: measured local HTTP responses. `demo-transcript.json`: exact real HTTP requests/responses for changed-price, acceptance and STOP. `browser-check.json`: UI method, checks and environment limitation. `source-manifest.json`: original source hashes. `installation-status.json`: unsuccessful fresh dependency-download attempt.

## Not established by this package

No live LLM judge score, hidden-test result, human engagement data, win probability, public deployment, remote CI result, Docker build, stress-capacity bound or multi-host correctness is reported. A clean package-index install was attempted but timed out; dependency versions match the preinstalled environment and are recorded, not claimed freshly downloaded. Perform these remaining checks on your own machine and chosen host.
