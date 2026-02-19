# Price Alert Workflow

## Objective
Track baby product prices across supported shopping platforms, compare against baseline and target values, collect sign-up coupon opportunities, and send a daily email digest with explicit trust policy.

## Inputs
- Google Sheet ID: `1qExKo8CK7m6bedBHRvmv-maja2bxRuy3dSQHQYxXAms`
- Worksheet `products` with columns:
  - `product_id`
  - `product_name`
  - `brand`
  - `platform` (comma-separated list, e.g. `babyletto,target,amazon,nordstrom`)
  - `product_url` (optional; auto-discovered via web search when blank)
  - `baseline_price`
  - `target_price`
  - `significant_drop_pct`
  - `active`
- Worksheet `url_candidates` for URL discovery evidence:
  - `run_ts, product_id, platform, query, candidate_url, rank, selected, reason`
- Worksheet `approved_urls` (human review queue + approvals):
  - `run_ts, product_id, platform, approved_url, query, rank, source_reason, validator_score, validator_notes, approval`
  - validator writes candidate rows with blank `approval`
  - human reviewer sets `approval=TRUE` to approve, `FALSE` to reject
- Worksheet `price_history` for append-only run history rows
- Environment variables:
  - `PRICE_SHEET_ID`
  - `GOOGLE_SERVICE_ACCOUNT_FILE`
  - `GMAIL_OAUTH_CLIENT_FILE`
  - `GMAIL_TOKEN_FILE`
  - `ALERT_RECIPIENT_EMAIL`
  - `OPENAI_API_KEY` (or legacy `OPEN_API_KEY`) for search discovery and parse fallbacks
  - `MAX_OPENAI_SEARCH_CALLS` (default `15`)
  - `MAX_OPENAI_RETAILER_PARSE_CALLS` (default `10`)
  - `MAX_OPENAI_FALLBACKS` (default `5`)
  - optional worksheet overrides:
    - `PRODUCTS_WORKSHEET_NAME`
    - `URL_CANDIDATES_WORKSHEET_NAME`
    - `APPROVED_URLS_WORKSHEET_NAME`
    - `PRICE_HISTORY_WORKSHEET_NAME`

## Tools to Run
- `tools/run_daily_price_alerts.py` (main pipeline)
- `tools/discover_urls.py` (URL-candidate collection only)
- `tools/check_price.py` (single-product diagnostic)
- `tools/send_price_digest.py` (email-only utility)

## Daily Execution Flow
1. Load pipeline settings from environment variables.
2. Read active products from worksheet `products`.
3. Expand each product into per-platform targets using the comma-separated `platform` list.
4. Resolve extraction strategy by platform:
   - `babyletto`, `newtonbaby` -> `deterministic`
   - `target`, `nordstrom` -> `hybrid_retailer`
   - default (including `amazon`) -> unsupported
5. Discover URL candidates with OpenAI web search (subject to `MAX_OPENAI_SEARCH_CALLS`) and write evidence rows to `url_candidates`.
6. Auto-validate candidates with explicit sanity checks:
   - allowed domain check
   - keyword overlap threshold (brand/product tokens)
   - URL path relevance check
7. Write filtered useful candidates into worksheet `approved_urls` for human review (`approval` left blank).
8. For downstream pricing:
   - if an approved row exists (`approval=TRUE`) for `product_id + platform`, use that URL
   - otherwise continue with existing pipeline (use product/discovery selection)
9. Save HTML snapshots to `.tmp/html/<product_id>/<platform>.html` when URL is resolved.
10. Extract prices:
   - deterministic path for deterministic strategy
   - hybrid strategy for `target`/`nordstrom`: search -> fetch HTML -> parse from HTML
11. Trust gate: snippet-only price is never trusted. If search snippet contains a price but HTML parse fails, return `parse_error` with `error=search_price_unverified`.
12. Use retailer parse budget (`MAX_OPENAI_RETAILER_PARSE_CALLS`) only for hybrid HTML parse attempts.
13. Use legacy OpenAI fallback budget (`MAX_OPENAI_FALLBACKS`) only for deterministic path.
14. Unsupported platforms return `status=no_data`, `error=platform_not_supported`, `snapshot_status=skip`.
15. Compute alert categories (`SIGNIFICANT_DROP`, `TARGET_REACHED`, `NO_DATA`).
16. Append run records to worksheet `price_history`.
17. Render HTML digest and send one email.
18. Save run summary JSON to `.tmp/latest_run.json`.

## Expected Output
- Email digest sections:
  - Top Significant Drops
  - Full tracked item table (current/baseline/target)
  - Coupon opportunities
- JSON summary in `.tmp/latest_run.json`:
  - `processed`
  - `alerts`
  - `coupons`
  - `url_candidates`
  - `openai_fallback_uses`
  - `openai_search_attempts`
  - `openai_search_uses`
  - `openai_retailer_parse_attempts`
  - `openai_retailer_parse_uses`
  - `generated_at`

## Operations Checklist
- First run checklist (cold start):
  - run `python3 tools/discover_urls.py` first to populate `url_candidates` and `approved_urls`
  - review `approved_urls` and set `approval=TRUE` for trusted PDP rows
  - run `python3 tools/run_daily_price_alerts.py --dry-run`
- OAuth bootstrap:
  - `python3 tools/send_price_digest.py --recipient yuanzfan16@gmail.com --client-secret client_secret_desktop.json --token-file gmail_token.json --bootstrap-oauth`
- Dry run:
  - `python3 tools/run_daily_price_alerts.py --dry-run`
- URL discovery only:
  - `python3 tools/discover_urls.py --max-candidates 10`
- Review queue cleanup:
  - `python3 tools/cleanup_approved_urls.py --dry-run`
  - `python3 tools/cleanup_approved_urls.py`
- Daily automation schedule:
  - 7:00 AM local time
- Google Sheet sharing:
  - Share sheet with service account email from `google_drive_personal.json`

## Failure Handling
- Price fetch errors:
  - status is marked `fetch_error`; pipeline continues for other products.
- Parse errors:
  - status is marked `parse_error`.
  - snippet-only hybrid result is downgraded to `error=search_price_unverified`.
  - deterministic path may attempt OpenAI fallback before marking `NO_DATA`.
- Unsupported platforms:
  - status is marked `no_data` with `error=platform_not_supported` and snapshot skipped.
- URL discovery misses:
  - inspect `url_candidates` rows and adjust brand/product naming or platform list.
  - verify OpenAI key is set and search budget is not exhausted.
  - optionally copy vetted PDP links into `approved_urls` and set `active=TRUE`.
- Sheets auth/share errors:
  - verify service account has access and `GOOGLE_SERVICE_ACCOUNT_FILE` is valid.
- Gmail OAuth errors:
  - re-run OAuth bootstrap and confirm `client_secret_desktop.json` uses desktop app credentials.

## Verification Sequence
1. `python3 -m pytest -q`
2. `python3 tools/discover_urls.py --max-candidates 10`
3. Human review in `approved_urls` (`approval=TRUE/FALSE`)
4. `python3 tools/run_daily_price_alerts.py --dry-run`
5. Validate `.tmp/latest_run.json` includes:
   - no snippet-only `status=ok` for hybrid retailers
   - explicit `platform_not_supported` rows for unsupported platforms
   - separate OpenAI search/retailer-parse/fallback counters
