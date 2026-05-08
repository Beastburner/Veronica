from __future__ import annotations

"""
news.py — RSS news digest module for Veronica AI assistant.

Tables used:
    rss_feeds(id, title, url, category, created_at)

Uses only stdlib: urllib.request + xml.etree.ElementTree.
Supports RSS 2.0 and Atom feeds.
"""

import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from typing import Any

from app.db import get_db, utcnow


# ---------------------------------------------------------------------------
# Namespace helpers
# ---------------------------------------------------------------------------

_ATOM_NS = "http://www.w3.org/2005/Atom"

_DEFAULT_FEEDS: list[tuple[str, str, str]] = [
    ("Hacker News", "https://news.ycombinator.com/rss", "tech"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "tech"),
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "general"),
    ("ESPN F1", "https://www.espn.com/espn/rss/f1/news", "sports"),
]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def _seed_default_feeds(db: Any) -> None:
    """Insert default feeds if the table is empty."""
    count = db.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
    if count == 0:
        now = utcnow()
        for title, url, category in _DEFAULT_FEEDS:
            db.execute(
                "INSERT INTO rss_feeds (title, url, category, created_at) VALUES (?, ?, ?, ?)",
                (title, url, category, now),
            )
        db.commit()


# ---------------------------------------------------------------------------
# Feed management
# ---------------------------------------------------------------------------

def add_feed(url: str, title: str = "", category: str = "general") -> dict[str, Any]:
    """Add an RSS/Atom feed URL to the database and return the new row."""
    now = utcnow()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO rss_feeds (title, url, category, created_at) VALUES (?, ?, ?, ?)",
            (title or url, url, category, now),
        )
        db.commit()
        feed_id = cur.lastrowid
        row = db.execute("SELECT * FROM rss_feeds WHERE id = ?", (feed_id,)).fetchone()
    return _row_to_dict(row)


def list_feeds() -> list[dict[str, Any]]:
    """Return all stored feeds. Seeds defaults if the table is empty."""
    with get_db() as db:
        _seed_default_feeds(db)
        rows = db.execute(
            "SELECT * FROM rss_feeds ORDER BY created_at ASC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def remove_feed(feed_id: int) -> bool:
    """Delete a feed by ID. Returns True if a row was deleted."""
    with get_db() as db:
        cur = db.execute("DELETE FROM rss_feeds WHERE id = ?", (feed_id,))
        db.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _text(element: ET.Element | None) -> str:
    """Safely extract stripped text from an Element."""
    if element is None:
        return ""
    return (element.text or "").strip()


def _parse_rss(root: ET.Element) -> list[dict[str, Any]]:
    """Parse an RSS 2.0 document."""
    items: list[dict[str, Any]] = []
    channel = root.find("channel")
    if channel is None:
        return items
    for item in channel.findall("item"):
        title = _text(item.find("title"))
        link_el = item.find("link")
        # RSS <link> is sometimes CDATA stored as text, sometimes tail
        link = _text(link_el) if link_el is not None else ""
        summary = _text(item.find("description"))
        published = _text(item.find("pubDate"))
        items.append(
            {"title": title, "link": link, "summary": summary, "published": published}
        )
    return items


def _parse_atom(root: ET.Element) -> list[dict[str, Any]]:
    """Parse an Atom feed document."""
    ns = _ATOM_NS
    items: list[dict[str, Any]] = []
    for entry in root.findall(f"{{{ns}}}entry"):
        title = _text(entry.find(f"{{{ns}}}title"))
        # Atom <link> uses href attribute
        link_el = entry.find(f"{{{ns}}}link")
        link = (link_el.get("href") or "").strip() if link_el is not None else ""
        summary_el = entry.find(f"{{{ns}}}summary") or entry.find(
            f"{{{ns}}}content"
        )
        summary = _text(summary_el)
        published = _text(
            entry.find(f"{{{ns}}}published") or entry.find(f"{{{ns}}}updated")
        )
        items.append(
            {"title": title, "link": link, "summary": summary, "published": published}
        )
    return items


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_feed(url: str) -> list[dict[str, Any]]:
    """
    Fetch and parse a single RSS/Atom feed URL.
    Returns a list of article dicts: {title, link, summary, published}.
    Returns an empty list on any HTTP or parse error.
    """
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError):
        return []

    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    # Detect feed type by root tag
    tag = root.tag
    if tag == "rss" or (tag == "channel"):
        return _parse_rss(root)
    if tag == f"{{{_ATOM_NS}}}feed" or tag == "feed":
        return _parse_atom(root)
    # Try both as fallback
    items = _parse_rss(root)
    if not items:
        items = _parse_atom(root)
    return items


def fetch_all_feeds(limit_per_feed: int = 5) -> list[dict[str, Any]]:
    """
    Fetch all stored feeds and return a combined list of articles,
    capped at limit_per_feed articles per feed.
    """
    feeds = list_feeds()
    all_items: list[dict[str, Any]] = []
    for feed in feeds:
        items = fetch_feed(feed["url"])
        for item in items[:limit_per_feed]:
            item["feed_title"] = feed["title"]
            item["feed_category"] = feed["category"]
            all_items.append(item)
    return all_items


def get_digest(limit_per_feed: int = 3) -> dict[str, Any]:
    """
    Return a digest dict: {feeds: [articles...], total: int, fetched_at: str}.
    """
    articles = fetch_all_feeds(limit_per_feed=limit_per_feed)
    return {
        "feeds": articles,
        "total": len(articles),
        "fetched_at": utcnow(),
    }
