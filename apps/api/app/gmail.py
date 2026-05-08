from __future__ import annotations

import base64
import email.message
import json
import logging
from typing import Any

log = logging.getLogger("veronica.gmail")

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _get_service():
    try:
        from google.oauth2.credentials import Credentials  # type: ignore[import]
        from googleapiclient.discovery import build  # type: ignore[import]
        from app.oauth_store import load_oauth_token

        token_json = load_oauth_token("google")
        if not token_json:
            return None
        creds = Credentials.from_authorized_user_info(json.loads(token_json), GMAIL_SCOPES)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception as exc:
        log.warning("Failed to build Gmail service: %s", exc)
        return None


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(errors="replace")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode(errors="replace")
    return ""


def _make_raw(to: str, subject: str, body: str) -> str:
    from app.config import settings
    name = settings.sender_name
    msg = email.message.EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    signed_body = f"{body}\n\n-- \n{name}"
    msg.set_content(signed_body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


async def list_inbox(max_results: int = 10) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "list_inbox", "ok": False, "error": "Gmail not connected"}
    try:
        result = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
            .execute()
        )
        items = []
        for msg in result.get("messages", []):
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = detail.get("payload", {}).get("headers", [])
            try:
                from app.contacts import ingest_gmail_headers
                ingest_gmail_headers(headers)
            except Exception:
                pass
            items.append(
                {
                    "id": msg["id"],
                    "from": _header(headers, "From"),
                    "subject": _header(headers, "Subject"),
                    "date": _header(headers, "Date"),
                    "snippet": detail.get("snippet", ""),
                    "unread": "UNREAD" in detail.get("labelIds", []),
                }
            )
        return {"tool": "list_inbox", "ok": True, "result": items}
    except Exception as exc:
        return {"tool": "list_inbox", "ok": False, "error": str(exc)}


async def read_email(message_id: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "read_email", "ok": False, "error": "Gmail not connected"}
    try:
        detail = (
            service.users().messages().get(userId="me", id=message_id, format="full").execute()
        )
        headers = detail.get("payload", {}).get("headers", [])
        body = _decode_body(detail.get("payload", {}))
        try:
            from app.contacts import ingest_gmail_headers
            ingest_gmail_headers(headers)
        except Exception:
            pass
        return {
            "tool": "read_email",
            "ok": True,
            "result": {
                "id": message_id,
                "from": _header(headers, "From"),
                "to": _header(headers, "To"),
                "subject": _header(headers, "Subject"),
                "date": _header(headers, "Date"),
                "body": body[:3000],
            },
        }
    except Exception as exc:
        return {"tool": "read_email", "ok": False, "error": str(exc)}


async def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "send_email", "ok": False, "error": "Gmail not connected"}
    try:
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": _make_raw(to, subject, body)})
            .execute()
        )
        return {
            "tool": "send_email",
            "ok": True,
            "result": {"id": result.get("id"), "to": to, "subject": subject},
        }
    except Exception as exc:
        return {"tool": "send_email", "ok": False, "error": str(exc)}


async def draft_email(to: str, subject: str, body: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "draft_email", "ok": False, "error": "Gmail not connected"}
    try:
        result = (
            service.users()
            .drafts()
            .create(userId="me", body={"message": {"raw": _make_raw(to, subject, body)}})
            .execute()
        )
        return {
            "tool": "draft_email",
            "ok": True,
            "result": {"id": result.get("id"), "to": to, "subject": subject},
        }
    except Exception as exc:
        return {"tool": "draft_email", "ok": False, "error": str(exc)}


async def search_email(query: str) -> dict[str, Any]:
    service = _get_service()
    if not service:
        return {"tool": "search_email", "ok": False, "error": "Gmail not connected"}
    try:
        result = (
            service.users().messages().list(userId="me", q=query, maxResults=5).execute()
        )
        items = []
        for msg in result.get("messages", []):
            detail = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = detail.get("payload", {}).get("headers", [])
            items.append(
                {
                    "id": msg["id"],
                    "from": _header(headers, "From"),
                    "subject": _header(headers, "Subject"),
                    "date": _header(headers, "Date"),
                    "snippet": detail.get("snippet", ""),
                }
            )
        return {"tool": "search_email", "ok": True, "query": query, "result": items}
    except Exception as exc:
        return {"tool": "search_email", "ok": False, "error": str(exc)}
