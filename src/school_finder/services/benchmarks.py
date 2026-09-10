"""Load benchmark context for school search results."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from school_finder.errors import SchoolFinderError
from school_finder.models.school import SchoolBenchmarks, school_benchmark_from_flat_record
from school_finder.data.parquet import require_pyarrow

_REQUIRED_COLUMNS = {
    "benchmark_level",
    "benchmark_code",
    "benchmark_name",
    "performance_year",
    "attainment8",
    "english_maths_grade5_pct",
    "english_maths_grade4_pct",
    "ebacc_entry_pct",
    "ebacc_aps",
    "progress8",
    "progress8_year",
    "source",
    "source_dataset_id",
    "attendance_year",
    "attendance_enrolments",
    "overall_absence_pct",
    "authorised_absence_pct",
    "unauthorised_absence_pct",
    "persistent_absence_pct",
    "severe_absence_pct",
    "attendance_source",
    "attendance_source_dataset_id",
    "behaviour_year",
    "behaviour_pupil_headcount",
    "suspension_count",
    "suspension_rate",
    "pupils_with_one_or_more_suspension",
    "pupils_with_one_or_more_suspension_rate",
    "permanent_exclusion_count",
    "permanent_exclusion_rate",
    "behaviour_source",
    "behaviour_source_dataset_id",
    "workforce_year",
    "workforce_ratio_year",
    "pupil_fte",
    "teacher_fte",
    "qualified_teacher_fte",
    "classroom_teacher_fte",
    "teaching_assistant_fte",
    "support_staff_fte",
    "teachers_without_qts_fte",
    "part_time_teacher_pct",
    "pupil_qualified_teacher_ratio",
    "pupil_teacher_ratio",
    "pupil_adult_ratio",
    "workforce_source",
    "workforce_source_dataset_id",
    "workforce_ratio_source",
    "workforce_ratio_source_dataset_id",
}


def find_relevant_benchmarks(
    benchmarks_path: Path,
    schools: pd.DataFrame,
) -> pd.DataFrame:
    """Return England plus the local-authority benchmarks represented by schools."""

    require_pyarrow()
    try:
        benchmarks = pd.read_parquet(benchmarks_path, engine="pyarrow")
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {benchmarks_path}: {exc}") from exc

    missing = sorted(_REQUIRED_COLUMNS - set(benchmarks.columns))
    if missing:
        raise SchoolFinderError(
            f"{benchmarks_path} uses an older benchmark schema. "
            "Run 'school-finder build' to rebuild it. Missing columns: "
            + ", ".join(missing)
        )

    if schools.empty:
        return benchmarks.iloc[0:0].copy()

    levels = benchmarks["benchmark_level"].fillna("").astype("string").str.casefold()
    national = levels.eq("national")
    la_codes: set[str] = set()
    if "local_authority_code" in schools.columns:
        la_codes = {
            str(value).strip()
            for value in schools["local_authority_code"].dropna()
            if str(value).strip()
        }
    local = levels.eq("local authority") & benchmarks["benchmark_code"].isin(la_codes)
    relevant = benchmarks[national | local].copy()
    order = relevant["benchmark_level"].str.casefold().map(
        {"national": 0, "local authority": 1}
    )
    return (
        relevant.assign(_level_order=order.fillna(2))
        .sort_values(["_level_order", "benchmark_name"], kind="stable")
        .drop(columns="_level_order")
        .reset_index(drop=True)
    )


def benchmark_results_from_frame(frame: pd.DataFrame) -> tuple[SchoolBenchmarks, ...]:
    records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    return tuple(school_benchmark_from_flat_record(record) for record in records)
