#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.lib.email_renderer import render_digest_html
from tools.lib.gmail_sender import get_gmail_service, send_html_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Send price digest email")
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--client-secret", default="client_secret_desktop.json")
    parser.add_argument("--token-file", default="gmail_token.json")
    parser.add_argument("--data-file", help="JSON file with top_drops/all_items/coupons", default="")
    parser.add_argument("--bootstrap-oauth", action="store_true")
    args = parser.parse_args()

    service = get_gmail_service(args.client_secret, args.token_file)
    if args.bootstrap_oauth:
        print(json.dumps({"status": "oauth_ready", "token_file": args.token_file}))
        return

    payload = {"top_drops": [], "all_items": [], "coupons": []}
    if args.data_file:
        with open(args.data_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)

    html = render_digest_html(
        run_date=str(date.today()),
        top_drops=payload.get("top_drops", []),
        all_items=payload.get("all_items", []),
        coupons=payload.get("coupons", []),
    )
    result = send_html_email(
        service=service,
        recipient=args.recipient,
        subject=f"Daily Baby Price Alert - {date.today().isoformat()}",
        html_body=html,
    )
    print(json.dumps({"status": "sent", "message_id": result.get("id")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
