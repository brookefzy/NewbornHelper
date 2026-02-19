import os

from tools.lib.config import load_settings


def test_load_settings_has_required_paths_and_sheet_id(monkeypatch):
    monkeypatch.setenv("PRICE_SHEET_ID", "sheet-123")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google_drive_personal.json")
    monkeypatch.setenv("GMAIL_OAUTH_CLIENT_FILE", "client_secret_desktop.json")
    monkeypatch.setenv("GMAIL_TOKEN_FILE", "gmail_token.json")
    monkeypatch.setenv("ALERT_RECIPIENT_EMAIL", "yuanzfan16@gmail.com")
    monkeypatch.setenv("OPEN_API_KEY", "sk-test")
    monkeypatch.setenv("PRODUCTS_WORKSHEET_NAME", "products")
    monkeypatch.setenv("PRICE_HISTORY_WORKSHEET_NAME", "price_history")
    monkeypatch.setenv("URL_CANDIDATES_WORKSHEET_NAME", "url_candidates")
    monkeypatch.setenv("APPROVED_URLS_WORKSHEET_NAME", "approved_urls")
    monkeypatch.setenv("MAX_OPENAI_SEARCH_CALLS", "12")
    monkeypatch.setenv("MAX_OPENAI_RETAILER_PARSE_CALLS", "7")
    monkeypatch.setenv("MAX_OPENAI_FALLBACKS", "3")
    monkeypatch.setenv("GOOGLE_CSE_API_KEY", "cse-key")
    monkeypatch.setenv("GOOGLE_CSE_ID", "cse-id")

    settings = load_settings()

    assert settings.price_sheet_id == "sheet-123"
    assert settings.google_service_account_file.endswith("google_drive_personal.json")
    assert settings.gmail_oauth_client_file.endswith("client_secret_desktop.json")
    assert settings.gmail_token_file.endswith("gmail_token.json")
    assert settings.alert_recipient_email == "yuanzfan16@gmail.com"
    assert settings.openai_api_key == "sk-test"
    assert settings.products_worksheet_name == "products"
    assert settings.price_history_worksheet_name == "price_history"
    assert settings.url_candidates_worksheet_name == "url_candidates"
    assert settings.approved_urls_worksheet_name == "approved_urls"
    assert settings.max_openai_search_calls == 12
    assert settings.max_openai_retailer_parse_calls == 7
    assert settings.max_openai_fallbacks == 3
    assert settings.google_cse_api_key == "cse-key"
    assert settings.google_cse_id == "cse-id"
