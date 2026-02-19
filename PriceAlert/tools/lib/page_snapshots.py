from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from tools.lib.http_cache import get_cached_html, put_cached_html


def _download_html(url: str) -> str:
    cached = get_cached_html(url)
    if cached:
        return cached
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (PriceAlertBot/1.0)"})
    response.raise_for_status()
    html = response.text
    put_cached_html(url, html)
    return html


def snapshot_page(
    *,
    url: str,
    product_id: str,
    platform: str,
    fetch_html_fn: Callable[[str], str] | None = None,
    base_dir: str | Path = ".tmp/html",
) -> dict:
    downloader = fetch_html_fn or _download_html
    output_dir = Path(base_dir) / str(product_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{platform}.html"
    try:
        html = downloader(url)
        out_file.write_text(html, encoding="utf-8")
        return {
            "status": "ok",
            "path": str(out_file),
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "fetch_error",
            "path": str(out_file),
            "url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }
