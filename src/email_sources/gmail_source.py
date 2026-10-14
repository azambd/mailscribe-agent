"""
Gmail API email source.

Requires an OAuth client (credentials.json from Google Cloud Console,
Gmail API enabled) and a one-time browser login to produce token.json.
See README.md for the exact setup steps.
"""

import base64
import os
from datetime import datetime, timezone
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .base import EmailSource, RawEmail

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailSource(EmailSource):
    def __init__(self, credentials_path: str, token_path: str):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._service = self._authenticate()

    def _authenticate(self):
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(self.token_path, "w") as f:
                f.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    def fetch_new(self, since_iso: Optional[str] = None) -> list[RawEmail]:
        query = "in:inbox"
        if since_iso:
            since_dt = datetime.fromisoformat(since_iso)
            # Gmail search only supports day-level granularity for `after:`,
            # so this may re-fetch a few hours of overlap — the agent's own
            # message_id dedupe (see agent.py) is what actually guarantees
            # no duplicate rows, not this query.
            query += f" after:{int(since_dt.timestamp())}"

        results = self._service.users().messages().list(userId="me", q=query, maxResults=50).execute()
        message_refs = results.get("messages", [])

        emails: list[RawEmail] = []
        for ref in message_refs:
            msg = self._service.users().messages().get(
                userId="me", id=ref["id"], format="full"
            ).execute()
            emails.append(self._parse_message(msg))

        return emails

    def _parse_message(self, msg: dict) -> RawEmail:
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        sender_raw = headers.get("from", "")
        sender_name, sender_email = self._split_sender(sender_raw)

        date_iso = datetime.fromtimestamp(
            int(msg["internalDate"]) / 1000, tz=timezone.utc
        ).isoformat()

        body_text = self._extract_body(msg["payload"])
        has_attachment = self._has_attachment(msg["payload"])

        return RawEmail(
            message_id=msg["id"],
            sender_name=sender_name,
            sender_email=sender_email,
            subject=headers.get("subject", "(no subject)"),
            date_iso=date_iso,
            body_text=body_text,
            has_attachment=has_attachment,
        )

    @staticmethod
    def _split_sender(raw: str) -> tuple[str, str]:
        if "<" in raw and ">" in raw:
            name = raw.split("<")[0].strip().strip('"')
            email = raw.split("<")[1].split(">")[0].strip()
            return name or email, email
        return raw, raw

    def _extract_body(self, payload: dict) -> str:
        if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
            return self._decode(payload["body"]["data"])

        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                return self._decode(part["body"]["data"])
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/html" and "data" in part.get("body", {}):
                # Fall back to HTML, extraction step is tolerant of markup
                return self._decode(part["body"]["data"])
        return ""

    @staticmethod
    def _decode(data: str) -> str:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")

    @staticmethod
    def _has_attachment(payload: dict) -> bool:
        for part in payload.get("parts", []):
            if part.get("filename"):
                return True
        return False
