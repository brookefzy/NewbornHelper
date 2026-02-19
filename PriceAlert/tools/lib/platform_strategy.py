from __future__ import annotations

EXTRACTION_STRATEGIES = {
    "babyletto": "deterministic",
    "newtonbaby": "deterministic",
    "target": "hybrid_retailer",
    "nordstrom": "hybrid_retailer",
}


def resolve_extraction_strategy(platform: str) -> str:
    key = (platform or "").strip().lower()
    return EXTRACTION_STRATEGIES.get(key, "unsupported")


def unsupported_platform_result(*, platform: str) -> dict:
    return {
        "platform": platform,
        "status": "no_data",
        "error": "platform_not_supported",
        "snapshot_status": "skip",
        "current_price": None,
        "confidence": 0.0,
    }

