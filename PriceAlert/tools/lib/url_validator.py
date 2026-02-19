from __future__ import annotations

from urllib.parse import unquote, urlparse

from tools.lib.url_rules import product_tokens

ALLOWED_DOMAINS = {
    "target": ("target.com",),
    "nordstrom": ("nordstrom.com",),
    "babyletto": ("babyletto.com",),
    "newtonbaby": ("newtonbaby.com",),
}


def _is_allowed_domain(platform: str, url: str) -> bool:
    host = urlparse(url).netloc.lower()
    allowed = ALLOWED_DOMAINS.get((platform or "").strip().lower(), ())
    return any(domain in host for domain in allowed)


def _keyword_overlap(*, product: dict, url: str, candidate_title: str, candidate_snippet: str) -> int:
    tokens = product_tokens(product)
    path = unquote(urlparse(url).path).lower()
    text = f"{candidate_title} {candidate_snippet} {path}".lower()
    return sum(1 for token in tokens if token and token in text)


def _is_path_relevant(url: str, product: dict) -> bool:
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()
    query = unquote(parsed.query).lower()
    combined = f"{path}?{query}" if query else path

    listing_indicators = ["/s", "/search", "searchterm=", "keyword=", "sr?", "q="]
    if any(fragment in combined for fragment in listing_indicators):
        return False

    if any(fragment in path for fragment in ["/product", "/products", "/p/", "-/a-"]):
        return True

    tokens = product_tokens(product)
    slug_hits = sum(1 for token in tokens if token and token in path)
    return slug_hits >= 1


def validate_candidate_url(
    *,
    url: str,
    platform: str,
    product: dict,
    fetch_html_fn=None,
    candidate_title: str = "",
    candidate_snippet: str = "",
) -> dict:
    if not url.strip():
        return {
            "is_useful": False,
            "score": 0,
            "reason": "empty_url",
            "notes": "",
            "allowed_domain": False,
            "keyword_overlap": 0,
            "path_relevant": False,
        }

    allowed_domain = _is_allowed_domain(platform, url)
    keyword_overlap = _keyword_overlap(
        product=product,
        url=url,
        candidate_title=candidate_title,
        candidate_snippet=candidate_snippet,
    )
    path_relevant = _is_path_relevant(url, product)
    is_useful = allowed_domain and keyword_overlap >= 2 and path_relevant
    score = (4 if allowed_domain else 0) + min(keyword_overlap, 4) + (3 if path_relevant else 0)
    reason = "validated" if is_useful else "weak_match"
    notes = f"allowed_domain={allowed_domain};keyword_overlap={keyword_overlap};path_relevant={path_relevant}"
    return {
        "is_useful": is_useful,
        "score": score,
        "reason": reason,
        "notes": notes,
        "allowed_domain": allowed_domain,
        "keyword_overlap": keyword_overlap,
        "path_relevant": path_relevant,
    }
