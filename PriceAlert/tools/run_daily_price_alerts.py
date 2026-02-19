#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.lib.alert_engine import categorize_alert
from tools.lib.config import load_settings
from tools.lib.coupon_finder import find_signup_coupon
from tools.lib.email_renderer import render_digest_html
from tools.lib.extract_with_openai import extract_price_and_coupon_with_openai
from tools.lib.gmail_sender import get_gmail_service, send_html_email
from tools.lib.page_snapshots import snapshot_page
from tools.lib.platform_strategy import resolve_extraction_strategy, unsupported_platform_result
from tools.lib.price_collectors import collect_price, has_snippet_price_signal
from tools.lib.openai_web_search import search_product_candidates_with_openai
from tools.lib.sheets_registry import (
    ProductRecord,
    append_price_history_rows,
    append_url_candidate_rows,
    apply_missing_baseline_updates,
    build_missing_baseline_updates,
    load_products_from_sheet,
    load_approved_urls,
    upsert_best_price_flags,
)
from tools.lib.url_rules import is_listing_or_search_url, is_platform_product_url, product_tokens

MIN_CONFIDENCE_FOR_DIRECT_USE = 0.6
OUTLIER_BASELINE_RATIO_MIN = 0.5


def _is_likely_product_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    if not lowered:
        return False
    blacklist_fragments = [
        "/search",
        "?q=",
        "&q=",
        "searchterm=",
        "keyword=",
        "/sr?",
        "/s?",
        "?k=",
        "/s?k=",
    ]
    return not any(fragment in lowered for fragment in blacklist_fragments)


def _candidate_score(url: str, tokens: set[str]) -> int:
    parsed = urlparse(url)
    host_path = f"{parsed.netloc}{parsed.path}".lower()
    return sum(1 for token in tokens if token in host_path)


def _load_snapshot_html(snapshot_meta: dict) -> str:
    if snapshot_meta.get("status") != "ok":
        return ""
    path = str(snapshot_meta.get("path", "")).strip()
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def _has_price_signal(html: str) -> bool:
    if not html:
        return False
    if re.search(r'product:price:amount" content="([0-9][\d,.]*)"', html, flags=re.IGNORECASE):
        return True
    if re.search(r"[$£€]\s*([0-9][\d,]*(?:\.\d{2})?)", html):
        return True
    return False


def _html_token_match_count(html: str, tokens: set[str]) -> int:
    if not html or not tokens:
        return 0
    lowered = html.lower()
    return sum(1 for token in tokens if token in lowered)


def _select_validated_candidate_url(
    candidates: list[dict],
    product: dict,
    platform: str,
    snapshot_fn,
) -> str:
    tokens = product_tokens(product)
    product_id = str(product.get("product_id", "")).strip()
    if not product_id:
        return ""
    for row in candidates:
        url = str(row.get("candidate_url", "")).strip()
        if not url:
            continue
        if not is_platform_product_url(platform, url):
            continue
        snapshot_meta = snapshot_fn(url, product_id, platform)
        html = _load_snapshot_html(snapshot_meta)
        if not html:
            continue
        if _html_token_match_count(html, tokens) < 2:
            continue
        if not _has_price_signal(html):
            continue
        return url
    return ""


def _is_platform_host(platform: str, url: str) -> bool:
    host = urlparse(url).netloc.lower()
    if platform == "target":
        return "target.com" in host
    if platform == "amazon":
        return "amazon." in host
    if platform == "nordstrom":
        return "nordstrom.com" in host
    if platform == "babyletto":
        return "babyletto.com" in host
    if platform == "newtonbaby":
        return "newtonbaby.com" in host
    if platform == "uppababy":
        return "uppababy.com" in host
    return bool(host)


def _choose_candidate_url(candidates: list[dict], product: dict, platform: str) -> str:
    if not candidates:
        return ""
    tokens = product_tokens(product)
    best_url = ""
    best_priority = -1
    best_score = -1
    heuristic_slug_url = ""
    heuristic_homepage_url = ""
    weak_fallback_url = ""
    weak_fallback_score = -1

    for row in candidates:
        url = str(row.get("candidate_url", "")).strip()
        reason = str(row.get("reason", "")).strip().lower()
        if not _is_platform_host(platform, url):
            continue
        parsed = urlparse(url)
        is_homepage = parsed.path in {"", "/"}

        # Prefer strong non-heuristic product URLs first.
        if (
            _is_likely_product_url(url)
            and is_platform_product_url(platform, url)
            and not reason.startswith("heuristic_")
            and not is_homepage
        ):
            score = _candidate_score(url, tokens)
            if best_priority < 3 or (best_priority == 3 and score > best_score):
                best_priority = 3
                best_score = score
                best_url = url
            continue

        # Keep a weak fallback for platform URLs with non-homepage paths
        # (e.g., retailer listing/search URLs) when no PDP was found.
        if not is_homepage:
            weak_score = _candidate_score(url, tokens)
            if _is_likely_product_url(url):
                weak_score += 2
            if reason == "heuristic_platform_search":
                weak_score += 1
            if weak_score > weak_fallback_score:
                weak_fallback_score = weak_score
                weak_fallback_url = url

        # Keep brand-domain heuristic fallbacks as backup options.
        if reason == "heuristic_domain_slug" and not heuristic_slug_url:
            heuristic_slug_url = url
        if reason == "heuristic_domain_homepage" and not heuristic_homepage_url:
            heuristic_homepage_url = url

    if best_url:
        return best_url
    if heuristic_slug_url and is_platform_product_url(platform, heuristic_slug_url):
        return heuristic_slug_url
    if weak_fallback_url:
        return weak_fallback_url
    if heuristic_homepage_url and is_platform_product_url(platform, heuristic_homepage_url):
        return heuristic_homepage_url

    for row in candidates:
        url = str(row.get("candidate_url", "")).strip()
        reason = str(row.get("reason", "")).strip().lower()
        if (
            _is_likely_product_url(url)
            and is_platform_product_url(platform, url)
            and not reason.startswith("heuristic_")
        ):
            return url
    return ""


def _is_price_outlier(price: float | None, baseline_price: float | None) -> bool:
    if price is None or baseline_price is None or baseline_price <= 0:
        return False
    return float(price) < float(baseline_price) * OUTLIER_BASELINE_RATIO_MIN


def _invalidate_untrusted_listing_price(platform: str, selected_url: str, price_result: dict) -> dict:
    if (
        price_result.get("current_price") is not None
        and is_listing_or_search_url(selected_url)
        and not is_platform_product_url(platform, selected_url)
    ):
        return {
            **price_result,
            "status": "parse_error",
            "current_price": None,
            "error": "listing_page_price_untrusted",
            "confidence": 0.0,
        }
    return price_result


def _resolve_source_url(*, approved_url: str, discovered_url: str, fallback_url: str) -> str:
    if approved_url.strip():
        return approved_url.strip()
    if discovered_url.strip():
        return discovered_url.strip()
    return fallback_url.strip()


def run_daily_pipeline(
    products: list[dict],
    price_fetcher,
    coupon_fetcher,
    discover_candidates_fn,
    snapshot_fn,
    llm_fallback_fn,
    digest_sender,
    history_writer,
    url_candidate_writer,
    best_price_writer,
    output_json_path: Path,
    max_openai_search_calls: int = 1000,
    max_openai_retailer_parse_calls: int = 1000,
    max_openai_fallbacks: int = 0,
    retailer_parse_fn=None,
) -> dict:
    alerts = []
    all_items = []
    coupons = []
    history_rows = []
    candidate_rows = []
    current_prices: dict[str, float] = {}
    fallback_uses = 0
    fallback_attempts = 0
    openai_search_uses = 0
    openai_search_attempts = 0
    openai_retailer_parse_uses = 0
    openai_retailer_parse_attempts = 0

    for product in products:
        platform = str(product.get("platform", "")).strip().lower()
        strategy = resolve_extraction_strategy(platform)
        selected_url = str(product.get("product_url", "")).strip()
        selected_candidate_snippet = ""
        candidates = []
        candidate_selection_error = None
        if strategy == "unsupported":
            unsupported = unsupported_platform_result(platform=platform)
            product["product_url"] = selected_url
            snapshot_meta = {"status": unsupported["snapshot_status"], "error": unsupported["error"]}
            price_result = {
                "status": unsupported["status"],
                "current_price": unsupported["current_price"],
                "currency": "USD",
                "evidence_url": selected_url,
                "error": unsupported["error"],
                "confidence": unsupported["confidence"],
            }
            html_text = ""
        elif not selected_url:
            if openai_search_attempts < max(0, max_openai_search_calls):
                openai_search_attempts += 1
                candidates = discover_candidates_fn(product, platform)
                if candidates:
                    openai_search_uses += 1
            else:
                candidates = []
            validated_url = _select_validated_candidate_url(candidates, product, platform, snapshot_fn)
            fallback_url = _choose_candidate_url(candidates, product, platform)
            selected_url = _resolve_source_url(
                approved_url="",
                discovered_url=validated_url,
                fallback_url=fallback_url,
            )
            for row in candidates:
                if str(row.get("candidate_url", "")).strip() == selected_url:
                    selected_candidate_snippet = str(row.get("snippet", ""))
                candidate_rows.append(
                    [
                        datetime.now(timezone.utc).isoformat(),
                        product["product_id"],
                        platform,
                        row.get("query", ""),
                        row.get("candidate_url", ""),
                        row.get("rank", ""),
                        str(row.get("candidate_url", "")).strip() == selected_url,
                        row.get("reason", ""),
                    ]
                )
            if candidates and not selected_url:
                candidate_selection_error = "no_likely_product_url_in_candidates"
            product["product_url"] = selected_url
            html_text = ""
            snapshot_meta = {"status": "skip", "error": None}
            if not selected_url:
                price_result = {
                    "status": "no_url",
                    "current_price": None,
                    "currency": "USD",
                    "evidence_url": "",
                    "error": "unresolved_url",
                    "confidence": 0.0,
                }
            else:
                snapshot_meta = snapshot_fn(selected_url, product["product_id"], platform)
                if snapshot_meta.get("status") == "ok":
                    try:
                        html_text = Path(snapshot_meta["path"]).read_text(encoding="utf-8")
                    except Exception:  # noqa: BLE001
                        html_text = ""
                price_result = price_fetcher(product, html=html_text if html_text else None)
        elif not _is_likely_product_url(selected_url):
            candidate_selection_error = "provided_url_not_likely_product_page"
            selected_url = ""
            product["product_url"] = selected_url
            html_text = ""
            snapshot_meta = {"status": "skip", "error": None}
            price_result = {
                "status": "no_url",
                "current_price": None,
                "currency": "USD",
                "evidence_url": "",
                "error": "unresolved_url",
                "confidence": 0.0,
            }
        else:
            product["product_url"] = selected_url
            html_text = ""
            snapshot_meta = snapshot_fn(selected_url, product["product_id"], platform)
            if snapshot_meta.get("status") == "ok":
                try:
                    html_text = Path(snapshot_meta["path"]).read_text(encoding="utf-8")
                except Exception:  # noqa: BLE001
                    html_text = ""
            price_result = price_fetcher(product, html=html_text if html_text else None)
        if _is_price_outlier(price_result.get("current_price"), product.get("baseline_price")):
            price_result = {
                **price_result,
                "status": "parse_error",
                "current_price": None,
                "error": "price_outlier_vs_baseline",
                "confidence": 0.0,
            }
        price_result = _invalidate_untrusted_listing_price(platform, selected_url, price_result)

        if strategy == "hybrid_retailer":
            if (
                price_result.get("current_price") is None
                and html_text
                and retailer_parse_fn is not None
                and openai_retailer_parse_attempts < max(0, max_openai_retailer_parse_calls)
            ):
                openai_retailer_parse_attempts += 1
                parsed = retailer_parse_fn(url=selected_url, html=html_text)
                if parsed:
                    openai_retailer_parse_uses += 1
                    price_result = parsed
            if price_result.get("current_price") is None and has_snippet_price_signal(selected_candidate_snippet):
                price_result = {
                    **price_result,
                    "status": "parse_error",
                    "current_price": None,
                    "error": "search_price_unverified",
                    "confidence": 0.0,
                }

        confidence = float(price_result.get("confidence") or 0.0)
        untrusted_listing = is_listing_or_search_url(selected_url) and not is_platform_product_url(platform, selected_url)
        needs_fallback = (
            (price_result.get("status") == "parse_error" or confidence < MIN_CONFIDENCE_FOR_DIRECT_USE)
            and not untrusted_listing
            and strategy == "deterministic"
        )
        if (
            needs_fallback
            and html_text
            and fallback_uses < max_openai_fallbacks
            and llm_fallback_fn is not None
        ):
            fallback_attempts += 1
            fallback = llm_fallback_fn(url=selected_url, html=html_text)
            if fallback:
                fallback_uses += 1
                price_result = fallback
            else:
                price_result = {**price_result, "error": price_result.get("error") or "openai_fallback_failed"}
        # Re-apply guard in case fallback produced a price from a listing/search page.
        price_result = _invalidate_untrusted_listing_price(platform, selected_url, price_result)

        price = price_result.get("current_price")
        if price is not None:
            current_prices[product["product_id"]] = float(price)

        if price is None:
            category, drop_pct = "NO_DATA", 0.0
        else:
            category, drop_pct = categorize_alert(
                current_price=float(price),
                baseline_price=product.get("baseline_price"),
                target_price=product.get("target_price"),
                significant_drop_pct=float(product.get("significant_drop_pct", 10.0)),
            )
        item = {
            "product_id": product["product_id"],
            "product_name": product.get("product_name", ""),
            "brand": product.get("brand", ""),
            "current_price": price,
            "baseline_price": product.get("baseline_price"),
            "target_price": product.get("target_price"),
            "significant_drop_pct": product.get("significant_drop_pct", 10.0),
            "status": price_result.get("status", "unknown"),
            "error": price_result.get("error") or candidate_selection_error,
            "confidence": float(price_result.get("confidence") or 0.0),
            "snapshot_status": snapshot_meta.get("status"),
            "alert_category": category,
            "drop_pct": drop_pct,
            "product_url": product.get("product_url", ""),
            "platform": product.get("platform", ""),
        }
        all_items.append(item)
        if category in {"SIGNIFICANT_DROP", "TARGET_REACHED"}:
            alerts.append(item)

        coupon = coupon_fetcher(product.get("product_url", ""), html=html_text if html_text else None)
        if not coupon and price_result.get("coupon_text"):
            coupon = {"offer_text": price_result.get("coupon_text"), "source_url": product.get("product_url", "")}
        if coupon:
            coupon["brand"] = product.get("brand", "")
            coupons.append(coupon)

        history_rows.append(
            [
                datetime.now(timezone.utc).isoformat(),
                product["product_id"],
                product.get("product_name", ""),
                product.get("platform", ""),
                price,
                product.get("baseline_price"),
                product.get("target_price"),
                category,
                drop_pct,
                product.get("product_url", ""),
            ]
        )

    # Aggregate one best (lowest) price per product across platforms.
    best_by_product: dict[str, dict] = {}
    for item in all_items:
        product_id = item["product_id"]
        price = item.get("current_price")
        if price is None:
            continue
        if product_id not in best_by_product or float(price) < float(best_by_product[product_id]["current_price"]):
            best_by_product[product_id] = item

    best_items = []
    best_alerts = []
    for product_id, best in best_by_product.items():
        category, drop_pct = categorize_alert(
            current_price=float(best["current_price"]),
            baseline_price=best.get("baseline_price"),
            target_price=best.get("target_price"),
            significant_drop_pct=float(best.get("significant_drop_pct", 10.0)),
        )
        enriched = {
            **best,
            "best_across_platforms": True,
            "alert_category": category,
            "drop_pct": drop_pct,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        best_items.append(enriched)
        if category in {"SIGNIFICANT_DROP", "TARGET_REACHED"}:
            best_alerts.append(enriched)

    digest_sender({"top_drops": best_alerts, "all_items": best_items, "coupons": coupons})
    url_candidate_writer(candidate_rows)
    history_writer(history_rows)
    best_price_writer(best_items)

    summary = {
        "processed": len(products),
        "alerts": len(best_alerts),
        "best_alerts": len(best_alerts),
        "coupons": len(coupons),
        "url_candidates": len(candidate_rows),
        "openai_fallback_attempts": fallback_attempts,
        "openai_fallback_uses": fallback_uses,
        "openai_search_attempts": openai_search_attempts,
        "openai_search_uses": openai_search_uses,
        "openai_retailer_parse_attempts": openai_retailer_parse_attempts,
        "openai_retailer_parse_uses": openai_retailer_parse_uses,
        "no_data": sum(1 for item in all_items if item["alert_category"] == "NO_DATA"),
        "unresolved_urls": sum(1 for item in all_items if not str(item.get("product_url", "")).strip()),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_prices": {item["product_id"]: item["current_price"] for item in best_items},
        "best_items": best_items,
        "items": all_items,
    }
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return summary


def _records_from_products(products: list[ProductRecord]) -> list[dict]:
    records = []
    for p in products:
        platforms = list(p.platforms) if p.platforms else ([p.platform] if p.platform else [])
        for platform in platforms:
            records.append(
                {
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "brand": p.brand,
                    "platform": platform,
                    "product_url": p.product_url,
                    "baseline_price": p.baseline_price,
                    "target_price": p.target_price,
                    "significant_drop_pct": p.significant_drop_pct,
                }
            )
    return records


def _apply_approved_urls(records: list[dict], approved_lookup: dict[tuple[str, str], str]) -> None:
    if not approved_lookup:
        return
    for record in records:
        key = (str(record.get("product_id", "")).strip(), str(record.get("platform", "")).strip().lower())
        approved = approved_lookup.get(key, "")
        if approved:
            record["product_url"] = approved


def _make_llm_fallback(settings):
    if not settings.openai_api_key:
        return None

    def _fallback(*, url: str, html: str) -> dict | None:
        return extract_price_and_coupon_with_openai(
            html=html,
            url=url,
            api_key=settings.openai_api_key,
        )

    return _fallback


def _make_retailer_parse_fn(settings):
    if not settings.openai_api_key:
        return None

    def _parse(*, url: str, html: str) -> dict | None:
        return extract_price_and_coupon_with_openai(
            html=html,
            url=url,
            api_key=settings.openai_api_key,
            source_label="openai_retailer_parse",
        )

    return _parse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run daily price alert workflow")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-json", default=".tmp/latest_run.json")
    args = parser.parse_args()

    settings = load_settings()
    products = load_products_from_sheet(
        service_account_file=settings.google_service_account_file,
        sheet_id=settings.price_sheet_id,
        worksheet_name=settings.products_worksheet_name,
    )
    records = _records_from_products(products)
    approved_lookup = load_approved_urls(
        service_account_file=settings.google_service_account_file,
        sheet_id=settings.price_sheet_id,
        worksheet_name=settings.approved_urls_worksheet_name,
    )
    _apply_approved_urls(records, approved_lookup)

    def digest_sender(payload: dict) -> None:
        if args.dry_run:
            return
        html = render_digest_html(
            run_date=str(date.today()),
            top_drops=payload["top_drops"],
            all_items=payload["all_items"],
            coupons=payload["coupons"],
        )
        service = get_gmail_service(settings.gmail_oauth_client_file, settings.gmail_token_file)
        send_html_email(
            service=service,
            recipient=settings.alert_recipient_email,
            subject=f"Daily Baby Price Alert - {date.today().isoformat()}",
            html_body=html,
        )

    def history_writer(rows: list[list]) -> None:
        append_price_history_rows(
            service_account_file=settings.google_service_account_file,
            sheet_id=settings.price_sheet_id,
            rows=rows,
            worksheet_name=settings.price_history_worksheet_name,
        )

    def url_candidate_writer(rows: list[list]) -> None:
        if args.dry_run:
            return
        append_url_candidate_rows(
            service_account_file=settings.google_service_account_file,
            sheet_id=settings.price_sheet_id,
            rows=rows,
            worksheet_name=settings.url_candidates_worksheet_name,
        )

    def best_price_writer(best_items: list[dict]) -> None:
        if args.dry_run:
            return
        best_map = {
            item["product_id"]: {
                "current_price": item.get("current_price"),
                "platform": item.get("platform"),
                "product_url": item.get("product_url"),
                "checked_at": item.get("checked_at"),
            }
            for item in best_items
        }
        upsert_best_price_flags(
            service_account_file=settings.google_service_account_file,
            sheet_id=settings.price_sheet_id,
            best_by_product_id=best_map,
            worksheet_name=settings.products_worksheet_name,
        )

    def discover_candidates(product: dict, platform: str) -> list[dict]:
        return search_product_candidates_with_openai(
            product=product,
            platform=platform,
            api_key=settings.openai_api_key,
        )

    def snapshot(url: str, product_id: str, platform: str) -> dict:
        return snapshot_page(url=url, product_id=product_id, platform=platform)

    llm_fallback_fn = _make_llm_fallback(settings)
    retailer_parse_fn = _make_retailer_parse_fn(settings)

    summary = run_daily_pipeline(
        products=records,
        price_fetcher=collect_price,
        coupon_fetcher=find_signup_coupon,
        discover_candidates_fn=discover_candidates,
        snapshot_fn=snapshot,
        llm_fallback_fn=llm_fallback_fn,
        retailer_parse_fn=retailer_parse_fn,
        digest_sender=digest_sender,
        history_writer=history_writer,
        url_candidate_writer=url_candidate_writer,
        best_price_writer=best_price_writer,
        output_json_path=Path(args.output_json),
        max_openai_search_calls=settings.max_openai_search_calls,
        max_openai_retailer_parse_calls=settings.max_openai_retailer_parse_calls,
        max_openai_fallbacks=settings.max_openai_fallbacks,
    )
    if not args.dry_run:
        baseline_updates = build_missing_baseline_updates(
            products,
            {k: float(v) for k, v in summary.get("current_prices", {}).items() if v is not None},
        )
        apply_missing_baseline_updates(
            service_account_file=settings.google_service_account_file,
            sheet_id=settings.price_sheet_id,
            updates=baseline_updates,
            worksheet_name=settings.products_worksheet_name,
        )
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
