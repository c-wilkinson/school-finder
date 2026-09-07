"""Ofsted school inspection source adapters."""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

from school_finder.errors import SchoolFinderError
from school_finder.data.sources.common import (
    CsvSource,
    clean_text_series,
    find_column,
    read_public_csv,
)

OFSTED_MANAGEMENT_URL = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "monthly-management-information-ofsteds-school-inspections-outcomes"
)

OFSTED_INDEPENDENT_URL = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "non-association-independent-schools-inspections-and-outcomes-management-information"
)


def discover_ofsted_csv(
    session: requests.Session,
    page_url: str,
    *,
    required_phrases: tuple[str, ...],
    source_name: str,
) -> CsvSource:
    try:
        response = session.get(page_url, timeout=(15, 60))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve {source_name}: {exc}") from exc

    anchors = re.findall(
        r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for href, raw_label in anchors:
        label = html.unescape(re.sub(r"<[^>]+>", " ", raw_label))
        label = re.sub(r"\s+", " ", label).strip()
        lowered = label.casefold()
        if not all(phrase.casefold() in lowered for phrase in required_phrases):
            continue
        if not href.casefold().endswith(".csv"):
            continue
        return CsvSource(
            name=source_name,
            url=urljoin(page_url, href),
            release_label=label,
        )

    raise SchoolFinderError(f"Could not discover the latest CSV for {source_name}.")


def discover_latest_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_MANAGEMENT_URL,
        required_phrases=("state-funded schools", "latest inspections as at"),
        source_name="Ofsted state-funded school inspections",
    )


def discover_latest_independent_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_INDEPENDENT_URL,
        required_phrases=("most recent inspections data as at",),
        source_name="Ofsted non-association independent school inspections",
    )


def read_ofsted_quality(path: Path) -> pd.DataFrame:
    frame = read_public_csv(path, "Ofsted")
    urn_col = find_column(frame, "URN")
    if urn_col is None:
        raise SchoolFinderError("Ofsted CSV does not contain a URN column.")

    result = pd.DataFrame({"urn": clean_text_series(frame[urn_col])})
    mappings = {
        "ofsted_rating": ("Overall effectiveness", "Overall effectiveness grade"),
        "ofsted_inspection_date": ("Inspection start date", "Inspection date"),
        "ofsted_publication_date": ("Publication date",),
        "ofsted_safeguarding": ("Safeguarding standards", "Safeguarding is effective?"),
        "ofsted_inclusion": ("Inclusion",),
        "ofsted_curriculum_teaching": ("Curriculum and teaching", "Quality of education"),
        "ofsted_achievement": ("Achievement",),
        "ofsted_attendance_behaviour": ("Attendance and behaviour", "Behaviour and attitudes"),
        "ofsted_personal_development": ("Personal development and wellbeing", "Personal development"),
        "ofsted_leadership": ("Leadership and governance", "Effectiveness of leadership and management"),
    }
    for output, aliases in mappings.items():
        source_col = find_column(frame, *aliases)
        result[output] = clean_text_series(frame[source_col]) if source_col else pd.NA

    for date_col in ("ofsted_inspection_date", "ofsted_publication_date"):
        result[date_col] = pd.to_datetime(result[date_col], errors="coerce", dayfirst=True)

    result = result[result["urn"].ne("")].copy()
    result = result.sort_values(
        ["urn", "ofsted_publication_date", "ofsted_inspection_date"],
        kind="stable",
        na_position="first",
    ).drop_duplicates("urn", keep="last")
    return result.reset_index(drop=True)
