from __future__ import annotations

import re
from urllib.parse import urlparse


def product_tokens(product: dict) -> set[str]:
    text = f"{product.get('brand', '')} {product.get('product_name', '')}".lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    return {t for t in tokens if len(t) >= 4}


def is_platform_product_url(platform: str, url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    if platform == "target":
        return "target.com" in host and "/p/" in path and "/-/a-" in path
    if platform == "amazon":
        return "amazon." in host and ("/dp/" in path or "/gp/product/" in path)
    if platform == "nordstrom":
        return "nordstrom.com" in host and path.startswith("/s/")
    if platform in {"babyletto", "newtonbaby", "uppababy"}:
        return any(fragment in path for fragment in ["/products/", "/product/", "/collections/", "/shop/"])
    return path not in {"", "/"}


def is_listing_or_search_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    if not lowered:
        return False
    listing_fragments = [
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
    return any(fragment in lowered for fragment in listing_fragments)

