"""DfE Key Stage 4 school-level subject entries and grades adapter."""

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

EES_KS4_SUBJECTS_DATASET_ID = "1ae39901-b462-df76-b108-640a078d7944"
EES_KS4_SUBJECTS_CSV_URL = (
    "https://api.education.gov.uk/statistics/v1/data-sets/"
    f"{EES_KS4_SUBJECTS_DATASET_ID}/csv"
)
SUBJECT_SOURCE_NAME = "DfE Key stage 4 subject entries and grades"


def discover_ks4_subject_source(session: requests.Session) -> CsvSource:
    try:
        response = session.get(EES_KS4_SUBJECTS_CSV_URL, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE KS4 subject data: {exc}") from exc
    return CsvSource(
        name=SUBJECT_SOURCE_NAME,
        url=EES_KS4_SUBJECTS_CSV_URL,
        release_label=f"EES dataset {EES_KS4_SUBJECTS_DATASET_ID} (latest)",
    )


def _is_nine_to_one(qualification: str, grade_structure: str) -> bool:
    text = f"{qualification} {grade_structure}".casefold()
    return "9-1" in text or ("9 / 8 / 7" in text and "gcse" in text)


def _safe_sum(values: pd.Series) -> float | None:
    numeric = numeric_quality(values)
    if numeric.isna().any():
        return None
    return float(numeric.sum())


def _threshold_count(grades: pd.Series, values: pd.Series, threshold: int) -> float | None:
    numeric = numeric_quality(values)
    if numeric.isna().any():
        return None
    grade_numbers = pd.to_numeric(clean_text_series(grades), errors="coerce")
    return float(numeric[grade_numbers.ge(threshold)].sum())


def read_ks4_subjects(path: Path) -> pd.DataFrame:
    """Aggregate grade rows into one canonical row per school/subject/qualification."""

    frame = read_public_csv(path, "DfE KS4 subjects")
    urn_col = find_column(frame, "school_urn", "urn")
    time_col = find_column(frame, "time_period")
    subject_col = find_column(frame, "subject_discount_group", "subject")
    qualification_col = find_column(frame, "qualification_detailed", "qualification_type")
    grade_col = find_column(frame, "grade")
    count_col = find_column(frame, "number_achieving")
    if any(
        column is None
        for column in (urn_col, time_col, subject_col, qualification_col, grade_col, count_col)
    ):
        raise SchoolFinderError(
            "DfE KS4 subject CSV is missing school, time, subject, qualification or grade columns."
        )

    level_col = find_column(frame, "geographic_level")
    if level_col is not None:
        frame = frame[clean_text_series(frame[level_col]).str.casefold().eq("school")].copy()

    frame["_time_num"] = pd.to_numeric(frame[time_col], errors="coerce")
    frame = frame.dropna(subset=["_time_num"])
    if frame.empty:
        raise SchoolFinderError("DfE KS4 subject CSV contained no valid time periods.")
    latest = int(frame["_time_num"].max())
    frame = frame[frame["_time_num"] == latest].copy()

    grade_structure_col = find_column(frame, "grade_structure")
    work = pd.DataFrame(
        {
            "urn": clean_text_series(frame[urn_col]),
            "data_year": clean_text_series(frame[time_col]),
            "subject": clean_text_series(frame[subject_col]),
            "qualification": clean_text_series(frame[qualification_col]),
            "grade_structure": (
                clean_text_series(frame[grade_structure_col]) if grade_structure_col else ""
            ),
            "grade": clean_text_series(frame[grade_col]),
            "number_achieving": frame[count_col],
        }
    )
    work = work[work["urn"].ne("") & work["subject"].ne("")].copy()

    rows: list[dict[str, object]] = []
    group_cols = ["urn", "data_year", "subject", "qualification", "grade_structure"]
    for key, group in work.groupby(group_cols, dropna=False, sort=False):
        urn, data_year, subject, qualification, grade_structure = key
        qualification_text = str(qualification or "")
        grade_structure_text = str(grade_structure or "")
        entries = _safe_sum(group["number_achieving"])
        row: dict[str, object] = {
            "urn": urn,
            "data_year": data_year,
            "subject": subject,
            "qualification": qualification_text or None,
            "grade_structure": grade_structure_text or None,
            "entries": entries,
            "grade4_plus": None,
            "grade4_plus_pct": None,
            "grade5_plus": None,
            "grade5_plus_pct": None,
            "grade7_plus": None,
            "grade7_plus_pct": None,
            "source": SUBJECT_SOURCE_NAME,
            "source_dataset_id": EES_KS4_SUBJECTS_DATASET_ID,
        }
        if entries is not None and entries > 0 and _is_nine_to_one(
            qualification_text, grade_structure_text
        ):
            for threshold, prefix in ((4, "grade4_plus"), (5, "grade5_plus"), (7, "grade7_plus")):
                count = _threshold_count(group["grade"], group["number_achieving"], threshold)
                row[prefix] = count
                row[f"{prefix}_pct"] = (
                    round(count / entries * 100.0, 3) if count is not None else None
                )
        rows.append(row)

    columns = [
        "urn",
        "data_year",
        "subject",
        "qualification",
        "grade_structure",
        "entries",
        "grade4_plus",
        "grade4_plus_pct",
        "grade5_plus",
        "grade5_plus_pct",
        "grade7_plus",
        "grade7_plus_pct",
        "source",
        "source_dataset_id",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame.from_records(rows, columns=columns)
        .sort_values(["urn", "subject", "qualification"], kind="stable", na_position="last")
        .reset_index(drop=True)
    )
