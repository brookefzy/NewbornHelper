#!/usr/bin/env python3
"""Deterministic tool for single price checks."""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.lib.price_collectors import collect_price


def main() -> None:
    parser = argparse.ArgumentParser(description="Check current price against target")
    parser.add_argument("--item-name", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--target-price", type=float, required=True)
    args = parser.parse_args()

    collect_result = collect_price(
        {
            "product_id": args.item_name,
            "platform": "generic",
            "product_url": args.source_url,
        }
    )

    current_price = collect_result["current_price"]
    result = {
        "item_name": args.item_name,
        "source_url": args.source_url,
        "current_price": current_price,
        "target_price": args.target_price,
        "triggered": current_price is not None and current_price <= args.target_price,
        "status": collect_result["status"],
        "error": collect_result["error"],
    }
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
