from __future__ import annotations

import hashlib
from pathlib import Path


def _cache_path(url: str, base_dir: str | Path = ".tmp/http_cache") -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return Path(base_dir) / f"{digest}.html"


def get_cached_html(url: str, base_dir: str | Path = ".tmp/http_cache") -> str | None:
    path = _cache_path(url, base_dir=base_dir)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None


def put_cached_html(url: str, html: str, base_dir: str | Path = ".tmp/http_cache") -> None:
    path = _cache_path(url, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
