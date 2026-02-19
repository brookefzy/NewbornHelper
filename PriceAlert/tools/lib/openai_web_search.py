from __future__ import annotations

import json
import time
from typing import Callable
from urllib.parse import urlparse

import requests

DEFAULT_MODEL = "gpt-4.1-mini"


def _default_request(payload: dict, api_key: str, timeout: int = 30) -> dict:
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _extract_text(response_json: dict) -> str:
    text = response_json.get("output_text")
    if isinstance(text, str) and text.strip():
        return text
    output = response_json.get("output", [])
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                value = block.get("text")
                if isinstance(value, str) and value.strip():
                    return value
                nested = block.get("output_text")
                if isinstance(nested, str) and nested.strip():
                    return nested
    return ""


def _build_search_query(*, product_name: str, brand: str, platform: str) -> str:
    parts = [brand.strip(), product_name.strip(), platform.strip()]
    return " ".join(part for part in parts if part)


def _build_candidate_ranking_prompt(*, product_name: str, brand: str, platform: str) -> str:
    return (
        "Find likely product detail page URLs for this product and retailer. "
        "Return JSON array only. Each item must include: candidate_url, title, snippet, domain, match_score. "
        "match_score must be a float from 0 to 1. "
        f"Brand term required: {brand}. Product term required: {product_name}. Retailer: {platform}."
    )


def _normalize_candidates(raw_rows: list[dict], *, query: str) -> list[dict]:
    normalized: list[dict] = []
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("candidate_url", "")).strip()
        if not url:
            continue
        domain = str(row.get("domain", "")).strip().lower() or urlparse(url).netloc.lower()
        try:
            match_score = float(row.get("match_score", 0.0))
        except Exception:  # noqa: BLE001
            match_score = 0.0
        normalized.append(
            {
                "candidate_url": url,
                "title": str(row.get("title", "")).strip(),
                "snippet": str(row.get("snippet", "")).strip(),
                "domain": domain,
                "match_score": max(0.0, min(1.0, match_score)),
                "rank": len(normalized) + 1,
                "query": query,
                "reason": "openai_web_search",
            }
        )
    return normalized


def search_product_candidates_with_openai(
    *,
    product: dict,
    platform: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 2,
    request_fn: Callable[[dict, str], dict] | None = None,
) -> list[dict]:
    if not api_key:
        return []

    product_name = str(product.get("product_name", "")).strip()
    brand = str(product.get("brand", "")).strip()
    query = _build_search_query(product_name=product_name, brand=brand, platform=platform)
    prompt = _build_candidate_ranking_prompt(product_name=product_name, brand=brand, platform=platform)
    payload = {
        "model": model,
        "tools": [{"type": "web_search"}],
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": query}]},
        ],
    }
    caller = request_fn or _default_request

    last_error: Exception | None = None
    attempts = max(1, max_retries)
    for attempt in range(attempts):
        try:
            response_json = caller(payload, api_key)
            text = _extract_text(response_json)
            if not text:
                return []
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                return []
            return _normalize_candidates(parsed, query=query)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.25 * (attempt + 1))
    if last_error:
        return []
    return []

