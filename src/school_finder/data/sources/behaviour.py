"""DfE suspensions and permanent exclusions source adapters."""

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

BEHAVIOUR_SCHOOL_DATASET_ID = "a4b5a46f-5bed-42b5-91b8-93620a04001e"
BEHAVIOUR_BENCHMARK_DATASET_ID = "59d8b51e-fea6-40f5-911a-0d916679d206"
_EES_DATASET_URL = "https://explore-education-statistics.service.gov.uk/data-catalogue/data-set/{dataset_id}/csv"
BEHAVIOUR_SOURCE_NAME = "DfE suspensions and permanent exclusions - school level"
BEHAVIOUR_BENCHMARK_SOURCE_NAME = "DfE suspensions and permanent exclusions benchmarks"


def _source(dataset_id: str, name: str) -> CsvSource:
    return CsvSource(
        name=name,
        url=_EES_DATASET_URL.format(dataset_id=dataset_id),
        release_label=f"EES dataset {dataset_id} (2024/25 academic year)",
    )


def _discover(session: requests.Session, source: CsvSource, error_label: str) -> CsvSource:
    try:
        response = session.get(source.url, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE {error_label} data: {exc}") from exc
    return source


def discover_behaviour_school_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(BEHAVIOUR_SCHOOL_DATASET_ID, BEHAVIOUR_SOURCE_NAME),
        "behaviour school-level",
    )


def discover_behaviour_benchmark_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(BEHAVIOUR_BENCHMARK_DATASET_ID, BEHAVIOUR_BENCHMARK_SOURCE_NAME),
        "behaviour benchmark",
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


def _metrics(frame: pd.DataFrame) -> dict[str, pd.Series]:
    mapping = {
        "behaviour_pupil_headcount": "headcount",
        "suspension_count": "suspension",
        "suspension_rate": "susp_rate",
        "pupils_with_one_or_more_suspension": "one_plus_susp",
        "pupils_with_one_or_more_suspension_rate": "one_plus_susp_rate",
        "permanent_exclusion_count": "perm_excl",
        "permanent_exclusion_rate": "perm_excl_rate",
    }
    values: dict[str, pd.Series] = {}
    for output, source_name in mapping.items():
        col = find_column(frame, source_name)
        values[output] = numeric_quality(frame[col]) if col else pd.Series(pd.NA, index=frame.index)
    return values


def read_behaviour_school(path: Path) -> pd.DataFrame:
    frame = read_public_csv(path, "DfE suspensions and exclusions school-level")
    urn_col = find_column(frame, "school_urn", "urn")
    level_col = find_column(frame, "geographic_level")
    if urn_col is None:
        raise SchoolFinderError("DfE behaviour school CSV is missing school_urn.")
    if level_col is not None:
        frame = frame[clean_text_series(frame[level_col]).str.casefold().eq("school")].copy()
    current, time_col = _latest_rows(frame, "DfE behaviour school")
    result = pd.DataFrame(
        {
            "urn": clean_text_series(current[urn_col]),
            "behaviour_year": clean_text_series(current[time_col]),
            **_metrics(current),
        }
    )
    result["behaviour_source"] = BEHAVIOUR_SOURCE_NAME
    result["behaviour_source_dataset_id"] = BEHAVIOUR_SCHOOL_DATASET_ID
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
        raise SchoolFinderError("DfE behaviour benchmark CSV is missing geography identity columns.")
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


def read_behaviour_benchmarks(path: Path) -> pd.DataFrame:
    frame = read_public_csv(path, "DfE suspensions and exclusions benchmarks")
    level_col = find_column(frame, "geographic_level")
    phase_col = find_column(frame, "education_phase", "school_type")
    if level_col is None or phase_col is None:
        raise SchoolFinderError(
            "DfE behaviour benchmark CSV is missing geographic_level or education_phase."
        )
    levels = clean_text_series(frame[level_col]).str.casefold()
    phases = clean_text_series(frame[phase_col]).str.casefold()
    frame = frame[
        levels.isin({"national", "local authority"})
        & phases.eq("state-funded secondary")
    ].copy()
    if frame.empty:
        raise SchoolFinderError("DfE behaviour benchmark CSV contained no secondary benchmark rows.")
    current, time_col = _latest_rows(frame, "DfE behaviour benchmark")

    result = _benchmark_identity(current)
    result["behaviour_year"] = clean_text_series(current[time_col])
    for name, values in _metrics(current).items():
        result[name] = values
    result["behaviour_source"] = BEHAVIOUR_BENCHMARK_SOURCE_NAME
    result["behaviour_source_dataset_id"] = BEHAVIOUR_BENCHMARK_DATASET_ID
    return (
        result[result["benchmark_code"].ne("")]
        .drop_duplicates(["benchmark_level", "benchmark_code"], keep="last")
        .reset_index(drop=True)
    )
