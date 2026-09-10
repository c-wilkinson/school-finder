"""Dataset manifest serialization and source-version comparisons."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from school_finder.data.sources.common import CsvSource
from school_finder.data.sources.gias import GiasLinksSource, GiasSource
from school_finder.data.sources.onspd import OnspdSource
from school_finder.utils import iso_utc


def read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(payload: dict[str, Any], destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def gias_manifest(source: GiasSource) -> dict[str, Any]:
    return {
        "name": "Get Information About Schools",
        "source_date": source.source_date.isoformat(),
        "download_url": source.url,
    }


def gias_links_manifest(source: GiasLinksSource) -> dict[str, Any]:
    return {
        "name": "Get Information About Schools establishment links",
        "source_date": source.source_date.isoformat(),
        "download_url": source.url,
    }


def csv_source_manifest(source: CsvSource) -> dict[str, Any]:
    return {
        "name": source.name,
        "release_label": source.release_label,
        "download_url": source.url,
    }


def onspd_manifest(source: OnspdSource) -> dict[str, Any]:
    return {
        "name": "ONS Postcode Directory",
        "title": source.title,
        "release_date": source.release_date.isoformat(),
        "modified_at": iso_utc(source.modified_at),
        "arcgis_item_id": source.item_id,
        "item_url": source.item_url,
        "download_url": source.download_url,
        "coverage": "Current and terminated postcodes in England",
    }


def source_matches(
    manifest: dict[str, Any] | None,
    source_name: str,
    expected: dict[str, Any],
    keys: tuple[str, ...],
) -> bool:
    if manifest is None:
        return False
    actual = manifest.get("sources", {}).get(source_name, {})
    return all(actual.get(key) == expected.get(key) for key in keys)
