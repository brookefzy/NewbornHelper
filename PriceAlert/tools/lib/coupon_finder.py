from __future__ import annotations

import re
from collections.abc import Callable

import requests


def _fetch_html(url: str) -> str:
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (PriceAlertBot/1.0)"})
    response.raise_for_status()
    return response.text


def find_signup_coupon_in_html(html: str, url: str) -> dict | None:
    patterns = [
        r"(sign up[^.]{0,140}\d{1,2}%\s*off[^.]*)",
        r"(newsletter[^.]{0,140}\d{1,2}%\s*off[^.]*)",
        r"(first order[^.]{0,140}\d{1,2}%\s*off[^.]*)",
    ]
    lowered = " ".join(html.split()).lower()
    for pattern in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            text = match.group(1).strip()
            return {"offer_text": text, "source_url": url}
    return None


def find_signup_coupon(url: str, fetch_html_fn: Callable[[str], str] | None = None, html: str | None = None) -> dict | None:
    fetch = fetch_html_fn or _fetch_html
    try:
        page_html = html if html is not None else fetch(url)
    except Exception:  # noqa: BLE001
        return None
    return find_signup_coupon_in_html(page_html, url)
