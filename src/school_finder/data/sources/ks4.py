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
KS4_SOURCE_NAME = "DfE Key stage 4 performance"

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
        name=KS4_SOURCE_NAME,
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


def _history_from_headline(
    headline: pd.DataFrame,
    urn_col: str,
    time_col: str,
) -> pd.DataFrame:
    la_code_col = find_column(headline, "new_la_code", "local_authority_code")
    la_name_col = find_column(headline, "la_name", "local_authority_name")
    result = pd.DataFrame(
        {
            "urn": clean_text_series(headline[urn_col]),
            "performance_year": clean_text_series(headline[time_col]),
            "local_authority_code": (
                clean_text_series(headline[la_code_col]) if la_code_col else pd.NA
            ),
            "local_authority_name": (
                clean_text_series(headline[la_name_col]) if la_name_col else pd.NA
            ),
            **_metric_values(headline, CURRENT_METRICS),
            **_metric_values(headline, PROGRESS_METRICS),
        }
    )
    return (
        result[result["urn"].ne("") & result["performance_year"].ne("")]
        .drop_duplicates(["urn", "performance_year"], keep="last")
        .reset_index(drop=True)
    )


def read_ks4_history(path: Path) -> pd.DataFrame:
    """Return all published all-pupils KS4 headline rows by school and year."""
    frame = read_public_csv(path, "DfE KS4")
    headline, urn_col, time_col = _headline_rows(frame)
    return _history_from_headline(headline, urn_col, time_col)


def read_ks4_quality(path: Path) -> pd.DataFrame:
    """Return current KS4 measures plus the latest published Progress 8 measures."""

    frame = read_public_csv(path, "DfE KS4")
    headline, urn_col, time_col = _headline_rows(frame)
    history = _history_from_headline(headline, urn_col, time_col)

    latest_time = int(headline["_time_num"].max())
    current_years = clean_text_series(
        headline.loc[headline["_time_num"].eq(latest_time), time_col]
    )
    latest_label = current_years.iloc[-1]

    current_columns = [
        "urn",
        "performance_year",
        "local_authority_code",
        "local_authority_name",
        *CURRENT_METRICS,
    ]
    result = history[history["performance_year"].eq(latest_label)][current_columns].copy()

    progress_columns = ["urn", "progress8_year", *PROGRESS_METRICS]
    progress = pd.DataFrame(columns=progress_columns)
    p8 = history[history["progress8"].notna()].copy()
    if not p8.empty:
        p8["_time_num"] = pd.to_numeric(p8["performance_year"], errors="coerce")
        p8 = (
            p8.dropna(subset=["_time_num"])
            .sort_values(["urn", "_time_num"], kind="stable")
            .drop_duplicates("urn", keep="last")
        )
        progress = p8[["urn", "performance_year", *PROGRESS_METRICS]].rename(
            columns={"performance_year": "progress8_year"}
        )

    result = result[result["urn"].ne("")].drop_duplicates("urn", keep="last")
    result = result.merge(progress, on="urn", how="outer")
    return result.reset_index(drop=True)
