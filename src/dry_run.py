"""
Dry-run mode: runs the extraction step against synthetic sample emails and
prints the result to the console. No Gmail, IMAP, or Google Sheets
credentials required — only ANTHROPIC_API_KEY.

This exists so anyone evaluating this repo can see the agent actually
work in about 30 seconds, without setting up OAuth or a service account
first.
"""

import json
import logging

from src.config import load_settings
from src.email_sources.base import RawEmail
from src.extraction import ClaudeExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_sample_emails(path: str = "sample_data/sample_emails.json") -> list[RawEmail]:
    with open(path, "r") as f:
        raw = json.load(f)
    return [RawEmail(**item) for item in raw]


def main():
    settings = load_settings(yaml_path="config/schema.example.yaml")
    # message_id is never asked of the model — it's system metadata the
    # email content doesn't contain. It's injected below after extraction,
    # same as the live pipeline in agent.py does.
    extractor = ClaudeExtractor(
        settings.anthropic_api_key, settings.field_schema, exclude_fields=[settings.key_field]
    )
    samples = load_sample_emails()

    print(f"\nRunning extraction against {len(samples)} sample emails...\n")

    for email in samples:
        result = extractor.extract(email)
        print(f"--- {email.subject} ---")
        if result is None:
            print("  Extraction failed.\n")
            continue

        fields = {settings.key_field: getattr(email, settings.key_field), **result.fields}
        for key, value in fields.items():
            print(f"  {key}: {value}")
        print(f"  confidence: {result.confidence}\n")


if __name__ == "__main__":
    main()
