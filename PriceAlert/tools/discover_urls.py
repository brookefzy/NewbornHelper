#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.lib.config import load_settings
from tools.lib.openai_web_search import search_product_candidates_with_openai
from tools.lib.sheets_registry import append_review_queue_rows, append_url_candidate_rows, load_products_from_sheet
from tools.lib.url_validator import validate_candidate_url


def _log(message: str, *, enabled: bool = True) -> None:
    if enabled:
        print(message, flush=True)


def _choose_selected_candidate(candidates: list[dict], validations: dict[str, dict]) -> str:
    if not candidates:
        return ""
    scored: list[tuple[int, int, str]] = []
    for candidate in candidates:
        url = str(candidate.get("candidate_url", "")).strip()
        if not url:
            continue
        validation = validations.get(url, {})
        score = int(validation.get("score", 0))
        rank = int(candidate.get("rank", 9999) or 9999)
        scored.append((score, -rank, url))
    if not scored:
        return ""
    scored.sort(reverse=True)
    return scored[0][2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover product URL candidates and write to sheet")
    parser.add_argument("--verbose", action="store_true", help="Print per-product and per-platform progress logs")
    parser.add_argument("--max-candidates", type=int, default=10, help="Maximum candidate URLs per product-platform")
    args = parser.parse_args()

    started = time.time()
    settings = load_settings()
    _log(f"[discover_urls] loading products from worksheet '{settings.products_worksheet_name}'")
    products = load_products_from_sheet(
        service_account_file=settings.google_service_account_file,
        sheet_id=settings.price_sheet_id,
        worksheet_name=settings.products_worksheet_name,
    )
    _log(f"[discover_urls] loaded {len(products)} active products")

    rows = []
    review_rows = []
    total_targets = 0
    completed_targets = 0
    for product in products:
        platforms = list(product.platforms) if product.platforms else [product.platform]
        total_targets += len([p for p in platforms if p])

    for product_index, product in enumerate(products, start=1):
        platforms = list(product.platforms) if product.platforms else [product.platform]
        _log(
            f"[discover_urls] product {product_index}/{len(products)}: {product.product_id} - {product.product_name}",
            enabled=args.verbose,
        )
        for platform in platforms:
            if not platform:
                continue
            target_start = time.time()
            candidates = search_product_candidates_with_openai(
                product={
                    "product_id": product.product_id,
                    "product_name": product.product_name,
                    "brand": product.brand,
                    "platform": platform,
                },
                platform=platform,
                api_key=settings.openai_api_key,
            )
            # Deduplicate and cap candidates per product-platform.
            seen_urls: set[str] = set()
            capped_candidates = []
            for c in candidates:
                url = str(c.get("candidate_url", "")).strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                capped_candidates.append(c)
                if len(capped_candidates) >= max(1, args.max_candidates):
                    break
            candidates = capped_candidates
            completed_targets += 1
            elapsed = time.time() - target_start
            _log(
                f"[discover_urls] target {completed_targets}/{total_targets}: "
                f"{product.product_id} [{platform}] -> {len(candidates)} candidates in {elapsed:.1f}s",
                enabled=True,
            )
            validations_by_url: dict[str, dict] = {}
            for candidate in candidates:
                validation = validate_candidate_url(
                    url=candidate["candidate_url"],
                    platform=platform,
                    product={
                        "product_id": product.product_id,
                        "product_name": product.product_name,
                        "brand": product.brand,
                        "platform": platform,
                    },
                    candidate_title=str(candidate.get("title", "")),
                    candidate_snippet=str(candidate.get("snippet", "")),
                )
                validations_by_url[candidate["candidate_url"]] = validation
            selected_url = _choose_selected_candidate(candidates, validations_by_url)
            for candidate in candidates:
                validation = validations_by_url.get(candidate["candidate_url"], {})
                rows.append(
                    [
                        datetime.now(timezone.utc).isoformat(),
                        product.product_id,
                        platform,
                        candidate["query"],
                        candidate["candidate_url"],
                        candidate["rank"],
                        candidate["candidate_url"] == selected_url,
                        candidate["reason"],
                    ]
                )
                if validation["is_useful"]:
                    review_rows.append(
                        [
                            datetime.now(timezone.utc).isoformat(),
                            product.product_id,
                            platform,
                            candidate["candidate_url"],
                            candidate["query"],
                            candidate["rank"],
                            candidate["reason"],
                            validation["score"],
                            validation["notes"],
                            "",
                        ]
                    )

    _log(
        f"[discover_urls] writing {len(rows)} candidate rows to worksheet '{settings.url_candidates_worksheet_name}'",
        enabled=True,
    )
    append_url_candidate_rows(
        service_account_file=settings.google_service_account_file,
        sheet_id=settings.price_sheet_id,
        rows=rows,
        worksheet_name=settings.url_candidates_worksheet_name,
    )
    _log(
        f"[discover_urls] writing {len(review_rows)} validated rows to worksheet '{settings.approved_urls_worksheet_name}'",
        enabled=True,
    )
    append_review_queue_rows(
        service_account_file=settings.google_service_account_file,
        sheet_id=settings.price_sheet_id,
        rows=review_rows,
        worksheet_name=settings.approved_urls_worksheet_name,
    )
    total_elapsed = time.time() - started
    print(
        json.dumps(
            {"status": "ok", "rows_written": len(rows), "targets": total_targets, "elapsed_seconds": round(total_elapsed, 2)},
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
