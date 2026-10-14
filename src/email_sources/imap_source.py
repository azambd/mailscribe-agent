"""
Generic IMAP email source — works with any provider that exposes IMAP
(Outlook/Office365, Yahoo, iCloud, self-hosted mail, etc). This is what
makes the agent usable by "anyone," not just Gmail users.
"""

import email
import imaplib
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from typing import Optional

from .base import EmailSource, RawEmail


class ImapSource(EmailSource):
    def __init__(self, host: str, port: int, username: str, password: str, mailbox: str = "INBOX"):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.mailbox = mailbox

    def fetch_new(self, since_iso: Optional[str] = None) -> list[RawEmail]:
        conn = imaplib.IMAP4_SSL(self.host, self.port)
        try:
            conn.login(self.username, self.password)
            conn.select(self.mailbox)

            search_criteria = "ALL"
            if since_iso:
                since_dt = datetime.fromisoformat(since_iso)
                # IMAP SINCE is date-only granularity, same overlap caveat
                # as the Gmail adapter — dedupe happens in agent.py.
                search_criteria = f'(SINCE "{since_dt.strftime("%d-%b-%Y")}")'

            status, message_ids = conn.search(None, search_criteria)
            if status != "OK":
                return []

            emails: list[RawEmail] = []
            for msg_id in message_ids[0].split():
                status, msg_data = conn.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                raw_message = email.message_from_bytes(msg_data[0][1])
                emails.append(self._parse_message(raw_message, msg_id.decode()))

            return emails
        finally:
            conn.logout()

    def _parse_message(self, msg, fallback_id: str) -> RawEmail:
        message_id = msg.get("Message-ID", fallback_id).strip()
        subject = self._decode_header(msg.get("Subject", "(no subject)"))
        sender_name, sender_email = self._split_sender(msg.get("From", ""))

        try:
            date_iso = parsedate_to_datetime(msg.get("Date")).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            date_iso = datetime.now(timezone.utc).isoformat()

        body_text = self._extract_body(msg)
        has_attachment = self._has_attachment(msg)

        return RawEmail(
            message_id=message_id,
            sender_name=sender_name,
            sender_email=sender_email,
            subject=subject,
            date_iso=date_iso,
            body_text=body_text,
            has_attachment=has_attachment,
        )

    @staticmethod
    def _decode_header(raw: str) -> str:
        parts = decode_header(raw)
        decoded = ""
        for text, enc in parts:
            if isinstance(text, bytes):
                decoded += text.decode(enc or "utf-8", errors="replace")
            else:
                decoded += text
        return decoded

    @staticmethod
    def _split_sender(raw: str) -> tuple[str, str]:
        if "<" in raw and ">" in raw:
            name = raw.split("<")[0].strip().strip('"')
            email_addr = raw.split("<")[1].split(">")[0].strip()
            return name or email_addr, email_addr
        return raw, raw

    @staticmethod
    def _extract_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in disposition:
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            return ""
        else:
            payload = msg.get_payload(decode=True)
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace") if payload else ""

    @staticmethod
    def _has_attachment(msg) -> bool:
        if not msg.is_multipart():
            return False
        for part in msg.walk():
            if part.get("Content-Disposition", "").startswith("attachment"):
                return True
        return False
