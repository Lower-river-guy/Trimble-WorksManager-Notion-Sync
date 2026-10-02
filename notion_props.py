"""Notion property builders and readers."""

from __future__ import annotations

import json
from typing import Any

from mapping import plain


def rich_text(value: Any) -> dict[str, Any]:
    text = plain(value)
    if not text:
        return {"rich_text": []}
    chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
    return {
        "rich_text": [
            {"type": "text", "text": {"content": chunk}} for chunk in chunks[:50]
        ]
    }


def title(value: Any) -> dict[str, Any]:
    text = plain(value)[:1900] or "(Unnamed)"
    return {"title": [{"type": "text", "text": {"content": text}}]}


def number(value: Any) -> dict[str, Any]:
    try:
        if value is None or value == "":
            return {"number": None}
        return {"number": float(value)}
    except Exception:
        return {"number": None}


def date_prop(value: Any) -> dict[str, Any]:
    if not value:
        return {"date": None}
    return {"date": {"start": str(value)}}


def read_rich_text(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    chunks = prop.get("rich_text") or []
    parts: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("type") == "text":
            parts.append(str(chunk.get("text", {}).get("content") or ""))
        else:
            parts.append(plain(chunk.get("plain_text")))
    return "".join(parts).strip()


def read_title(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    chunks = prop.get("title") or []
    parts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            parts.append(str(chunk.get("plain_text") or chunk.get("text", {}).get("content") or ""))
    return "".join(parts).strip()


def read_number(prop: dict[str, Any] | None) -> float | None:
    if not isinstance(prop, dict):
        return None
    val = prop.get("number")
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


def read_date(prop: dict[str, Any] | None) -> str | None:
    if not isinstance(prop, dict):
        return None
    date_obj = prop.get("date")
    if not isinstance(date_obj, dict):
        return None
    start = date_obj.get("start")
    return str(start) if start else None


def properties_equal(
    existing: dict[str, Any],
    desired: dict[str, Any],
    *,
    keys: tuple[str, ...],
) -> bool:
    for key in keys:
        if normalize_property(existing.get(key)) != normalize_property(desired.get(key)):
            return False
    return True


def normalize_property(prop: dict[str, Any] | None) -> str:
    if not isinstance(prop, dict):
        return ""
    if "title" in prop:
        return read_title(prop)
    if "rich_text" in prop:
        return read_rich_text(prop)
    if "number" in prop:
        val = read_number(prop)
        return "" if val is None else str(val)
    if "date" in prop:
        return read_date(prop) or ""
    return json.dumps(prop, sort_keys=True)
