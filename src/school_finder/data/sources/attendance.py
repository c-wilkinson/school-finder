"""DfE full-year pupil absence source adapters."""

from __future__ import annotations

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

ATTENDANCE_SCHOOL_DATASET_ID = "889f9166-e3bf-4d3a-afb2-d86e4aecc70a"
ATTENDANCE_BENCHMARK_DATASET_ID = "d37f27c4-cca2-4274-97e9-1cdcb4ecad18"
_EES_DATASET_URL = "https://explore-education-statistics.service.gov.uk/data-catalogue/data-set/{dataset_id}/csv"
ATTENDANCE_SOURCE_NAME = "DfE pupil absence - school level"
ATTENDANCE_BENCHMARK_SOURCE_NAME = "DfE pupil absence benchmarks"


def _source(dataset_id: str, name: str) -> CsvSource:
    return CsvSource(
        name=name,
        url=_EES_DATASET_URL.format(dataset_id=dataset_id),
        release_label=f"EES dataset {dataset_id} (2024/25 full academic year)",
    )


def _discover(session: requests.Session, source: CsvSource, error_label: str) -> CsvSource:
    try:
        response = session.get(source.url, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE {error_label} data: {exc}") from exc
    return source


def discover_attendance_school_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(ATTENDANCE_SCHOOL_DATASET_ID, ATTENDANCE_SOURCE_NAME),
        "attendance school-level",
    )


def discover_attendance_benchmark_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(ATTENDANCE_BENCHMARK_DATASET_ID, ATTENDANCE_BENCHMARK_SOURCE_NAME),
        "attendance benchmark",
    )


def _latest_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    time_col = find_column(frame, "time_period")
    if time_col is None:
        raise SchoolFinderError(f"{source_name} CSV is missing time_period.")
    work = frame.copy()
    work["_time_num"] = pd.to_numeric(work[time_col], errors="coerce")
    work = work.dropna(subset=["_time_num"])
    if work.empty:
        raise SchoolFinderError(f"{source_name} CSV contained no valid time periods.")
    latest = int(work["_time_num"].max())
    return work[work["_time_num"] == latest].copy(), time_col


def read_attendance_school(path: Path) -> pd.DataFrame:
    frame = read_public_csv(path, "DfE pupil absence school-level")
    urn_col = find_column(frame, "school_urn", "urn")
    level_col = find_column(frame, "geographic_level")
    if urn_col is None:
        raise SchoolFinderError("DfE attendance school CSV is missing school_urn.")
    if level_col is not None:
        frame = frame[clean_text_series(frame[level_col]).str.casefold().eq("school")].copy()
    current, time_col = _latest_rows(frame, "DfE attendance school")

    result = pd.DataFrame(
        {
            "urn": clean_text_series(current[urn_col]),
            "attendance_year": clean_text_series(current[time_col]),
        }
    )
    metrics = {
        "attendance_enrolments": "enrolments",
        "overall_absence_pct": "sess_overall_percent",
        "authorised_absence_pct": "sess_authorised_percent",
        "unauthorised_absence_pct": "sess_unauthorised_percent",
        "persistent_absence_pct": "enrolments_pa_10_exact_percent",
        "severe_absence_pct": "enrolments_pa_50_exact_percent",
    }
    for output, source_name in metrics.items():
        col = find_column(current, source_name)
        result[output] = numeric_quality(current[col]) if col else pd.NA

    result["attendance_source"] = ATTENDANCE_SOURCE_NAME
    result["attendance_source_dataset_id"] = ATTENDANCE_SCHOOL_DATASET_ID
    return (
        result[result["urn"].ne("")]
        .drop_duplicates("urn", keep="last")
        .reset_index(drop=True)
    )


def _benchmark_identity(frame: pd.DataFrame) -> pd.DataFrame:
    level_col = find_column(frame, "geographic_level")
    country_code_col = find_column(frame, "country_code")
    country_name_col = find_column(frame, "country_name")
    la_code_col = find_column(frame, "new_la_code", "local_authority_code")
    la_name_col = find_column(frame, "la_name", "local_authority_name")
    if any(col is None for col in (level_col, country_code_col, country_name_col, la_code_col, la_name_col)):
        raise SchoolFinderError("DfE attendance benchmark CSV is missing geography identity columns.")
    levels = clean_text_series(frame[level_col])
    national = levels.str.casefold().eq("national")
    return pd.DataFrame(
        {
            "benchmark_level": levels,
            "benchmark_code": clean_text_series(frame[la_code_col]).where(
                ~national, clean_text_series(frame[country_code_col])
            ),
            "benchmark_name": clean_text_series(frame[la_name_col]).where(
                ~national, clean_text_series(frame[country_name_col])
            ),
        },
        index=frame.index,
    )


def read_attendance_benchmarks(path: Path) -> pd.DataFrame:
    frame = read_public_csv(path, "DfE pupil absence benchmarks")
    level_col = find_column(frame, "geographic_level")
    phase_col = find_column(frame, "education_phase", "school_type")
    if level_col is None or phase_col is None:
        raise SchoolFinderError(
            "DfE attendance benchmark CSV is missing geographic_level or education_phase."
        )
    levels = clean_text_series(frame[level_col]).str.casefold()
    phases = clean_text_series(frame[phase_col]).str.casefold()
    frame = frame[
        levels.isin({"national", "local authority"})
        & phases.eq("state-funded secondary")
    ].copy()
    if frame.empty:
        raise SchoolFinderError("DfE attendance benchmark CSV contained no secondary benchmark rows.")
    current, time_col = _latest_rows(frame, "DfE attendance benchmark")

    result = _benchmark_identity(current)
    result["attendance_year"] = clean_text_series(current[time_col])
    metrics = {
        "attendance_enrolments": "enrolments",
        "overall_absence_pct": "sess_overall_percent",
        "authorised_absence_pct": "sess_authorised_percent",
        "unauthorised_absence_pct": "sess_unauthorised_percent",
        "persistent_absence_pct": "enrolments_pa_10_exact_percent",
        "severe_absence_pct": "enrolments_pa_50_exact_percent",
    }
    for output, source_name in metrics.items():
        col = find_column(current, source_name)
        result[output] = numeric_quality(current[col]) if col else pd.NA
    result["attendance_source"] = ATTENDANCE_BENCHMARK_SOURCE_NAME
    result["attendance_source_dataset_id"] = ATTENDANCE_BENCHMARK_DATASET_ID
    return (
        result[result["benchmark_code"].ne("")]
        .drop_duplicates(["benchmark_level", "benchmark_code"], keep="last")
        .reset_index(drop=True)
    )
