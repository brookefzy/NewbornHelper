from __future__ import annotations

import json
import re
from collections.abc import Callable

import requests


def _fetch_html(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (PriceAlertBot/1.0)"},
        timeout=20,
    )
    response.raise_for_status()
    return response.text


def _extract_json_ld_price(html: str) -> tuple[float | None, str]:
    scripts = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, flags=re.DOTALL | re.IGNORECASE)
    for raw in scripts:
        try:
            data = json.loads(raw.strip())
        except Exception:  # noqa: BLE001
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price")
                if price is not None:
                    return float(str(price).replace(",", "")), "json_ld_offer_price"
    return None, ""


def _extract_price(html: str) -> tuple[float | None, str]:
    json_ld_price, reason = _extract_json_ld_price(html)
    if json_ld_price is not None:
        return json_ld_price, reason

    meta = re.search(r'property="product:price:amount" content="([0-9][\d,.]*)"', html, flags=re.IGNORECASE)
    if meta:
        return float(meta.group(1).replace(",", "")), "meta_product_price"

    whole_fraction = re.search(r'a-price-whole">([\d,]+)</span>\s*<span class="a-price-fraction">(\d{2})', html)
    if whole_fraction:
        whole = whole_fraction.group(1).replace(",", "")
        frac = whole_fraction.group(2)
        return float(f"{whole}.{frac}"), "amazon_whole_fraction"

    generic = re.search(r"[$£€]\s*([0-9][\d,]*(?:\.\d{2})?)", html)
    if generic:
        return float(generic.group(1).replace(",", "")), "generic_currency"
    return None, ""


def has_snippet_price_signal(text: str) -> bool:
    return bool(re.search(r"[$£€]\s*([0-9][\d,]*(?:\.\d{2})?)", text or ""))


def collect_price(
    product: dict,
    fetch_html_fn: Callable[[str], str] | None = None,
    html: str | None = None,
) -> dict:
    fetch = fetch_html_fn or _fetch_html
    url = product.get("product_url", "")
    try:
        page_html = html if html is not None else fetch(url)
        price, reason = _extract_price(page_html)
        if price is None:
            return {
                "status": "parse_error",
                "current_price": None,
                "currency": "USD",
                "evidence_url": url,
                "evidence_text": "",
                "confidence": 0.0,
                "error": "price_not_found",
            }
        return {
            "status": "ok",
            "current_price": price,
            "currency": "USD",
            "evidence_url": url,
            "evidence_text": reason,
            "confidence": 0.8 if reason != "generic_currency" else 0.5,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "fetch_error",
            "current_price": None,
            "currency": "USD",
            "evidence_url": url,
            "evidence_text": "",
            "confidence": 0.0,
            "error": str(exc),
        }
