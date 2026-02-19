# Price Alert Automation Implementation Plan

> Superseded on 2026-02-19 by `docs/plans/2026-02-19-openai-web-search-pivot.md`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a daily 7:00 AM system that reads baby products from Google Sheets, discovers candidate product URLs per platform via Google Programmable Search API, extracts prices/coupons from saved HTML (deterministic first, OpenAI fallback), and emails a professional digest to `yuanzfan16@gmail.com`.

**Architecture:** A staged pipeline:
1) registry read, 2) multi-query URL candidate discovery (Google CSE primary), 3) HTML snapshot caching, 4) deterministic extraction with LLM fallback, 5) alerting and Gmail digest.
All intermediate evidence is persisted for debug (`url_candidates` sheet + `.tmp/html` snapshots + `.tmp/latest_run.json`).

**Tech Stack:** Python 3, `pytest`, Google Sheets API (`gspread` + service account), Gmail API (`google-api-python-client`, OAuth desktop flow), `requests`, optional `playwright`, OpenAI API (fallback extractor).

## Assumptions
- Product sheet ID: `1qExKo8CK7m6bedBHRvmv-maja2bxRuy3dSQHQYxXAms`.
- Product worksheet name is `products`.
- URL candidate worksheet name is `url_candidates`.
- History worksheet name is `price_history`.
- Gmail sender uses `/Users/yuan/Dropbox (Personal)/Personal Work/_Projects2025/MumHelper/PriceAlert/client_secret_desktop.json`.
- Service account file remains `/Users/yuan/Dropbox (Personal)/Personal Work/_Projects2025/MumHelper/PriceAlert/google_drive_personal.json`.
- OpenAI key for extraction fallback is available via env (e.g., `OPENAI_API_KEY`).
- Google CSE credentials available via env:
  - `GOOGLE_CSE_API_KEY`
  - `GOOGLE_CSE_ID`

## Product Schema (Updated)
- `products` columns:
  - `product_id`
  - `product_name` (full model name)
  - `brand` (normalized, e.g., `Babyletto`, `Newtonbaby`, `UPPAbaby`)
  - `platform` (comma-separated list, e.g., `babyletto,target,amazon,nordstrom`)
  - `product_url` (optional canonical URL; blank allowed)
  - `baseline_price`
  - `target_price`
  - `significant_drop_pct`
  - `active`

## Revised Execution Tasks

### Task A: Normalize Registry + Platform Expansion
**Files:**
- Modify: `tools/lib/sheets_registry.py`
- Modify: `tests/test_sheets_registry.py`

**Implement:**
- parse comma-separated `platform` into normalized platform list
- keep backward compatibility when a single platform value is provided
- allow numeric and empty cells safely

### Task B: URL Candidate Collection Stage
**Files:**
- Modify: `tools/lib/product_discovery.py`
- Create: `tools/discover_urls.py`
- Create: `tests/test_product_discovery.py`

**Implement:**
- for each product + platform, generate 2-4 recall-oriented queries
- collect top candidate URLs with Google CSE (primary)
- keep fallback behavior when CSE is unavailable/missing credentials
- write candidate rows to `url_candidates` sheet:
  - `run_ts, product_id, platform, query, candidate_url, rank, selected, reason`
- if `product_url` blank, select best candidate automatically and keep evidence in candidate sheet

### Task C: HTML Snapshot Caching
**Files:**
- Create: `tools/lib/page_snapshots.py`
- Create: `tests/test_page_snapshots.py`

**Implement:**
- fetch chosen URL and persist HTML under:
  - `.tmp/html/<product_id>/<platform>.html`
- return snapshot metadata (`path`, `url`, `fetched_at`, `status_code`)
- do not overwrite successful recent snapshot in same run

### Task D: Deterministic Price/Coupon Extraction
**Files:**
- Modify: `tools/lib/price_collectors.py`
- Modify: `tools/lib/coupon_finder.py`
- Create: `tests/test_price_collectors.py`
- Create: `tests/test_coupon_finder.py`

**Implement:**
- extract from JSON-LD (`Offer.price`), meta tags, known selectors, regex fallback
- domain-specific hints for `babyletto.com`, `newtonbaby.com`, `uppababy.com`, `target.com`, `amazon.com`, `nordstrom.com`
- output strict result with evidence fields:
  - `status, current_price, currency, confidence, evidence_text, evidence_url, error`

### Task E: OpenAI Fallback Extractor
**Files:**
- Create: `tools/lib/extract_with_openai.py`
- Create: `tests/test_extract_with_openai.py`

**Implement:**
- invoke OpenAI only when deterministic extraction returns `parse_error`
- send trimmed HTML/text blocks, not full page where possible
- require strict JSON response schema
- store fallback reason and confidence in run artifact

### Task F: Orchestrator Update (Stage-by-Stage)
**Files:**
- Modify: `tools/run_daily_price_alerts.py`
- Modify: `tests/test_run_daily_alerts.py`

**Pipeline:**
1. load settings  
2. read products  
3. expand product-platform targets  
4. discover/write URL candidates  
5. choose URL per target  
6. snapshot HTML  
7. deterministic extract price + coupon  
8. OpenAI fallback when needed  
9. compute alerts vs baseline/target  
10. append `price_history`  
11. email digest  
12. write detailed `.tmp/latest_run.json`

### Task G: Runbook and Operational Controls
**Files:**
- Modify: `workflows/price_alert_runbook.md`

**Add:**
- new sheet schema and `url_candidates` contract
- debug playbook for `unresolved_urls`, `no_data`, low-confidence extractions
- cost guardrails for OpenAI fallback (only on failures; max retries; per-run cap)

## Revised Done Criteria
- `platform` list per row is fully supported.
- `product_url` can be blank and still produce candidate URLs.
- `url_candidates` sheet is populated each run with evidence.
- HTML snapshots are saved for inspected targets.
- deterministic extraction succeeds for a meaningful subset; OpenAI fallback handles residual failures.
- digest includes only confident alerts and links to source URLs.
