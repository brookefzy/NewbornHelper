from __future__ import annotations

import json
from typing import Callable

import requests


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
    # Parse raw Responses API payload shape when output_text is absent.
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


def extract_price_and_coupon_with_openai(
    *,
    html: str,
    url: str,
    api_key: str,
    model: str = "gpt-4.1-mini",
    request_fn: Callable[[dict, str], dict] | None = None,
    source_label: str = "openai_fallback",
) -> dict | None:
    if not api_key:
        return None

    prompt = (
        "Extract product price and sign-up coupon from HTML. "
        "Return strict JSON with keys: price, currency, coupon_text, confidence, evidence_text. "
        "Use null for missing values."
    )
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": f"URL: {url}\nHTML:\n{html[:12000]}"}]},
        ],
    }
    caller = request_fn or _default_request
    try:
        response = caller(payload, api_key)
    except Exception:  # noqa: BLE001
        return None

    text = _extract_text(response)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    try:
        price = parsed.get("price")
        return {
            "status": "ok" if price is not None else "parse_error",
            "current_price": float(price) if price is not None else None,
            "currency": parsed.get("currency") or "USD",
            "coupon_text": parsed.get("coupon_text"),
            "confidence": float(parsed.get("confidence") or 0.0),
            "evidence_text": parsed.get("evidence_text") or "",
            "evidence_url": url,
            "error": None if price is not None else "llm_price_not_found",
            "source": source_label,
        }
    except Exception:  # noqa: BLE001
        return None
