"""
Loads settings from .env (secrets/credentials) and a YAML file
(the extraction schema and sync/schedule settings a user would actually
want to edit).
"""

import os
from dataclasses import dataclass

import yaml
from dotenv import load_dotenv


@dataclass
class Settings:
    # Secrets, from .env
    anthropic_api_key: str
    google_service_account_path: str
    gmail_credentials_path: str
    gmail_token_path: str
    imap_password: str

    # From YAML config
    field_schema: list[dict[str, str]]
    spreadsheet_id: str
    worksheet_name: str
    key_field: str
    schedule_interval_minutes: int
    source_type: str  # "gmail" | "imap"
    imap_host: str
    imap_port: int
    imap_username: str


def load_settings(yaml_path: str, env_path: str = ".env") -> Settings:
    load_dotenv(env_path)

    with open(yaml_path, "r") as f:
        raw = yaml.safe_load(f)

    sync_cfg = raw.get("sync", {})
    schedule_cfg = raw.get("schedule", {})
    source_cfg = raw.get("source", {})

    return Settings(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        google_service_account_path=os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "service_account.json"),
        gmail_credentials_path=os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        gmail_token_path=os.environ.get("GMAIL_TOKEN_PATH", "token.json"),
        imap_password=os.environ.get("IMAP_PASSWORD", ""),
        field_schema=raw["fields"],
        spreadsheet_id=sync_cfg.get("spreadsheet_id", ""),
        worksheet_name=sync_cfg.get("worksheet_name", "Extracted Emails"),
        key_field=sync_cfg.get("key_field", "message_id"),
        schedule_interval_minutes=schedule_cfg.get("interval_minutes", 60),
        source_type=source_cfg.get("type", "gmail"),
        imap_host=source_cfg.get("imap_host", ""),
        imap_port=source_cfg.get("imap_port", 993),
        imap_username=source_cfg.get("imap_username", ""),
    )
