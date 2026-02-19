from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    price_sheet_id: str
    google_service_account_file: str
    gmail_oauth_client_file: str
    gmail_token_file: str
    alert_recipient_email: str
    openai_api_key: str
    products_worksheet_name: str
    price_history_worksheet_name: str
    url_candidates_worksheet_name: str
    approved_urls_worksheet_name: str
    max_openai_search_calls: int
    max_openai_retailer_parse_calls: int
    max_openai_fallbacks: int
    google_cse_api_key: str
    google_cse_id: str


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _as_int(name: str, default: int) -> int:
    raw = _optional(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer: {raw}") from exc


def load_settings() -> Settings:
    openai_api_key = _optional("OPENAI_API_KEY") or _optional("OPEN_API_KEY")
    return Settings(
        price_sheet_id=_required("PRICE_SHEET_ID"),
        google_service_account_file=str(Path(_required("GOOGLE_SERVICE_ACCOUNT_FILE")).expanduser()),
        gmail_oauth_client_file=str(Path(_required("GMAIL_OAUTH_CLIENT_FILE")).expanduser()),
        gmail_token_file=str(Path(_required("GMAIL_TOKEN_FILE")).expanduser()),
        alert_recipient_email=_required("ALERT_RECIPIENT_EMAIL"),
        openai_api_key=openai_api_key,
        products_worksheet_name=_optional("PRODUCTS_WORKSHEET_NAME", "products"),
        price_history_worksheet_name=_optional("PRICE_HISTORY_WORKSHEET_NAME", "price_history"),
        url_candidates_worksheet_name=_optional("URL_CANDIDATES_WORKSHEET_NAME", "url_candidates"),
        approved_urls_worksheet_name=_optional("APPROVED_URLS_WORKSHEET_NAME", "approved_urls"),
        max_openai_search_calls=_as_int("MAX_OPENAI_SEARCH_CALLS", 15),
        max_openai_retailer_parse_calls=_as_int("MAX_OPENAI_RETAILER_PARSE_CALLS", 10),
        max_openai_fallbacks=_as_int("MAX_OPENAI_FALLBACKS", 5),
        google_cse_api_key=_optional("GOOGLE_CSE_API_KEY"),
        google_cse_id=_optional("GOOGLE_CSE_ID"),
    )
