"""
Google Sheets sync — the core of "update or add new lines in the spreadsheet."

Every row is keyed by a unique field (message_id by default). On each run:
  - if a key already exists in the sheet, that row is updated in place
  - if it's new, it's appended

This makes the whole pipeline idempotent: re-running against the same
emails, or catching up after downtime, never creates duplicate rows.
"""

import logging
from typing import Any

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsSync:
    def __init__(self, service_account_path: str, spreadsheet_id: str, worksheet_name: str, key_field: str):
        creds = Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
        self.service = build("sheets", "v4", credentials=creds)
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self.key_field = key_field

    def upsert_rows(self, field_order: list[str], rows: list[dict[str, Any]]) -> dict[str, int]:
        """Returns {"updated": n, "appended": n} for logging/notifications."""
        self._ensure_header(field_order)
        existing_key_to_row = self._read_existing_keys(field_order)

        updates = 0
        to_append = []

        for row in rows:
            key_value = str(row.get(self.key_field, ""))
            values = [str(row.get(f, "None")) for f in field_order]

            if key_value in existing_key_to_row:
                row_number = existing_key_to_row[key_value]
                self._update_row(row_number, values)
                updates += 1
            else:
                to_append.append(values)

        if to_append:
            self._append_rows(to_append)

        return {"updated": updates, "appended": len(to_append)}

    def _ensure_header(self, field_order: list[str]) -> None:
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=f"{self.worksheet_name}!A1:1"
        ).execute()
        existing_header = result.get("values", [[]])
        if not existing_header or not existing_header[0]:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.worksheet_name}!A1",
                valueInputOption="RAW",
                body={"values": [field_order]},
            ).execute()

    def _read_existing_keys(self, field_order: list[str]) -> dict[str, int]:
        key_col_index = field_order.index(self.key_field)
        key_col_letter = chr(ord("A") + key_col_index)

        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!{key_col_letter}2:{key_col_letter}",
        ).execute()

        key_map: dict[str, int] = {}
        for i, row in enumerate(result.get("values", []), start=2):  # data starts row 2 (row 1 = header)
            if row:
                key_map[row[0]] = i
        return key_map

    def _update_row(self, row_number: int, values: list[str]) -> None:
        last_col = chr(ord("A") + len(values) - 1)
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A{row_number}:{last_col}{row_number}",
            valueInputOption="RAW",
            body={"values": [values]},
        ).execute()

    def _append_rows(self, rows: list[list[str]]) -> None:
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"{self.worksheet_name}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
