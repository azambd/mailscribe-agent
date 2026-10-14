"""
Only the provider-agnostic base types are imported here.

The Gmail and IMAP adapters are deliberately NOT imported at package load.
Gmail pulls in the Google client libraries, and importing them eagerly
meant that even dry-run mode (which never touches Gmail) crashed or
printed Google deprecation warnings when those libraries were missing or
outdated. Adapters are imported on demand in agent.py instead:

    from src.email_sources.gmail_source import GmailSource
    from src.email_sources.imap_source import ImapSource
"""

from .base import EmailSource, RawEmail

__all__ = ["EmailSource", "RawEmail"]
