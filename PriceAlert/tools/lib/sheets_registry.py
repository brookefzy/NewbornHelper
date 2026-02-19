from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import gspread
from gspread.exceptions import WorksheetNotFound
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials


@dataclass(frozen=True)
class ProductRecord:
    product_id: str
    product_name: str
    brand: str
    platform: str
    platforms: tuple[str, ...]
    product_url: str
    baseline_price: float | None
    target_price: float | None
    significant_drop_pct: float


def _as_float(value) -> float | None:
    raw = _as_text(value)
    if not raw:
        return None
    return float(raw)


def _as_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_active(value: str) -> bool:
    return (value or "").strip().lower() in {"true", "1", "yes", "y"}


def _parse_platforms(value) -> tuple[str, ...]:
    raw = _as_text(value).lower()
    if not raw:
        return tuple()
    parts = [segment.strip() for segment in raw.split(",")]
    normalized = [segment for segment in parts if segment]
    deduped: list[str] = []
    seen: set[str] = set()
    for platform in normalized:
        if platform in seen:
            continue
        seen.add(platform)
        deduped.append(platform)
    return tuple(deduped)


def parse_products(rows: Iterable[dict[str, str]]) -> list[ProductRecord]:
    products: list[ProductRecord] = []
    for row in rows:
        if not _is_active(row.get("active", "")):
            continue
        products.append(
            ProductRecord(
                product_id=_as_text(row.get("product_id", "")),
                product_name=_as_text(row.get("product_name", "")),
                brand=_as_text(row.get("brand", "")),
                platform=_as_text(row.get("platform", "")).lower(),
                platforms=_parse_platforms(row.get("platform", "")),
                product_url=_as_text(row.get("product_url", "")),
                baseline_price=_as_float(row.get("baseline_price", "")),
                target_price=_as_float(row.get("target_price", "")),
                significant_drop_pct=_as_float(row.get("significant_drop_pct", "")) or 10.0,
            )
        )
    return products


def build_missing_baseline_updates(products: Iterable[ProductRecord], current_prices: dict[str, float]) -> dict[str, float]:
    updates: dict[str, float] = {}
    for product in products:
        if product.baseline_price is not None:
            continue
        current = current_prices.get(product.product_id)
        if current is not None:
            updates[product.product_id] = current
    return updates


def _open_spreadsheet(service_account_file: str, sheet_id: str):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def load_products_from_sheet(
    service_account_file: str,
    sheet_id: str,
    worksheet_name: str = "products",
) -> list[ProductRecord]:
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    return parse_products(worksheet.get_all_records())


def apply_missing_baseline_updates(
    service_account_file: str,
    sheet_id: str,
    updates: dict[str, float],
    worksheet_name: str = "products",
) -> None:
    if not updates:
        return
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    rows = worksheet.get_all_records()
    for index, row in enumerate(rows, start=2):
        product_id = str(row.get("product_id", "")).strip()
        if product_id in updates:
            worksheet.update_cell(index, 6, updates[product_id])  # baseline_price column


def append_price_history_rows(
    service_account_file: str,
    sheet_id: str,
    rows: list[list],
    worksheet_name: str = "price_history",
) -> None:
    if not rows:
        return
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")


def append_url_candidate_rows(
    service_account_file: str,
    sheet_id: str,
    rows: list[list],
    worksheet_name: str = "url_candidates",
) -> None:
    if not rows:
        return
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=8)
        worksheet.append_row(
            [
                "run_ts",
                "product_id",
                "platform",
                "query",
                "candidate_url",
                "rank",
                "selected",
                "reason",
            ],
            value_input_option="USER_ENTERED",
        )
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")


def load_approved_urls(
    service_account_file: str,
    sheet_id: str,
    worksheet_name: str = "approved_urls",
) -> dict[tuple[str, str], str]:
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        return {}

    approved: dict[tuple[str, str], str] = {}
    for row in worksheet.get_all_records():
        approval = _as_text(row.get("approval", ""))
        if not _is_active(approval):
            continue
        product_id = _as_text(row.get("product_id", ""))
        platform = _as_text(row.get("platform", "")).lower()
        url = _as_text(row.get("approved_url", "")) or _as_text(row.get("product_url", ""))
        if not product_id or not platform or not url:
            continue
        approved[(product_id, platform)] = url
    return approved


def append_review_queue_rows(
    service_account_file: str,
    sheet_id: str,
    rows: list[list],
    worksheet_name: str = "approved_urls",
) -> None:
    if not rows:
        return
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=10)
        worksheet.append_row(
            [
                "run_ts",
                "product_id",
                "platform",
                "approved_url",
                "query",
                "rank",
                "source_reason",
                "validator_score",
                "validator_notes",
                "approval",
            ],
            value_input_option="USER_ENTERED",
        )
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")


def _is_reviewed_decision(value: str) -> bool:
    raw = _as_text(value).lower()
    return raw in {"true", "false", "1", "0", "yes", "no", "y", "n"}


def dedupe_review_queue_records(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best_by_key: dict[tuple[str, str, str], tuple[int, int, dict[str, str]]] = {}
    for idx, row in enumerate(rows):
        product_id = _as_text(row.get("product_id", ""))
        platform = _as_text(row.get("platform", "")).lower()
        approved_url = _as_text(row.get("approved_url", "")) or _as_text(row.get("product_url", ""))
        if not product_id or not platform or not approved_url:
            key = (f"__row__{idx}", "", "")
        else:
            key = (product_id, platform, approved_url)

        reviewed = 1 if _is_reviewed_decision(row.get("approval", "")) else 0
        previous = best_by_key.get(key)
        if previous is None or reviewed > previous[0] or (reviewed == previous[0] and idx > previous[1]):
            best_by_key[key] = (reviewed, idx, dict(row))

    kept = sorted(best_by_key.values(), key=lambda item: item[1])
    return [entry[2] for entry in kept]


def cleanup_review_queue(
    service_account_file: str,
    sheet_id: str,
    worksheet_name: str = "approved_urls",
    dry_run: bool = False,
) -> dict:
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except WorksheetNotFound:
        return {"status": "missing_worksheet", "worksheet": worksheet_name, "input_rows": 0, "kept_rows": 0, "removed_rows": 0}

    header = worksheet.row_values(1)
    input_rows = worksheet.get_all_records()
    deduped_rows = dedupe_review_queue_records(input_rows)
    removed_rows = len(input_rows) - len(deduped_rows)

    if not dry_run and removed_rows > 0:
        if not header:
            header = list(deduped_rows[0].keys()) if deduped_rows else []
        output = [header] + [[row.get(col, "") for col in header] for row in deduped_rows]
        worksheet.clear()
        worksheet.update("A1", output, value_input_option="USER_ENTERED")

    return {
        "status": "ok",
        "worksheet": worksheet_name,
        "input_rows": len(input_rows),
        "kept_rows": len(deduped_rows),
        "removed_rows": removed_rows,
        "dry_run": dry_run,
    }


def upsert_best_price_flags(
    service_account_file: str,
    sheet_id: str,
    best_by_product_id: dict[str, dict],
    worksheet_name: str = "products",
) -> None:
    if not best_by_product_id:
        return
    spreadsheet = _open_spreadsheet(service_account_file, sheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)

    header = worksheet.row_values(1)
    needed = ["best_price", "best_platform", "best_url", "last_checked"]
    missing = [name for name in needed if name not in header]
    if missing:
        base_col = len(header) + 1
        for offset, name in enumerate(missing):
            worksheet.update_cell(1, base_col + offset, name)
        header = worksheet.row_values(1)

    col_index = {name: header.index(name) + 1 for name in needed}
    rows = worksheet.get_all_records()
    updates: list[dict[str, list[list]]] = []
    for row_idx, row in enumerate(rows, start=2):
        product_id = str(row.get("product_id", "")).strip()
        best = best_by_product_id.get(product_id)
        if not best:
            continue
        updates.append(
            {
                "range": rowcol_to_a1(row_idx, col_index["best_price"]),
                "values": [[best.get("current_price", "")]],
            }
        )
        updates.append(
            {
                "range": rowcol_to_a1(row_idx, col_index["best_platform"]),
                "values": [[best.get("platform", "")]],
            }
        )
        updates.append(
            {
                "range": rowcol_to_a1(row_idx, col_index["best_url"]),
                "values": [[best.get("product_url", "")]],
            }
        )
        updates.append(
            {
                "range": rowcol_to_a1(row_idx, col_index["last_checked"]),
                "values": [[best.get("checked_at", "")]],
            }
        )
    if updates:
        worksheet.batch_update(updates, value_input_option="USER_ENTERED")
