"""Gmail access: OAuth, searching, message parsing and labeling.

Only read and label operations are used; this module never sends, trashes or deletes.
"""

import base64
import os
from html.parser import HTMLParser
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from email_triage.config import Config
from email_triage.models import Email

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


class AuthError(RuntimeError):
    pass


def build_query(config: Config) -> str:
    # Gmail search refers to nested labels with "/" replaced by "-", lowercased.
    excluded = " ".join(
        f"-label:{label.replace('/', '-').lower()}" for label in config.all_labels
    )
    return f"in:inbox newer_than:{config.lookback_days}d {excluded}"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._chunks).split())


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode(
        "utf-8", errors="replace"
    )


def _find_part(part: dict, mime_type: str) -> str | None:
    if part.get("mimeType") == mime_type and not part.get("filename"):
        data = part.get("body", {}).get("data")
        if data:
            return _decode(data)
    for child in part.get("parts", []):
        found = _find_part(child, mime_type)
        if found:
            return found
    return None


def parse_message(raw: dict) -> Email:
    payload = raw.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    body = _find_part(payload, "text/plain")
    if not body:
        html = _find_part(payload, "text/html")
        body = _html_to_text(html) if html else ""
    body = body.strip() or raw.get("snippet", "")

    return Email(
        id=raw["id"],
        sender=headers.get("from", ""),
        subject=headers.get("subject", ""),
        date=headers.get("date", ""),
        body=body,
        list_unsubscribe=headers.get("list-unsubscribe"),
        label_ids=list(raw.get("labelIds", [])),
    )


def run_oauth_flow(credentials_path: Path, token_path: Path) -> None:
    """Interactive browser consent; saves a refresh token for unattended runs."""
    if not credentials_path.exists():
        raise AuthError(f"OAuth client file not found: {credentials_path}")
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds, token_path)


def _save_token(creds: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())
    os.chmod(token_path, 0o600)


def _load_credentials(token_path: Path) -> Credentials:
    if not token_path.exists():
        raise AuthError("Not authorized yet. Run `triage auth` first.")
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise AuthError("Stored token has no refresh token. Run `triage auth` again.")
    try:
        creds.refresh(Request())
    except RefreshError as e:
        raise AuthError(f"Token refresh failed ({e}). Run `triage auth` again.") from e
    _save_token(creds, token_path)
    return creds


class GmailClient:
    def __init__(self, service) -> None:
        self._service = service

    @classmethod
    def from_token(cls, token_path: Path) -> "GmailClient":
        creds = _load_credentials(token_path)
        return cls(build("gmail", "v1", credentials=creds, cache_discovery=False))

    def list_message_ids(self, query: str, max_results: int) -> list[str]:
        response = (
            self._service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        return [m["id"] for m in response.get("messages", [])]

    def get_email(self, message_id: str) -> Email:
        raw = (
            self._service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        return parse_message(raw)

    def ensure_labels(self, names: list[str]) -> dict[str, str]:
        """Return {label name: label id}, creating any labels that don't exist."""
        labels = self._service.users().labels()
        existing = {
            label["name"]: label["id"]
            for label in labels.list(userId="me").execute().get("labels", [])
        }
        for name in names:
            if name not in existing:
                created = labels.create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                ).execute()
                existing[name] = created["id"]
        return {name: existing[name] for name in names}

    def add_label(self, message_id: str, label_id: str) -> None:
        self._service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [label_id]}
        ).execute()
