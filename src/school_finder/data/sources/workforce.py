"""DfE school workforce and pupil-to-teacher ratio source adapters."""

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

WORKFORCE_SCHOOL_DATASET_ID = "cce5e2fe-b6eb-4741-9199-21afa08fb97a"
WORKFORCE_RATIO_SCHOOL_DATASET_ID = "d5f1867a-ca93-454d-9361-6c64df108872"
WORKFORCE_BENCHMARK_DATASET_ID = "47006239-5f46-4c97-8ae0-38fd288d1c1e"
WORKFORCE_RATIO_BENCHMARK_DATASET_ID = "3682ab8e-9e55-4a99-8af2-be965ddfe43b"
_EES_DATASET_URL = "https://explore-education-statistics.service.gov.uk/data-catalogue/data-set/{dataset_id}/csv"
WORKFORCE_SOURCE_NAME = "DfE school workforce - school level"
WORKFORCE_RATIO_SOURCE_NAME = "DfE pupil to teacher ratios - school level"
WORKFORCE_BENCHMARK_SOURCE_NAME = "DfE school workforce benchmarks"
WORKFORCE_RATIO_BENCHMARK_SOURCE_NAME = "DfE pupil to teacher ratio benchmarks"

WORKFORCE_STAFF_METRICS = {
    "teacher_fte": "fte_all_teachers",
    "classroom_teacher_fte": "fte_classroom_teachers",
    "teaching_assistant_fte": "fte_teaching_assistants",
    "support_staff_fte": "fte_all_support_staff",
    "teachers_without_qts_fte": "fte_all_teachers_without_qts",
    "part_time_teacher_pct": "percent_pt_teacher",
}
WORKFORCE_RATIO_METRICS = {
    "pupil_fte": "pupils_fte",
    "qualified_teacher_fte": "qualified_teachers_fte",
    "pupil_qualified_teacher_ratio": "pupil_to_qual_teacher_ratio",
    "pupil_teacher_ratio": "pupil_to_qual_unqual_teacher_ratio",
    "pupil_adult_ratio": "pupil_to_adult_ratio",
}


def _source(dataset_id: str, name: str) -> CsvSource:
    return CsvSource(
        name=name,
        url=_EES_DATASET_URL.format(dataset_id=dataset_id),
        release_label=f"EES dataset {dataset_id} (reporting year 2025)",
    )


def _discover(session: requests.Session, source: CsvSource, error_label: str) -> CsvSource:
    try:
        response = session.get(source.url, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE {error_label} data: {exc}") from exc
    return source


def discover_workforce_school_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(WORKFORCE_SCHOOL_DATASET_ID, WORKFORCE_SOURCE_NAME),
        "school workforce school-level",
    )


def discover_workforce_ratio_school_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(WORKFORCE_RATIO_SCHOOL_DATASET_ID, WORKFORCE_RATIO_SOURCE_NAME),
        "pupil-to-teacher ratio school-level",
    )


def discover_workforce_benchmark_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(WORKFORCE_BENCHMARK_DATASET_ID, WORKFORCE_BENCHMARK_SOURCE_NAME),
        "school workforce benchmark",
    )


def discover_workforce_ratio_benchmark_source(session: requests.Session) -> CsvSource:
    return _discover(
        session,
        _source(
            WORKFORCE_RATIO_BENCHMARK_DATASET_ID,
            WORKFORCE_RATIO_BENCHMARK_SOURCE_NAME,
        ),
        "pupil-to-teacher ratio benchmark",
    )


def _time_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    time_col = find_column(frame, "time_period")
    if time_col is None:
        raise SchoolFinderError(f"{source_name} CSV is missing time_period.")
    work = frame.copy()
    work["_time_num"] = pd.to_numeric(work[time_col], errors="coerce")
    work = work.dropna(subset=["_time_num"])
    if work.empty:
        raise SchoolFinderError(f"{source_name} CSV contained no valid time periods.")
    return work, time_col


def _latest_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    work, time_col = _time_rows(frame, source_name)
    latest = int(work["_time_num"].max())
    return work[work["_time_num"] == latest].copy(), time_col


def _school_filtered(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    urn_col = find_column(frame, "school_urn", "urn")
    level_col = find_column(frame, "geographic_level")
    if urn_col is None:
        raise SchoolFinderError(f"{source_name} CSV is missing school_urn.")
    if level_col is not None:
        frame = frame[clean_text_series(frame[level_col]).str.casefold().eq("school")].copy()
    return frame, urn_col


def _school_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str, str]:
    frame, urn_col = _school_filtered(frame, source_name)
    current, time_col = _latest_rows(frame, source_name)
    return current, urn_col, time_col


def _school_history_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str, str]:
    frame, urn_col = _school_filtered(frame, source_name)
    rows, time_col = _time_rows(frame, source_name)
    return rows, urn_col, time_col


def _number(frame: pd.DataFrame, name: str) -> pd.Series:
    col = find_column(frame, name)
    if col is None:
        return pd.Series(pd.NA, index=frame.index, dtype="object")
    return numeric_quality(frame[col])


def _school_staff_frame(
    frame: pd.DataFrame,
    *,
    latest_only: bool,
) -> pd.DataFrame:
    rows, urn_col, time_col = (
        _school_rows(frame, "DfE workforce school")
        if latest_only
        else _school_history_rows(frame, "DfE workforce school")
    )
    result = pd.DataFrame(
        {
            "urn": clean_text_series(rows[urn_col]),
            "history_year": clean_text_series(rows[time_col]),
        }
    )
    for output, source_name in WORKFORCE_STAFF_METRICS.items():
        result[output] = _number(rows, source_name)
    subset = ["urn"] if latest_only else ["urn", "history_year"]
    return result[result["urn"].ne("")].drop_duplicates(subset, keep="last")


def _school_ratio_frame(
    frame: pd.DataFrame,
    *,
    latest_only: bool,
) -> pd.DataFrame:
    rows, urn_col, time_col = (
        _school_rows(frame, "DfE workforce ratio school")
        if latest_only
        else _school_history_rows(frame, "DfE workforce ratio school")
    )
    result = pd.DataFrame(
        {
            "urn": clean_text_series(rows[urn_col]),
            "history_year": clean_text_series(rows[time_col]),
        }
    )
    for output, source_name in WORKFORCE_RATIO_METRICS.items():
        result[output] = _number(rows, source_name)
    subset = ["urn"] if latest_only else ["urn", "history_year"]
    return result[result["urn"].ne("")].drop_duplicates(subset, keep="last")


def read_workforce_school(size_path: Path, ratio_path: Path) -> pd.DataFrame:
    size_raw = read_public_csv(size_path, "DfE school workforce school-level")
    staff = _school_staff_frame(size_raw, latest_only=True).rename(
        columns={"history_year": "workforce_year"}
    )
    staff["workforce_source"] = WORKFORCE_SOURCE_NAME
    staff["workforce_source_dataset_id"] = WORKFORCE_SCHOOL_DATASET_ID

    ratio_raw = read_public_csv(ratio_path, "DfE pupil-to-teacher ratios school-level")
    ratios = _school_ratio_frame(ratio_raw, latest_only=True).rename(
        columns={"history_year": "workforce_ratio_year"}
    )
    ratios["workforce_ratio_source"] = WORKFORCE_RATIO_SOURCE_NAME
    ratios["workforce_ratio_source_dataset_id"] = WORKFORCE_RATIO_SCHOOL_DATASET_ID

    return staff.merge(ratios, on="urn", how="outer", validate="one_to_one").reset_index(drop=True)


def read_workforce_school_history(size_path: Path, ratio_path: Path) -> pd.DataFrame:
    """Return all published school workforce and ratio measures by reporting year."""
    staff = _school_staff_frame(
        read_public_csv(size_path, "DfE school workforce school-level"),
        latest_only=False,
    )
    ratios = _school_ratio_frame(
        read_public_csv(ratio_path, "DfE pupil-to-teacher ratios school-level"),
        latest_only=False,
    )
    return staff.merge(
        ratios,
        on=["urn", "history_year"],
        how="outer",
        validate="one_to_one",
    ).reset_index(drop=True)


def _benchmark_identity(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    level_col = find_column(frame, "geographic_level")
    country_code_col = find_column(frame, "country_code")
    country_name_col = find_column(frame, "country_name")
    la_code_col = find_column(frame, "new_la_code", "local_authority_code")
    la_name_col = find_column(frame, "la_name", "local_authority_name")
    if any(col is None for col in (level_col, country_code_col, country_name_col, la_code_col, la_name_col)):
        raise SchoolFinderError(f"{source_name} CSV is missing geography identity columns.")
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


def _secondary_benchmark_filtered(frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
    level_col = find_column(frame, "geographic_level")
    type_col = find_column(frame, "establishment_type_group", "school_type")
    if level_col is None or type_col is None:
        raise SchoolFinderError(
            f"{source_name} CSV is missing geographic_level or school type."
        )
    levels = clean_text_series(frame[level_col]).str.casefold()
    school_types = clean_text_series(frame[type_col]).str.casefold()
    frame = frame[
        levels.isin({"national", "local authority"})
        & school_types.eq("state-funded secondary")
    ].copy()
    if frame.empty:
        raise SchoolFinderError(f"{source_name} CSV contained no secondary benchmark rows.")
    return frame


def _secondary_benchmark_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    frame = _secondary_benchmark_filtered(frame, source_name)
    return _latest_rows(frame, source_name)


def _secondary_benchmark_history_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
    frame = _secondary_benchmark_filtered(frame, source_name)
    return _time_rows(frame, source_name)


def _benchmark_metrics_frame(
    frame: pd.DataFrame,
    *,
    source_name: str,
    mapping: dict[str, str],
    latest_only: bool,
) -> pd.DataFrame:
    rows, time_col = (
        _secondary_benchmark_rows(frame, source_name)
        if latest_only
        else _secondary_benchmark_history_rows(frame, source_name)
    )
    result = _benchmark_identity(rows, source_name)
    result["history_year"] = clean_text_series(rows[time_col])
    for output, source_column in mapping.items():
        result[output] = _number(rows, source_column)
    subset = ["benchmark_level", "benchmark_code"]
    if not latest_only:
        subset.append("history_year")
    return result[result["benchmark_code"].ne("")].drop_duplicates(subset, keep="last")


def read_workforce_benchmarks(size_path: Path, ratio_path: Path) -> pd.DataFrame:
    staff = _benchmark_metrics_frame(
        read_public_csv(size_path, "DfE school workforce benchmarks"),
        source_name="DfE workforce benchmark",
        mapping=WORKFORCE_STAFF_METRICS,
        latest_only=True,
    ).rename(columns={"history_year": "workforce_year"})
    staff["workforce_source"] = WORKFORCE_BENCHMARK_SOURCE_NAME
    staff["workforce_source_dataset_id"] = WORKFORCE_BENCHMARK_DATASET_ID

    ratios = _benchmark_metrics_frame(
        read_public_csv(ratio_path, "DfE pupil-to-teacher ratio benchmarks"),
        source_name="DfE workforce ratio benchmark",
        mapping=WORKFORCE_RATIO_METRICS,
        latest_only=True,
    ).rename(columns={"history_year": "workforce_ratio_year"})
    ratios["workforce_ratio_source"] = WORKFORCE_RATIO_BENCHMARK_SOURCE_NAME
    ratios["workforce_ratio_source_dataset_id"] = WORKFORCE_RATIO_BENCHMARK_DATASET_ID

    ratios = ratios.rename(columns={"benchmark_name": "_ratio_benchmark_name"})
    result = staff.merge(
        ratios,
        on=["benchmark_level", "benchmark_code"],
        how="outer",
        validate="one_to_one",
    )
    result["benchmark_name"] = result["benchmark_name"].fillna(
        result["_ratio_benchmark_name"]
    )
    result = result.drop(columns="_ratio_benchmark_name")
    return result[result["benchmark_code"].fillna("").ne("")].reset_index(drop=True)


def read_workforce_benchmark_history(size_path: Path, ratio_path: Path) -> pd.DataFrame:
    """Return all secondary workforce benchmark measures by reporting year."""
    staff = _benchmark_metrics_frame(
        read_public_csv(size_path, "DfE school workforce benchmarks"),
        source_name="DfE workforce benchmark",
        mapping=WORKFORCE_STAFF_METRICS,
        latest_only=False,
    )
    ratios = _benchmark_metrics_frame(
        read_public_csv(ratio_path, "DfE pupil-to-teacher ratio benchmarks"),
        source_name="DfE workforce ratio benchmark",
        mapping=WORKFORCE_RATIO_METRICS,
        latest_only=False,
    ).rename(columns={"benchmark_name": "_ratio_benchmark_name"})

    result = staff.merge(
        ratios,
        on=["benchmark_level", "benchmark_code", "history_year"],
        how="outer",
        validate="one_to_one",
    )
    result["benchmark_name"] = result["benchmark_name"].fillna(
        result["_ratio_benchmark_name"]
    )
    return result.drop(columns="_ratio_benchmark_name").reset_index(drop=True)
