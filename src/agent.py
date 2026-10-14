"""
The agent itself: fetch new emails -> extract structured fields with
Claude -> upsert into Google Sheets. State (last run time + processed
message IDs) is kept in a small local JSON file so the agent is safe to
re-run, restart, or recover from downtime without creating duplicates or
missing anything.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from src.config import Settings
from src.email_sources import EmailSource, RawEmail
from src.extraction import ClaudeExtractor
from src.sync import SheetsSync

logger = logging.getLogger(__name__)

STATE_PATH = "state/agent_state.json"


class MailToSheetAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.source: EmailSource = self._build_source()
        self.extractor = ClaudeExtractor(
            settings.anthropic_api_key, settings.field_schema, exclude_fields=[settings.key_field]
        )
        self.sync = SheetsSync(
            settings.google_service_account_path,
            settings.spreadsheet_id,
            settings.worksheet_name,
            settings.key_field,
        )
        self.field_order = [f["name"] for f in settings.field_schema]
        self.state = self._load_state()

    def _build_source(self) -> EmailSource:
        # Adapters are imported here, not at module load, so only the chosen
        # provider's dependencies are ever required (Gmail needs the Google
        # libraries, IMAP needs nothing beyond the standard library).
        if self.settings.source_type == "gmail":
            from src.email_sources.gmail_source import GmailSource

            return GmailSource(self.settings.gmail_credentials_path, self.settings.gmail_token_path)
        elif self.settings.source_type == "imap":
            from src.email_sources.imap_source import ImapSource

            return ImapSource(
                host=self.settings.imap_host,
                port=self.settings.imap_port,
                username=self.settings.imap_username,
                password=self.settings.imap_password,
            )
        raise ValueError(f"Unknown source type: {self.settings.source_type}")

    def _load_state(self) -> dict:
        if os.path.exists(STATE_PATH):
            with open(STATE_PATH, "r") as f:
                return json.load(f)
        return {"last_run_iso": None, "processed_message_ids": []}

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        # Cap the processed-ID list so this file doesn't grow forever —
        # only the most recent window is needed to catch duplicate fetches
        # from a provider's coarse-grained date filters.
        self.state["processed_message_ids"] = self.state["processed_message_ids"][-5000:]
        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def run_once(self) -> dict:
        """Runs a single fetch -> extract -> sync cycle. Returns a summary dict."""
        since_iso = self.state.get("last_run_iso")
        raw_emails = self.source.fetch_new(since_iso=since_iso)

        processed_ids = set(self.state.get("processed_message_ids", []))
        new_emails: list[RawEmail] = [e for e in raw_emails if e.message_id not in processed_ids]

        logger.info(
            "Fetched %d emails (%d new, %d already processed)",
            len(raw_emails), len(new_emails), len(raw_emails) - len(new_emails),
        )

        extracted_rows = []
        low_confidence_count = 0

        for raw_email in new_emails:
            result = self.extractor.extract(raw_email)
            if result is None:
                logger.warning("Skipping message_id=%s — extraction failed", raw_email.message_id)
                continue

            row = dict(result.fields)
            row[self.settings.key_field] = raw_email.message_id
            extracted_rows.append(row)

            if result.confidence == "low":
                low_confidence_count += 1

            processed_ids.add(raw_email.message_id)

        sync_summary = {"updated": 0, "appended": 0}
        if extracted_rows:
            sync_summary = self.sync.upsert_rows(self.field_order, extracted_rows)

        self.state["processed_message_ids"] = list(processed_ids)
        self.state["last_run_iso"] = datetime.now(timezone.utc).isoformat()
        self._save_state()

        summary = {
            "fetched": len(raw_emails),
            "new": len(new_emails),
            "extracted": len(extracted_rows),
            "low_confidence": low_confidence_count,
            **sync_summary,
        }
        logger.info("Run complete: %s", summary)
        return summary
