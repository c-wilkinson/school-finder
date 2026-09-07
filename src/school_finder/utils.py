"""Small shared utilities with no dependency on the data or presentation layers."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone


def log(message: str) -> None:
    print(message, file=sys.stderr)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalise_postcode(postcode: str) -> str:
    return re.sub(r"\s+", "", postcode.strip().upper())


def format_postcode(postcode: str) -> str:
    compact = normalise_postcode(postcode)
    return compact if len(compact) <= 3 else f"{compact[:-3]} {compact[-3:]}"
