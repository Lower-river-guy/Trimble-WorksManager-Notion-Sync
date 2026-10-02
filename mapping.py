"""Field mapping and normalization helpers."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


def extract_project_number(project_name: str) -> str:
    """Leading numeric project number from WorksManager project name."""
    match = re.match(r"\s*(\d{3,5})\b", project_name or "")
    return match.group(1) if match else ""


def plain(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_iso_timestamp(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "." in text:
        head, tail = text.split(".", 1)
        for i, ch in enumerate(tail):
            if not ch.isdigit():
                text = f"{head}.{tail[: min(i, 6)]}{tail[i:]}"
                break
        else:
            text = f"{head}.{tail[:6]}"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return text


def design_summary(designs: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for design in designs:
        if not isinstance(design, dict):
            continue
        name = plain(design.get("name"))
        ver = design.get("version")
        status = plain(design.get("status"))
        bits = [name]
        if ver not in (None, ""):
            bits.append(f"v{ver}")
        if status:
            bits.append(status)
        line = " | ".join(x for x in bits if x)
        if line:
            lines.append(line)
    return "\n".join(lines)


def assigned_design_summary(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for design in items:
        if not isinstance(design, dict):
            continue
        name = plain(design.get("name") or design.get("designName") or design.get("id"))
        ver = design.get("version")
        suffix = f" | v{ver}" if ver not in (None, "") else ""
        lines.append(f"{name}{suffix}")
    return "\n".join(lines)


def coordinate_summary(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        did = plain(row.get("deviceId") or row.get("id"))
        lat = row.get("lat")
        lon = row.get("lon")
        reported = plain(row.get("lastReportedAt"))
        source = plain(row.get("correctionSource"))
        lines.append(
            f"{did} | lat={lat} | lon={lon} | correction={source} | reported={reported}"
        )
    return "\n".join(lines)


def coordinate_system_summary(project: dict[str, Any], detail: dict[str, Any] | None) -> str:
    parts: list[str] = []
    for key in (
        "coordinateSystem",
        "coordinateSystemName",
        "coordinateSystemDescription",
        "crsName",
        "name",
        "description",
    ):
        val = project.get(key)
        if val:
            parts.append(f"{key}={plain(val)}")
    if detail:
        for key, val in detail.items():
            if key in {"links", "id"}:
                continue
            if val not in (None, "", [], {}):
                parts.append(f"{key}={plain(val)}")
    return "\n".join(parts)


def join_project_labels(pairs: list[tuple[str, str]]) -> tuple[str, str]:
    """Join multiple project assignments for text fields."""
    if not pairs:
        return "", ""
    names = [name for _, name in pairs if name]
    ids = [pid for pid, _ in pairs if pid]
    return " / ".join(names), " / ".join(ids)
