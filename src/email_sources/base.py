"""
Shared data model and abstract interface for email sources.

Any inbox provider (Gmail, generic IMAP, eventually Outlook/Graph) plugs in
by implementing EmailSource.fetch_new(). The rest of the agent only ever
talks to this interface, so swapping providers never touches extraction
or sync code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class RawEmail:
    """Provider-agnostic representation of a single email."""
    message_id: str          # Stable unique ID — used as the dedupe / upsert key downstream
    sender_name: str
    sender_email: str
    subject: str
    date_iso: str             # ISO 8601 timestamp
    body_text: str            # Plain-text body (HTML already stripped)
    has_attachment: bool


class EmailSource(ABC):
    """Interface every email provider adapter must implement."""

    @abstractmethod
    def fetch_new(self, since_iso: Optional[str] = None) -> list[RawEmail]:
        """
        Return emails received after `since_iso` (ISO 8601), newest last.
        If `since_iso` is None, implementations should apply a sane default
        (e.g. last 24 hours) rather than pulling an entire mailbox.
        """
        raise NotImplementedError
