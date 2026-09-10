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


def _school_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str, str]:
    urn_col = find_column(frame, "school_urn", "urn")
    level_col = find_column(frame, "geographic_level")
    if urn_col is None:
        raise SchoolFinderError(f"{source_name} CSV is missing school_urn.")
    if level_col is not None:
        frame = frame[clean_text_series(frame[level_col]).str.casefold().eq("school")].copy()
    current, time_col = _latest_rows(frame, source_name)
    return current, urn_col, time_col


def _number(frame: pd.DataFrame, name: str) -> pd.Series:
    col = find_column(frame, name)
    if col is None:
        return pd.Series(pd.NA, index=frame.index)
    return numeric_quality(frame[col])


def read_workforce_school(size_path: Path, ratio_path: Path) -> pd.DataFrame:
    size = read_public_csv(size_path, "DfE school workforce school-level")
    size, size_urn_col, size_time_col = _school_rows(size, "DfE workforce school")
    staff = pd.DataFrame(
        {
            "urn": clean_text_series(size[size_urn_col]),
            "workforce_year": clean_text_series(size[size_time_col]),
            "teacher_fte": _number(size, "fte_all_teachers"),
            "classroom_teacher_fte": _number(size, "fte_classroom_teachers"),
            "teaching_assistant_fte": _number(size, "fte_teaching_assistants"),
            "support_staff_fte": _number(size, "fte_all_support_staff"),
            "teachers_without_qts_fte": _number(size, "fte_all_teachers_without_qts"),
            "part_time_teacher_pct": _number(size, "percent_pt_teacher"),
        }
    )
    staff["workforce_source"] = WORKFORCE_SOURCE_NAME
    staff["workforce_source_dataset_id"] = WORKFORCE_SCHOOL_DATASET_ID
    staff = staff[staff["urn"].ne("")].drop_duplicates("urn", keep="last")

    ratio = read_public_csv(ratio_path, "DfE pupil-to-teacher ratios school-level")
    ratio, ratio_urn_col, ratio_time_col = _school_rows(ratio, "DfE workforce ratio school")
    ratios = pd.DataFrame(
        {
            "urn": clean_text_series(ratio[ratio_urn_col]),
            "workforce_ratio_year": clean_text_series(ratio[ratio_time_col]),
            "pupil_fte": _number(ratio, "pupils_fte"),
            "qualified_teacher_fte": _number(ratio, "qualified_teachers_fte"),
            "pupil_qualified_teacher_ratio": _number(ratio, "pupil_to_qual_teacher_ratio"),
            "pupil_teacher_ratio": _number(ratio, "pupil_to_qual_unqual_teacher_ratio"),
            "pupil_adult_ratio": _number(ratio, "pupil_to_adult_ratio"),
        }
    )
    ratios["workforce_ratio_source"] = WORKFORCE_RATIO_SOURCE_NAME
    ratios["workforce_ratio_source_dataset_id"] = WORKFORCE_RATIO_SCHOOL_DATASET_ID
    ratios = ratios[ratios["urn"].ne("")].drop_duplicates("urn", keep="last")

    return staff.merge(ratios, on="urn", how="outer", validate="one_to_one").reset_index(drop=True)


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


def _secondary_benchmark_rows(frame: pd.DataFrame, source_name: str) -> tuple[pd.DataFrame, str]:
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
    current, time_col = _latest_rows(frame, source_name)
    return current, time_col


def read_workforce_benchmarks(size_path: Path, ratio_path: Path) -> pd.DataFrame:
    size = read_public_csv(size_path, "DfE school workforce benchmarks")
    size, size_time_col = _secondary_benchmark_rows(size, "DfE workforce benchmark")
    staff = _benchmark_identity(size, "DfE workforce benchmark")
    staff["workforce_year"] = clean_text_series(size[size_time_col])
    for output, source_name in {
        "teacher_fte": "fte_all_teachers",
        "classroom_teacher_fte": "fte_classroom_teachers",
        "teaching_assistant_fte": "fte_teaching_assistants",
        "support_staff_fte": "fte_all_support_staff",
        "teachers_without_qts_fte": "fte_all_teachers_without_qts",
        "part_time_teacher_pct": "percent_pt_teacher",
    }.items():
        staff[output] = _number(size, source_name)
    staff["workforce_source"] = WORKFORCE_BENCHMARK_SOURCE_NAME
    staff["workforce_source_dataset_id"] = WORKFORCE_BENCHMARK_DATASET_ID
    staff = staff.drop_duplicates(["benchmark_level", "benchmark_code"], keep="last")

    ratio = read_public_csv(ratio_path, "DfE pupil-to-teacher ratio benchmarks")
    ratio, ratio_time_col = _secondary_benchmark_rows(ratio, "DfE workforce ratio benchmark")
    ratios = _benchmark_identity(ratio, "DfE workforce ratio benchmark")
    ratios["workforce_ratio_year"] = clean_text_series(ratio[ratio_time_col])
    for output, source_name in {
        "pupil_fte": "pupils_fte",
        "qualified_teacher_fte": "qualified_teachers_fte",
        "pupil_qualified_teacher_ratio": "pupil_to_qual_teacher_ratio",
        "pupil_teacher_ratio": "pupil_to_qual_unqual_teacher_ratio",
        "pupil_adult_ratio": "pupil_to_adult_ratio",
    }.items():
        ratios[output] = _number(ratio, source_name)
    ratios["workforce_ratio_source"] = WORKFORCE_RATIO_BENCHMARK_SOURCE_NAME
    ratios["workforce_ratio_source_dataset_id"] = WORKFORCE_RATIO_BENCHMARK_DATASET_ID
    ratios = ratios.drop_duplicates(["benchmark_level", "benchmark_code"], keep="last")

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
