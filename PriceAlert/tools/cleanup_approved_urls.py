#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.lib.config import load_settings
from tools.lib.sheets_registry import cleanup_review_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Deduplicate approved_urls review queue rows")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing to sheet")
    args = parser.parse_args()

    settings = load_settings()
    result = cleanup_review_queue(
        service_account_file=settings.google_service_account_file,
        sheet_id=settings.price_sheet_id,
        worksheet_name=settings.approved_urls_worksheet_name,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()

