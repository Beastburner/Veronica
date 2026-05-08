from __future__ import annotations

import re
from typing import Any

from app.db import get_db, utcnow


def _normalize_phone(phone: str) -> str:
    """Strip spaces/dashes, keep leading +."""
    p = phone.strip()
    if not p:
        return ""
    has_plus = p.startswith("+")
    digits = re.sub(r"[^\d]", "", p)
    return ("+" + digits) if has_plus else digits


def upsert_contact(name: str, email: str, source: str = "auto", phone: str = "") -> dict[str, Any]:
    """Insert or bump interaction count for a contact."""
    name = name.strip()
    email = email.strip().lower()
    phone = _normalize_phone(phone)
    if not name or not email or "@" not in email:
        return {}
    now = utcnow()
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO contacts (name, email, phone, source, interaction_count, last_seen, created_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                interaction_count = interaction_count + 1,
                last_seen = excluded.last_seen,
                name = CASE WHEN excluded.name != '' THEN excluded.name ELSE name END,
                phone = CASE WHEN excluded.phone != '' THEN excluded.phone ELSE phone END
            """,
            (name, email, phone, source, now, now),
        )
    return {"name": name, "email": email, "phone": phone}


def find_contacts(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fuzzy name/email/phone search — returns best matches."""
    q = query.strip().lower()
    if not q:
        return []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT name, email, phone, interaction_count, last_seen
            FROM contacts
            WHERE lower(name) LIKE ? OR lower(email) LIKE ? OR phone LIKE ?
            ORDER BY interaction_count DESC, last_seen DESC
            LIMIT ?
            """,
            (f"%{q}%", f"%{q}%", f"%{q}%", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def resolve_name_to_email(name: str) -> str | None:
    """Return the best-matching email for a display name, or None if not found."""
    matches = find_contacts(name, limit=1)
    return matches[0]["email"] if matches else None


def resolve_name_to_phone(name: str) -> str | None:
    """Return the best-matching phone number for a display name, or None if not found."""
    matches = find_contacts(name, limit=3)
    for m in matches:
        phone = (m.get("phone") or "").strip()
        if phone:
            return phone
    return None


def list_contacts(limit: int = 100) -> list[dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT name, email, phone, source, interaction_count, last_seen FROM contacts "
            "ORDER BY interaction_count DESC, last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Email header parsing ──────────────────────────────────────────────────────

_ADDR_RE = re.compile(r'"?([^"<,]+)"?\s*<([^>]+)>|([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)')


def extract_contacts_from_headers(headers: list[dict]) -> list[tuple[str, str]]:
    """Pull (name, email) pairs from Gmail message headers."""
    results: list[tuple[str, str]] = []
    for h in headers:
        name_h = h.get("name", "")
        if name_h not in ("From", "To", "Cc"):
            continue
        value = h.get("value", "")
        for m in _ADDR_RE.finditer(value):
            if m.group(1) and m.group(2):
                results.append((m.group(1).strip().strip('"'), m.group(2).strip().lower()))
            elif m.group(3):
                results.append(("", m.group(3).strip().lower()))
    return results


def ingest_gmail_headers(headers: list[dict], source: str = "gmail") -> None:
    for name, email in extract_contacts_from_headers(headers):
        upsert_contact(name or email.split("@")[0], email, source)


def ingest_calendar_attendees(attendees: list[str | dict], source: str = "calendar") -> None:
    for a in attendees:
        if isinstance(a, dict):
            email = a.get("email", "").strip().lower()
            name = a.get("displayName") or a.get("name") or email.split("@")[0]
        else:
            email = str(a).strip().lower()
            name = email.split("@")[0]
        if email and "@" in email:
            upsert_contact(name, email, source)


def resolve_attendees(raw: list[str]) -> list[str]:
    """
    For each item in raw attendee list:
    - If it looks like an email, keep it.
    - Otherwise treat it as a name and try to resolve via contacts DB.
    Returns a list of emails (unresolved names are kept as-is so the LLM can warn).
    """
    out: list[str] = []
    for item in raw:
        item = item.strip()
        if not item:
            continue
        if "@" in item:
            out.append(item.lower())
        else:
            email = resolve_name_to_email(item)
            out.append(email if email else item)
    return out
