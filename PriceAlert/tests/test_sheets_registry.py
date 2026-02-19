from gspread.exceptions import WorksheetNotFound

from tools.lib.sheets_registry import cleanup_review_queue, dedupe_review_queue_records, load_approved_urls, parse_products


def test_parse_products_filters_active_and_normalizes_columns():
    rows = [
        {
            "product_id": "p1",
            "product_name": "Stroller",
            "brand": "BrandA",
            "platform": "amazon",
            "product_url": "https://example.com/p1",
            "baseline_price": "499.99",
            "target_price": "450.00",
            "significant_drop_pct": "10",
            "active": "TRUE",
        },
        {
            "product_id": "p2",
            "product_name": "Bottle Warmer",
            "brand": "BrandB",
            "platform": "target",
            "product_url": "https://example.com/p2",
            "baseline_price": "",
            "target_price": "",
            "significant_drop_pct": "",
            "active": "false",
        },
    ]

    products = parse_products(rows)

    assert len(products) == 1
    assert products[0].product_id == "p1"
    assert products[0].baseline_price == 499.99
    assert products[0].target_price == 450.0
    assert products[0].significant_drop_pct == 10.0
    assert products[0].platforms == ("amazon",)


def test_parse_products_allows_missing_product_url():
    rows = [
        {
            "product_id": "p3",
            "product_name": "Car Seat",
            "brand": "BrandC",
            "platform": "target",
            "target_price": "220",
            "active": "TRUE",
        }
    ]

    products = parse_products(rows)

    assert len(products) == 1
    assert products[0].product_url == ""


def test_parse_products_accepts_integer_product_id():
    rows = [
        {
            "product_id": 12345,
            "product_name": "Crib",
            "brand": "BrandD",
            "platform": "amazon",
            "product_url": "",
            "active": "TRUE",
        }
    ]

    products = parse_products(rows)

    assert len(products) == 1
    assert products[0].product_id == "12345"


def test_parse_products_accepts_numeric_price_cells():
    rows = [
        {
            "product_id": "p9",
            "product_name": "Monitor",
            "brand": "BrandE",
            "platform": "target",
            "product_url": "",
            "baseline_price": 300,
            "target_price": 250,
            "significant_drop_pct": 15,
            "active": "TRUE",
        }
    ]

    products = parse_products(rows)

    assert len(products) == 1
    assert products[0].baseline_price == 300.0
    assert products[0].target_price == 250.0
    assert products[0].significant_drop_pct == 15.0


def test_parse_products_splits_comma_separated_platforms():
    rows = [
        {
            "product_id": "p10",
            "product_name": "Crib",
            "brand": "Babyletto",
            "platform": "babyletto, target, amazon, nordstrom",
            "active": "TRUE",
        }
    ]

    products = parse_products(rows)
    assert len(products) == 1
    assert products[0].platforms == ("babyletto", "target", "amazon", "nordstrom")


def test_load_approved_urls_filters_and_normalizes(monkeypatch):
    class DummyWorksheet:
        def get_all_records(self):
            return [
                {"product_id": "1", "platform": "target", "approved_url": "https://www.target.com/p/a/-/A-1", "approval": "TRUE"},
                {"product_id": "1", "platform": "amazon", "approved_url": "", "product_url": "https://www.amazon.com/dp/B0001", "approval": "true"},
                {"product_id": "2", "platform": "nordstrom", "approved_url": "https://www.nordstrom.com/s/x", "approval": "FALSE"},
            ]

    class DummySpreadsheet:
        def worksheet(self, name):
            assert name == "approved_urls"
            return DummyWorksheet()

    monkeypatch.setattr("tools.lib.sheets_registry._open_spreadsheet", lambda *_args, **_kwargs: DummySpreadsheet())
    approved = load_approved_urls("sa.json", "sheet", worksheet_name="approved_urls")
    assert approved == {
        ("1", "target"): "https://www.target.com/p/a/-/A-1",
        ("1", "amazon"): "https://www.amazon.com/dp/B0001",
    }


def test_load_approved_urls_returns_empty_when_worksheet_missing(monkeypatch):
    class DummySpreadsheet:
        def worksheet(self, _name):
            raise WorksheetNotFound("approved_urls")

    monkeypatch.setattr("tools.lib.sheets_registry._open_spreadsheet", lambda *_args, **_kwargs: DummySpreadsheet())
    approved = load_approved_urls("sa.json", "sheet", worksheet_name="approved_urls")
    assert approved == {}


def test_dedupe_review_queue_records_prefers_latest_reviewed_decision():
    rows = [
        {
            "run_ts": "2026-02-19T10:00:00Z",
            "product_id": "1",
            "platform": "target",
            "approved_url": "https://target.com/p/a",
            "approval": "",
            "validator_score": "7",
        },
        {
            "run_ts": "2026-02-19T10:05:00Z",
            "product_id": "1",
            "platform": "target",
            "approved_url": "https://target.com/p/a",
            "approval": "TRUE",
            "validator_score": "7",
        },
        {
            "run_ts": "2026-02-19T10:10:00Z",
            "product_id": "1",
            "platform": "target",
            "approved_url": "https://target.com/p/a",
            "approval": "",
            "validator_score": "9",
        },
    ]
    deduped = dedupe_review_queue_records(rows)
    assert len(deduped) == 1
    assert deduped[0]["approval"] == "TRUE"


def test_dedupe_review_queue_records_keeps_latest_when_no_decision():
    rows = [
        {
            "run_ts": "2026-02-19T10:00:00Z",
            "product_id": "2",
            "platform": "nordstrom",
            "approved_url": "https://nordstrom.com/s/x",
            "approval": "",
            "validator_score": "3",
        },
        {
            "run_ts": "2026-02-19T10:07:00Z",
            "product_id": "2",
            "platform": "nordstrom",
            "approved_url": "https://nordstrom.com/s/x",
            "approval": "",
            "validator_score": "6",
        },
    ]
    deduped = dedupe_review_queue_records(rows)
    assert len(deduped) == 1
    assert deduped[0]["validator_score"] == "6"


def test_cleanup_review_queue_dry_run_reports_counts(monkeypatch):
    class DummyWorksheet:
        def __init__(self):
            self.cleared = False

        def row_values(self, _row):
            return ["run_ts", "product_id", "platform", "approved_url", "approval"]

        def get_all_records(self):
            return [
                {"run_ts": "1", "product_id": "1", "platform": "target", "approved_url": "https://target.com/p/a", "approval": ""},
                {"run_ts": "2", "product_id": "1", "platform": "target", "approved_url": "https://target.com/p/a", "approval": "TRUE"},
            ]

        def clear(self):
            self.cleared = True

        def update(self, *_args, **_kwargs):
            raise AssertionError("update should not be called in dry-run")

    class DummySpreadsheet:
        def worksheet(self, _name):
            return DummyWorksheet()

    monkeypatch.setattr("tools.lib.sheets_registry._open_spreadsheet", lambda *_args, **_kwargs: DummySpreadsheet())
    result = cleanup_review_queue("sa.json", "sheet", worksheet_name="approved_urls", dry_run=True)
    assert result["status"] == "ok"
    assert result["input_rows"] == 2
    assert result["kept_rows"] == 1
    assert result["removed_rows"] == 1


def test_cleanup_review_queue_rewrites_sheet(monkeypatch):
    class DummyWorksheet:
        def __init__(self):
            self.cleared = False
            self.updated_payload = None

        def row_values(self, _row):
            return ["run_ts", "product_id", "platform", "approved_url", "approval"]

        def get_all_records(self):
            return [
                {"run_ts": "1", "product_id": "1", "platform": "target", "approved_url": "https://target.com/p/a", "approval": ""},
                {"run_ts": "2", "product_id": "1", "platform": "target", "approved_url": "https://target.com/p/a", "approval": "TRUE"},
            ]

        def clear(self):
            self.cleared = True

        def update(self, _start, values, **_kwargs):
            self.updated_payload = values

    worksheet = DummyWorksheet()

    class DummySpreadsheet:
        def worksheet(self, _name):
            return worksheet

    monkeypatch.setattr("tools.lib.sheets_registry._open_spreadsheet", lambda *_args, **_kwargs: DummySpreadsheet())
    result = cleanup_review_queue("sa.json", "sheet", worksheet_name="approved_urls", dry_run=False)
    assert result["removed_rows"] == 1
    assert worksheet.cleared is True
    assert worksheet.updated_payload is not None
    # header + 1 deduped row
    assert len(worksheet.updated_payload) == 2
