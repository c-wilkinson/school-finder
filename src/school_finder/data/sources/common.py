"""Shared HTTP and CSV helpers for public-data source adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from school_finder.config import HTTP_CHUNK_SIZE, USER_AGENT
from school_finder.errors import SchoolFinderError
from school_finder.utils import log

QUALITY_MISSING_MARKERS = {"", "z", "x", "c", "na", "n/a", "null", "none"}


@dataclass(frozen=True)
class CsvSource:
    name: str
    url: str
    release_label: str


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = session.get(url, params=params, timeout=(15, 60))
        response.raise_for_status()
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise SchoolFinderError(f"Service returned invalid JSON: {url}") from exc
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve {url}: {exc}") from exc

    if not isinstance(payload, dict):
        raise SchoolFinderError(f"Service returned unexpected data: {url}")
    if payload.get("error"):
        raise SchoolFinderError(f"Service error for {url}: {payload['error']}")
    return payload


def stream_download(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    minimum_size: int,
) -> None:
    try:
        with session.get(url, stream=True, timeout=(20, 600)) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=HTTP_CHUNK_SIZE):
                    if chunk:
                        output.write(chunk)
    except requests.RequestException as exc:
        destination.unlink(missing_ok=True)
        raise SchoolFinderError(f"Could not download {url}: {exc}") from exc

    if destination.stat().st_size < minimum_size:
        destination.unlink(missing_ok=True)
        raise SchoolFinderError(f"Downloaded file from {url} was unexpectedly small.")


def download_csv(
    session: requests.Session,
    source: CsvSource,
    destination: Path,
    *,
    minimum_size: int = 10_000,
) -> None:
    log(f"Downloading {source.name}...")
    stream_download(session, source.url, destination, minimum_size=minimum_size)


def normalise_column_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().casefold())


def normalised_columns(frame: pd.DataFrame) -> dict[str, str]:
    return {normalise_column_name(str(column)): str(column) for column in frame.columns}


def find_column(frame: pd.DataFrame, *names: str) -> str | None:
    columns = normalised_columns(frame)
    for name in names:
        found = columns.get(normalise_column_name(name))
        if found:
            return found
    return None


def clean_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype("string").str.strip()


def numeric_quality(series: pd.Series) -> pd.Series:
    cleaned = clean_text_series(series)
    cleaned = cleaned.mask(cleaned.str.casefold().isin(QUALITY_MISSING_MARKERS))
    return pd.to_numeric(cleaned, errors="coerce")


def read_public_csv(path: Path, source_name: str) -> pd.DataFrame:
    """Read publisher CSVs that may use UTF-8, Windows-1252, or Latin-1."""
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=encoding, low_memory=False)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise SchoolFinderError(
        f"Could not decode {source_name} CSV using UTF-8, Windows-1252 or Latin-1: "
        f"{last_error}"
    )
