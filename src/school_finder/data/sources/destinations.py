"""DfE Key Stage 4 destination measures for schools and benchmarks."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import requests

from school_finder.data.sources.common import (
    CsvSource,
    clean_text_series,
    find_column,
    numeric_quality,
    read_public_csv,
)
from school_finder.errors import SchoolFinderError

DESTINATION_SCHOOL_DATASET_ID = "7be58881-d49f-4e3b-b2b6-0877a1a0fe6e"
DESTINATION_NATIONAL_DATASET_ID = "771e2b11-ef92-4885-acb9-f4ae2881ca41"
DESTINATION_LA_DATASET_ID = "29097d0c-dddd-4983-9afb-18a2bdce7099"
_EES_DATASET_URL = (
    "https://explore-education-statistics.service.gov.uk/data-catalogue/data-set/"
    "{dataset_id}/csv"
)
DESTINATION_SOURCE_NAME = "DfE Key stage 4 destinations - school level"
DESTINATION_NATIONAL_SOURCE_NAME = "DfE Key stage 4 destinations - national"
DESTINATION_LA_SOURCE_NAME = "DfE Key stage 4 destinations - local authority"

DESTINATION_METRICS = {
    "destination_pupil_count": "cohort",
    "sustained_destination_pct": "overall",
    "education_destination_pct": "education",
    "apprenticeship_destination_pct": "appren",
    "employment_destination_pct": "all_work",
    "not_sustained_destination_pct": "all_notsust",
    "unknown_destination_pct": "all_unknown",
}


def _source(dataset_id: str, name: str) -> CsvSource:
    return CsvSource(
        name=name,
        url=_EES_DATASET_URL.format(dataset_id=dataset_id),
        release_label=f"EES dataset {dataset_id} (latest)",
    )


def _discover(session: requests.Session, source: CsvSource, label: str) -> CsvSource:
    try:
        response = session.get(source.url, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE {label} data: {exc}") from exc
    return source


def discover_destination_school_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(DESTINATION_SCHOOL_DATASET_ID, DESTINATION_SOURCE_NAME),
        "destination school-level",
    )


def discover_destination_national_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(DESTINATION_NATIONAL_DATASET_ID, DESTINATION_NATIONAL_SOURCE_NAME),
        "destination national benchmark",
    )


def discover_destination_la_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(DESTINATION_LA_DATASET_ID, DESTINATION_LA_SOURCE_NAME),
        "destination local-authority benchmark",
    )


def next_academic_year(value: str) -> str | None:
    """Return the academic year immediately after a DfE compact or slash year."""
    text = str(value).strip()
    compact = re.fullmatch(r"(\d{4})(\d{2})", text)
    if compact:
        start = int(compact.group(1)) + 1
        end = (int(compact.group(2)) + 1) % 100
        return f"{start}{end:02d}"
    slash = re.fullmatch(r"(\d{4})/(\d{2})", text)
    if slash:
        start = int(slash.group(1)) + 1
        end = (int(slash.group(2)) + 1) % 100
        return f"{start}/{end:02d}"
    return None


def _headline_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    time_col = find_column(frame, "time_period")
    if time_col is None:
        raise SchoolFinderError(f"{source_name} CSV is missing time_period.")
    work = frame.copy()
    for dimension in ("breakdown_topic", "breakdown"):
        col = find_column(work, dimension)
        if col is not None:
            work = work[clean_text_series(work[col]).str.casefold().eq("total")].copy()
    data_type_col = find_column(work, "data_type")
    if data_type_col is not None:
        work = work[clean_text_series(work[data_type_col]).str.casefold().eq("percentage")].copy()
    work["_time_num"] = pd.to_numeric(work[time_col], errors="coerce")
    work = work.dropna(subset=["_time_num"])
    if work.empty:
        raise SchoolFinderError(f"{source_name} CSV contained no usable headline rows.")
    return work, time_col


def _headline(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    work, time_col = _headline_rows(frame, source_name)
    latest = int(work["_time_num"].max())
    return work[work["_time_num"] == latest].copy(), time_col


def _metrics(frame: pd.DataFrame) -> dict[str, pd.Series]:
    values: dict[str, pd.Series] = {}
    for output, source_name in DESTINATION_METRICS.items():
        col = find_column(frame, source_name)
        values[output] = (
            numeric_quality(frame[col])
            if col is not None
            else pd.Series(pd.NA, index=frame.index, dtype="object")
        )
    return values


def _school_frame(frame: pd.DataFrame, *, latest_only: bool) -> pd.DataFrame:
    urn_col = find_column(frame, "school_urn", "urn")
    if urn_col is None:
        raise SchoolFinderError("DfE destination school CSV is missing school_urn.")
    level_col = find_column(frame, "geographic_level")
    if level_col is not None:
        frame = frame[clean_text_series(frame[level_col]).str.casefold().eq("school")].copy()
    rows, time_col = (
        _headline(frame, "DfE destination school")
        if latest_only
        else _headline_rows(frame, "DfE destination school")
    )
    years = clean_text_series(rows[time_col])
    result = pd.DataFrame(
        {
            "urn": clean_text_series(rows[urn_col]),
            "destination_leaver_year": years,
            "destination_year": years.map(next_academic_year),
            **_metrics(rows),
        }
    )
    result["destination_source"] = DESTINATION_SOURCE_NAME
    result["destination_source_dataset_id"] = DESTINATION_SCHOOL_DATASET_ID
    subset = ["urn"] if latest_only else ["urn", "destination_leaver_year"]
    return (
        result[result["urn"].ne("")]
        .drop_duplicates(subset, keep="last")
        .reset_index(drop=True)
    )


def read_destination_school(path: Path) -> pd.DataFrame:
    return _school_frame(
        read_public_csv(path, "DfE destinations school-level"),
        latest_only=True,
    )


def read_destination_school_history(path: Path) -> pd.DataFrame:
    """Return all published school destination cohorts."""
    return _school_frame(
        read_public_csv(path, "DfE destinations school-level"),
        latest_only=False,
    )


def _filter_benchmark_rows(frame: pd.DataFrame) -> pd.DataFrame:
    group_col = find_column(frame, "institution_group")
    if group_col is not None:
        groups = clean_text_series(frame[group_col]).str.casefold()
        preferred = groups.eq("state-funded mainstream schools")
        if preferred.any():
            frame = frame[preferred].copy()
    type_col = find_column(frame, "institution_type")
    if type_col is not None:
        types = clean_text_series(frame[type_col]).str.casefold()
        total = types.eq("total")
        if total.any():
            frame = frame[total].copy()
    return frame


def _benchmark_frame(
    frame: pd.DataFrame,
    *,
    level: str,
    source_name: str,
    dataset_id: str,
    latest_only: bool,
) -> pd.DataFrame:
    filtered = _filter_benchmark_rows(frame)
    rows, time_col = (
        _headline(filtered, source_name)
        if latest_only
        else _headline_rows(filtered, source_name)
    )
    years = clean_text_series(rows[time_col])
    if level == "National":
        code_col = find_column(rows, "country_code")
        name_col = find_column(rows, "country_name")
    else:
        code_col = find_column(rows, "new_la_code", "local_authority_code")
        name_col = find_column(rows, "la_name", "local_authority_name")
    if code_col is None or name_col is None:
        raise SchoolFinderError(f"{source_name} CSV is missing geography identity columns.")
    result = pd.DataFrame(
        {
            "benchmark_level": level,
            "benchmark_code": clean_text_series(rows[code_col]),
            "benchmark_name": clean_text_series(rows[name_col]),
            "destination_leaver_year": years,
            "destination_year": years.map(next_academic_year),
            **_metrics(rows),
        }
    )
    result["destination_source"] = source_name
    result["destination_source_dataset_id"] = dataset_id
    subset = ["benchmark_level", "benchmark_code"]
    if not latest_only:
        subset.append("destination_leaver_year")
    return result[result["benchmark_code"].ne("")].drop_duplicates(subset, keep="last")


def read_destination_benchmarks(national_path: Path, la_path: Path) -> pd.DataFrame:
    national = _benchmark_frame(
        read_public_csv(national_path, "DfE destinations national"),
        level="National",
        source_name=DESTINATION_NATIONAL_SOURCE_NAME,
        dataset_id=DESTINATION_NATIONAL_DATASET_ID,
        latest_only=True,
    )
    local = _benchmark_frame(
        read_public_csv(la_path, "DfE destinations local authority"),
        level="Local authority",
        source_name=DESTINATION_LA_SOURCE_NAME,
        dataset_id=DESTINATION_LA_DATASET_ID,
        latest_only=True,
    )
    return pd.concat([national, local], ignore_index=True).reset_index(drop=True)


def read_destination_benchmark_history(national_path: Path, la_path: Path) -> pd.DataFrame:
    """Return all published national and local-authority destination cohorts."""
    national = _benchmark_frame(
        read_public_csv(national_path, "DfE destinations national"),
        level="National",
        source_name=DESTINATION_NATIONAL_SOURCE_NAME,
        dataset_id=DESTINATION_NATIONAL_DATASET_ID,
        latest_only=False,
    )
    local = _benchmark_frame(
        read_public_csv(la_path, "DfE destinations local authority"),
        level="Local authority",
        source_name=DESTINATION_LA_SOURCE_NAME,
        dataset_id=DESTINATION_LA_DATASET_ID,
        latest_only=False,
    )
    return pd.concat([national, local], ignore_index=True).reset_index(drop=True)
