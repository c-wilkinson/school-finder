"""DfE Key Stage 4 performance source adapter."""

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

EES_KS4_DATASET_ID = "19e39901-a96c-be76-b9c2-6af54ae076d2"
EES_KS4_CSV_URL = (
    "https://api.education.gov.uk/statistics/v1/data-sets/"
    f"{EES_KS4_DATASET_ID}/csv"
)

CURRENT_METRICS = {
    "pupil_count": "pupil_count",
    "attainment8": "attainment8_average",
    "attainment8_english": "attainment8eng_average",
    "attainment8_maths": "attainment8mat_average",
    "attainment8_ebacc": "attainment8ebacc_average",
    "attainment8_open": "attainment8open_average",
    "english_maths_grade5_pct": "engmath_95_percent",
    "english_maths_grade4_pct": "engmath_94_percent",
    "ebacc_entry_pct": "ebacc_entering_percent",
    "ebacc_grade5_pct": "ebacc_95_percent",
    "ebacc_grade4_pct": "ebacc_94_percent",
    "ebacc_aps": "ebacc_aps_average",
    "triple_science_entry_pct": "sci_triple_entering_percent",
    "multiple_languages_entry_pct": "lan_multiple_entering_percent",
    "gcse_entries_per_pupil": "gcse_entries_average",
    "qualification_entries_per_pupil": "qual_entries_average",
}

PROGRESS_METRICS = {
    "progress8_pupil_count": "progress8_pupil_count",
    "progress8": "progress8_average",
    "progress8_english": "progress8eng_average",
    "progress8_maths": "progress8mat_average",
    "progress8_ebacc": "progress8ebacc_average",
    "progress8_open": "progress8open_average",
}


def discover_ks4_source(session: requests.Session) -> CsvSource:
    try:
        response = session.get(EES_KS4_CSV_URL, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE KS4 performance data: {exc}") from exc
    return CsvSource(
        name="DfE Key stage 4 performance",
        url=EES_KS4_CSV_URL,
        release_label=f"EES dataset {EES_KS4_DATASET_ID} (latest)",
    )


def _headline_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, str, str]:
    urn_col = find_column(frame, "school_urn", "URN")
    time_col = find_column(frame, "time_period")
    if urn_col is None or time_col is None:
        raise SchoolFinderError("DfE KS4 CSV is missing school_urn or time_period.")

    total = pd.Series(True, index=frame.index)
    for dimension in (
        "breakdown_topic",
        "breakdown",
        "sex",
        "disadvantage_status",
        "first_language",
        "prior_attainment",
        "mobility",
    ):
        col = find_column(frame, dimension)
        if col is not None:
            total &= clean_text_series(frame[col]).str.casefold().eq("total")

    headline = frame[total].copy()
    if headline.empty:
        raise SchoolFinderError("DfE KS4 CSV contained no all-pupils headline rows.")

    headline["_time_num"] = pd.to_numeric(headline[time_col], errors="coerce")
    headline = headline.dropna(subset=["_time_num"])
    if headline.empty:
        raise SchoolFinderError("DfE KS4 CSV contained no valid time periods.")
    return headline, urn_col, time_col


def _metric_values(frame: pd.DataFrame, mapping: dict[str, str]) -> dict[str, pd.Series]:
    values: dict[str, pd.Series] = {}
    for output, source_name in mapping.items():
        col = find_column(frame, source_name)
        values[output] = (
            numeric_quality(frame[col])
            if col is not None
            else pd.Series(pd.NA, index=frame.index, dtype="object")
        )
    return values


def read_ks4_quality(path: Path) -> pd.DataFrame:
    """Return current KS4 measures plus the latest published Progress 8 measures."""

    frame = read_public_csv(path, "DfE KS4")
    headline, urn_col, time_col = _headline_rows(frame)

    latest_time = int(headline["_time_num"].max())
    current = headline[headline["_time_num"] == latest_time].copy()

    la_code_col = find_column(current, "new_la_code", "local_authority_code")
    la_name_col = find_column(current, "la_name", "local_authority_name")
    result = pd.DataFrame(
        {
            "urn": clean_text_series(current[urn_col]),
            "performance_year": clean_text_series(current[time_col]),
            "local_authority_code": (
                clean_text_series(current[la_code_col]) if la_code_col else pd.NA
            ),
            "local_authority_name": (
                clean_text_series(current[la_name_col]) if la_name_col else pd.NA
            ),
            **_metric_values(current, CURRENT_METRICS),
        }
    )

    progress_columns = ["urn", "progress8_year", *PROGRESS_METRICS]
    progress = pd.DataFrame(columns=progress_columns)
    progress_col = find_column(headline, "progress8_average")
    if progress_col is not None:
        p8 = headline.copy()
        p8["_progress8"] = numeric_quality(p8[progress_col])
        p8 = (
            p8[p8["_progress8"].notna()]
            .sort_values([urn_col, "_time_num"], kind="stable")
            .drop_duplicates(urn_col, keep="last")
        )
        if not p8.empty:
            progress = pd.DataFrame(
                {
                    "urn": clean_text_series(p8[urn_col]),
                    "progress8_year": clean_text_series(p8[time_col]),
                    **_metric_values(p8, PROGRESS_METRICS),
                }
            )

    result = result[result["urn"].ne("")].drop_duplicates("urn", keep="last")
    result = result.merge(progress, on="urn", how="outer")
    return result.reset_index(drop=True)
