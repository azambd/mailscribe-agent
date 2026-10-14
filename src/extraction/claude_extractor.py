"""
Extraction engine — takes a raw email plus a user-defined field schema and
returns a clean dict of extracted values using Claude.

The schema is entirely config-driven (see config/schema.example.yaml), so
this same code extracts invoice data, support-ticket data, or lead data
just by changing the YAML — nothing here is hardcoded to one use case.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from src.email_sources.base import RawEmail

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_BODY_CHARS = 6000  # keep prompts small and cheap; emails rarely need more context than this


@dataclass
class ExtractionResult:
    fields: dict[str, Any]
    confidence: str          # "high" | "low" — low confidence rows get flagged, never silently dropped
    raw_model_output: str


class ClaudeExtractor:
    def __init__(self, api_key: str, field_schema: list[dict[str, str]], exclude_fields: Optional[list[str]] = None):
        """
        exclude_fields: field names to leave out of what Claude is asked to
        produce — typically the sync key_field (e.g. message_id), which is
        system metadata the email content never actually contains. Asking
        the model to "extract" it just produces a confident-looking guess
        or an honest "None"; either way it's not the model's job. The
        caller (agent.py / dry_run.py) injects the real value afterward.
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        exclude = set(exclude_fields or [])
        self.field_schema = [f for f in field_schema if f["name"] not in exclude]
        self._system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        field_lines = "\n".join(
            f'- "{f["name"]}": {f["description"]}' for f in self.field_schema
        )
        field_names = [f["name"] for f in self.field_schema]

        return (
            "You extract structured data from a single email into JSON.\n\n"
            f"Extract exactly these fields:\n{field_lines}\n\n"
            "Rules:\n"
            "- Return ONLY a JSON object, no prose, no markdown fences.\n"
            f"- The JSON must have exactly these keys: {field_names}\n"
            "- If a field genuinely isn't present in the email, use \"None\" as the value. "
            "Never invent or guess a value that isn't supported by the email content.\n"
            "- Also include a \"_confidence\" key set to \"high\" or \"low\". Use \"low\" when "
            "the email is ambiguous, mostly boilerplate, or you had to guess at more than one field."
        )

    def extract(self, raw_email: RawEmail) -> Optional[ExtractionResult]:
        body = raw_email.body_text[:MAX_BODY_CHARS]

        user_message = (
            f"From: {raw_email.sender_name} <{raw_email.sender_email}>\n"
            f"Date: {raw_email.date_iso}\n"
            f"Subject: {raw_email.subject}\n"
            f"Has attachment: {raw_email.has_attachment}\n\n"
            f"Body:\n{body}"
        )

        try:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text.strip()
            parsed = self._parse_json(raw_text)
            if parsed is None:
                logger.warning("Extraction returned non-JSON output for message_id=%s", raw_email.message_id)
                return None

            confidence = parsed.pop("_confidence", "low")
            return ExtractionResult(fields=parsed, confidence=confidence, raw_model_output=raw_text)

        except anthropic.APIError as e:
            logger.error("Claude API error for message_id=%s: %s", raw_email.message_id, e)
            return None

    @staticmethod
    def _parse_json(text: str) -> Optional[dict[str, Any]]:
        # Strip accidental markdown fences — models sometimes add them
        # despite instructions not to.
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            return None
