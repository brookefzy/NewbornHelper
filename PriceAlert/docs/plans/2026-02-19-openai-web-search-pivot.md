# OpenAI Web Search Pivot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace fragile URL discovery with OpenAI-assisted discovery while keeping price extraction trustworthy through page-level verification and explicit platform strategies.

**Architecture:** Use a hybrid 2-stage path for `target` and `nordstrom`: (1) OpenAI web search finds likely PDP URLs and match evidence, then (2) fetch HTML from the selected URL and extract price from page content using existing parser flow (`extract_with_openai` + guardrails). Do not treat search snippets alone as trusted final price data. Keep `babyletto` and `newtonbaby` deterministic flow unchanged. Keep `approved_urls` as highest-priority source.

**Tech Stack:** Python 3.12, OpenAI Responses API (`web_search`), requests/gspread, pytest + pytest-mock.

## Resolved Design Decisions

1. **Target/Nordstrom extraction mode:** Hybrid, not black-box snippet pricing.
   - OpenAI search is for URL discovery and relevance evidence.
   - Final price must come from fetched page content.
2. **Price trust policy:** Snippet-only price is never `status="ok"`.
   - If no HTML-backed parse succeeds, return `parse_error` with `error="search_price_unverified"`.
3. **Routing pattern:** Use strategy map, not scattered `if/elif` branches.
4. **`discover_urls.py` status:** Keep and migrate to same OpenAI discovery backend as main loop.
5. **Validator scope:** Replace vague "token checks" with explicit sanity checks:
   - allowed domain check
   - product keyword overlap threshold
   - URL path relevance check
6. **Unsupported platforms:** Explicit default behavior (`amazon` included):
   - `status="no_data"`, `error="platform_not_supported"`, `snapshot_status="skip"`.
7. **Budget split:** Separate OpenAI usage categories:
   - `MAX_OPENAI_SEARCH_CALLS` (search/discovery)
   - `MAX_OPENAI_RETAILER_PARSE_CALLS` (target/nordstrom HTML parse)
   - `MAX_OPENAI_FALLBACKS` (legacy fallback for deterministic path)

## Scope

- In scope:
  - OpenAI search for candidate URL discovery in both loop and `discover_urls.py`
  - strategy-based extraction routing
  - HTML-backed final price extraction for `target` and `nordstrom`
  - explicit, testable sanity checks and trust gates
  - explicit unsupported-platform output
- Out of scope:
  - bypassing Amazon anti-bot controls
  - front-end/UI changes in Sheets

### Task 1: Define OpenAI Service Contracts and Mocked Tests First

**Files:**
- Create: `tools/lib/openai_web_search.py`
- Modify: `tools/lib/config.py`
- Test: `tests/test_openai_web_search.py`
- Test: `tests/test_config.py`

**Step 1: Write failing tests (with mocks only)**
- Use `pytest-mock` to mock all OpenAI calls.
- Add tests for `search_product_candidates_with_openai(...)` output schema:
  - `candidate_url`, `title`, `snippet`, `domain`, `match_score`
- Add tests for retailer prompt/response contract used for candidate ranking.
- Add tests for config parsing:
  - `MAX_OPENAI_SEARCH_CALLS`
  - `MAX_OPENAI_RETAILER_PARSE_CALLS`
  - `MAX_OPENAI_FALLBACKS`

**Step 2: Run tests to verify failure**
- Run: `python3 -m pytest -q tests/test_openai_web_search.py tests/test_config.py`
- Expected: FAIL (missing module/settings)

**Step 3: Implement minimal service and schemas**
- Implement `search_product_candidates_with_openai(...)` with retries/timeouts and deterministic normalized output.
- Add explicit query/prompt template for search ranking, including required product+brand terms.
- Add config fields listed above.

**Step 4: Run tests to verify pass**
- Run: `python3 -m pytest -q tests/test_openai_web_search.py tests/test_config.py`
- Expected: PASS

**Step 5: Commit**
```bash
git add tools/lib/openai_web_search.py tools/lib/config.py tests/test_openai_web_search.py tests/test_config.py
git commit -m "feat: define openai search contracts and budgets"
```

### Task 2: Implement Strategy-Based Resolver and Router

**Files:**
- Create: `tools/lib/platform_strategy.py`
- Modify: `tools/lib/price_collectors.py`
- Modify: `tools/run_daily_price_alerts.py`
- Test: `tests/test_platform_strategy.py`
- Test: `tests/test_run_daily_alerts.py`

**Step 1: Write failing tests**
- Add tests for strategy lookup:
  - `babyletto`, `newtonbaby` -> deterministic strategy
  - `target`, `nordstrom` -> hybrid retailer strategy
  - default -> unsupported strategy
- Add tests for source precedence resolver:
  - approved URL first
  - discovery second
  - fallback pattern last

**Step 2: Run tests to verify failure**
- Run: `python3 -m pytest -q tests/test_platform_strategy.py tests/test_run_daily_alerts.py`
- Expected: FAIL

**Step 3: Implement strategy map**
- Add `EXTRACTION_STRATEGIES` dictionary and pure resolver helpers.
- Ensure unsupported strategy returns:
  - `status="no_data"`, `error="platform_not_supported"`, `snapshot_status="skip"`.

**Step 4: Run tests to verify pass**
- Run: `python3 -m pytest -q tests/test_platform_strategy.py tests/test_run_daily_alerts.py`
- Expected: PASS

**Step 5: Commit**
```bash
git add tools/lib/platform_strategy.py tools/lib/price_collectors.py tools/run_daily_price_alerts.py tests/test_platform_strategy.py tests/test_run_daily_alerts.py
git commit -m "refactor: add strategy-based platform routing and resolver"
```

### Task 3: Migrate `discover_urls.py` and Define Sanity Checks

**Files:**
- Modify: `tools/discover_urls.py`
- Modify: `tools/lib/url_validator.py`
- Delete: `tools/lib/product_discovery.py`
- Test: `tests/test_discover_urls.py`
- Test: `tests/test_url_validator.py`

**Step 1: Write failing tests (mocks only)**
- Mock OpenAI search responses and URL fetch calls.
- Validate sanity checks are explicit and deterministic:
  - allowed domain list
  - keyword overlap threshold (product/brand tokens)
  - URL path relevance (`/product`, `/p/`, slug overlap)
- Ensure no dependency on `discover_product_url_candidates(...)` remains.

**Step 2: Run tests to verify failure**
- Run: `python3 -m pytest -q tests/test_discover_urls.py tests/test_url_validator.py`
- Expected: FAIL

**Step 3: Implement migration and cleanup**
- Migrate discovery to `search_product_candidates_with_openai(...)`.
- Apply sanity checks to generate review queue rows.
- Remove old discovery module and imports.

**Step 4: Run tests to verify pass**
- Run: `python3 -m pytest -q tests/test_discover_urls.py tests/test_url_validator.py`
- Expected: PASS

**Step 5: Commit**
```bash
git rm tools/lib/product_discovery.py
git add tools/discover_urls.py tools/lib/url_validator.py tests/test_discover_urls.py tests/test_url_validator.py
git commit -m "refactor: migrate discover_urls to openai search and explicit sanity checks"
```

### Task 4: Implement Hybrid Retailer Extraction (Search -> Fetch -> Parse)

**Files:**
- Modify: `tools/run_daily_price_alerts.py`
- Modify: `tools/lib/price_collectors.py`
- Modify: `tools/lib/extract_with_openai.py`
- Test: `tests/test_run_daily_alerts.py`
- Test: `tests/test_price_collectors.py`
- Test: `tests/test_extract_with_openai.py`

**Step 1: Write failing tests (mocks only)**
- Mock OpenAI search and HTTP HTML fetch.
- Mock OpenAI parse output from `extract_with_openai`.
- Add tests for retailer flow:
  1. OpenAI search returns candidate URL.
  2. Candidate URL HTML fetch succeeds.
  3. Price parse from HTML succeeds -> `status="ok"`.
- Add negative tests:
  - snippet has price but HTML parse fails -> `parse_error`, `error="search_price_unverified"`.
  - OpenAI search empty -> `no_url`/`unresolved_url` behavior.

**Step 2: Run tests to verify failure**
- Run: `python3 -m pytest -q tests/test_run_daily_alerts.py tests/test_price_collectors.py tests/test_extract_with_openai.py`
- Expected: FAIL

**Step 3: Implement hybrid retailer strategy**
- Implement retailer strategy pipeline:
  - search candidates
  - validate candidate relevance
  - fetch selected candidate HTML
  - parse price from HTML
- Keep snapshot semantics explicit:
  - if HTML fetched: normal snapshot status
  - if unsupported platform: `snapshot_status="skip"`
- Never mark snippet-only price as trusted.

**Step 4: Run tests to verify pass**
- Run: `python3 -m pytest -q tests/test_run_daily_alerts.py tests/test_price_collectors.py tests/test_extract_with_openai.py`
- Expected: PASS

**Step 5: Commit**
```bash
git add tools/run_daily_price_alerts.py tools/lib/price_collectors.py tools/lib/extract_with_openai.py tests/test_run_daily_alerts.py tests/test_price_collectors.py tests/test_extract_with_openai.py
git commit -m "feat: implement hybrid openai retailer extraction with html verification"
```

### Task 5: Enforce OpenAI Budgets and Observability

**Files:**
- Modify: `tools/run_daily_price_alerts.py`
- Modify: `tools/lib/config.py`
- Test: `tests/test_run_daily_alerts.py`
- Test: `tests/test_config.py`

**Step 1: Write failing tests**
- Add tests for separate counters and exhaustion behavior:
  - search budget exhausted does not consume parse budget
  - retailer parse budget exhausted does not consume fallback budget
  - fallback budget applies only to deterministic fallback path

**Step 2: Run tests to verify failure**
- Run: `python3 -m pytest -q tests/test_run_daily_alerts.py tests/test_config.py`
- Expected: FAIL

**Step 3: Implement accounting and run summary fields**
- Add summary counters:
  - `openai_search_attempts`, `openai_search_uses`
  - `openai_retailer_parse_attempts`, `openai_retailer_parse_uses`
  - existing fallback counters

**Step 4: Run tests to verify pass**
- Run: `python3 -m pytest -q tests/test_run_daily_alerts.py tests/test_config.py`
- Expected: PASS

**Step 5: Commit**
```bash
git add tools/run_daily_price_alerts.py tools/lib/config.py tests/test_run_daily_alerts.py tests/test_config.py
git commit -m "feat: separate openai search and parse budgets with metrics"
```

### Task 6: Documentation and E2E Verification Update

**Files:**
- Modify: `workflows/price_alert_runbook.md`
- Modify: `docs/plans/2026-02-18-price-alert-automation.md`

**Step 1: Update runbook details**
- Document hybrid retailer flow and trust policy:
  - search discovers URL
  - HTML parse confirms price
  - snippet-only is untrusted
- Document strategy map and unsupported platform behavior.
- Document explicit sanity checks and mock-only unit-test policy.

**Step 2: Update verification sequence**
1. `python3 -m pytest -q`
2. `python3 tools/discover_urls.py --max-candidates 10`
3. Human review in `approved_urls` (`approval=TRUE/FALSE`)
4. `python3 tools/run_daily_price_alerts.py --dry-run`
5. Validate `/Users/yuan/Dropbox (Personal)/Personal Work/_Projects2025/MumHelper/PriceAlert/.tmp/latest_run.json`

Expected indicators:
- no snippet-only `status="ok"` retailer prices
- explicit unsupported platform rows (`platform_not_supported`)
- separate OpenAI search/parse counters

**Step 3: Mark older plan superseded**
- Add top-note link in `docs/plans/2026-02-18-price-alert-automation.md`.

**Step 4: Commit**
```bash
git add workflows/price_alert_runbook.md docs/plans/2026-02-18-price-alert-automation.md docs/plans/2026-02-19-openai-web-search-pivot.md
git commit -m "docs: harden openai hybrid extraction design and test policy"
```
