"""Structured logging helpers."""

from __future__ import annotations

import sys
from datetime import datetime


def log(tag: str, message: str) -> None:
    line = f"[{tag}] {message}"
    print(line)
    sys.stdout.flush()


def log_ts(tag: str, message: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    log(tag, f"{ts} {message}")
