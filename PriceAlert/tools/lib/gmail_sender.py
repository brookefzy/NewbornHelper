from __future__ import annotations

import base64
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def load_gmail_credentials(client_secret_file: str, token_file: str) -> Credentials:
    token_path = Path(token_file)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, GMAIL_SCOPES)
        creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def get_gmail_service(client_secret_file: str, token_file: str):
    creds = load_gmail_credentials(client_secret_file, token_file)
    return build("gmail", "v1", credentials=creds)


def send_html_email(service, recipient: str, subject: str, html_body: str) -> dict:
    message = MIMEText(html_body, "html")
    message["to"] = recipient
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    payload = {"raw": raw}
    return service.users().messages().send(userId="me", body=payload).execute()
