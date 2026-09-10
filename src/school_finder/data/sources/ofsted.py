"""Ofsted school inspection source adapters."""

from __future__ import annotations

import html
import re
from datetime import date, datetime
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

# Ofsted's renewed school inspection framework began on 10 November 2025.
RENEWED_FRAMEWORK_START = date(2025, 11, 10)

_LATEST_INSPECTIONS_DATE = re.compile(
    r"latest inspections as at\s+(?P<date>\d{1,2}\s+[A-Za-z]+\s+\d{4})",
    flags=re.IGNORECASE,
)

_LEGACY_GRADE_CODES = {
    "1": "Outstanding",
    "2": "Good",
    "3": "Requires improvement",
    "4": "Inadequate",
}


def discover_ofsted_csv(
    session: requests.Session,
    page_url: str,
    *,
    required_phrases: tuple[str, ...],
    source_name: str,
    before: date | None = None,
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
    candidates: list[tuple[date, CsvSource]] = []
    for href, raw_label in anchors:
        label = html.unescape(re.sub(r"<[^>]+>", " ", raw_label))
        label = re.sub(r"\s+", " ", label).strip()
        lowered = label.casefold()
        if not all(phrase.casefold() in lowered for phrase in required_phrases):
            continue
        if not href.casefold().endswith(".csv"):
            continue
        source = CsvSource(
            name=source_name,
            url=urljoin(page_url, href),
            release_label=label,
        )
        if before is None:
            return source

        release_date = parse_latest_inspections_date(label)
        if release_date is not None and release_date < before:
            candidates.append((release_date, source))

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    raise SchoolFinderError(f"Could not discover the latest CSV for {source_name}.")


def discover_latest_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_MANAGEMENT_URL,
        required_phrases=("state-funded schools", "latest inspections as at"),
        source_name="Ofsted state-funded school inspections",
    )


def discover_latest_legacy_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_MANAGEMENT_URL,
        required_phrases=("state-funded schools", "latest inspections as at"),
        source_name="Ofsted state-funded school inspections (legacy snapshot)",
        before=RENEWED_FRAMEWORK_START,
    )


def discover_latest_independent_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_INDEPENDENT_URL,
        required_phrases=("most recent inspections data as at",),
        source_name="Ofsted non-association independent school inspections",
    )


def parse_latest_inspections_date(label: str) -> date | None:
    match = _LATEST_INSPECTIONS_DATE.search(label)
    if not match:
        return None
    value = match.group("date")
    for pattern in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _normalise_legacy_grade(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.casefold() in {
        "9",
        "nan",
        "none",
        "null",
        "not set",
        "not applicable",
    }:
        return None
    return _LEGACY_GRADE_CODES.get(text, text)


def _rating_from_ungraded_outcome(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().casefold()
    if not text:
        return None
    for phrase, rating in (
        ("remains outstanding", "Outstanding"),
        ("remains good", "Good"),
        ("remains requires improvement", "Requires improvement"),
        ("remains inadequate", "Inadequate"),
    ):
        if phrase in text:
            return rating
    return None


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

    for grade_col in (
        "ofsted_rating",
        "ofsted_inclusion",
        "ofsted_curriculum_teaching",
        "ofsted_achievement",
        "ofsted_attendance_behaviour",
        "ofsted_personal_development",
        "ofsted_leadership",
    ):
        result[grade_col] = result[grade_col].map(_normalise_legacy_grade)

    outcome_col = find_column(
        frame,
        "Outcomes for ungraded and monitoring inspections",
        "Inspection outcome",
        "Outcome",
    )
    if outcome_col is not None:
        retained = frame[outcome_col].map(_rating_from_ungraded_outcome)
        result["ofsted_rating"] = result["ofsted_rating"].where(
            result["ofsted_rating"].notna(), retained
        )

    for date_col in ("ofsted_inspection_date", "ofsted_publication_date"):
        result[date_col] = pd.to_datetime(result[date_col], errors="coerce", dayfirst=True)

    result = result[result["urn"].ne("")].copy()
    result = result.sort_values(
        ["urn", "ofsted_publication_date", "ofsted_inspection_date"],
        kind="stable",
        na_position="first",
    ).drop_duplicates("urn", keep="last")
    return result.reset_index(drop=True)
