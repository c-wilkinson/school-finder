"""DfE Key Stage 4 performance source adapter."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from school_finder.errors import SchoolFinderError
from school_finder.data.sources.common import (
    CsvSource,
    clean_text_series,
    find_column,
    numeric_quality,
    read_public_csv,
)

EES_KS4_DATASET_ID = "19e39901-a96c-be76-b9c2-6af54ae076d2"

EES_KS4_CSV_URL = (
    "https://api.education.gov.uk/statistics/v1/data-sets/"
    f"{EES_KS4_DATASET_ID}/csv"
)


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


def read_ks4_quality(path: Path) -> pd.DataFrame:
    frame = read_public_csv(path, "DfE KS4")
    urn_col = find_column(frame, "school_urn", "URN")
    time_col = find_column(frame, "time_period")
    if urn_col is None or time_col is None:
        raise SchoolFinderError("DfE KS4 CSV is missing school_urn or time_period.")

    total = pd.Series(True, index=frame.index)
    for dimension in (
        "breakdown_topic", "breakdown", "sex", "disadvantage_status",
        "first_language", "prior_attainment", "mobility",
    ):
        col = find_column(frame, dimension)
        if col is not None:
            total &= clean_text_series(frame[col]).str.casefold().eq("total")
    headline = frame[total].copy()
    if headline.empty:
        raise SchoolFinderError("DfE KS4 CSV contained no all-pupils headline rows.")

    headline["_time_num"] = pd.to_numeric(headline[time_col], errors="coerce")
    headline = headline.dropna(subset=["_time_num"])
    latest_time = int(headline["_time_num"].max())
    current = headline[headline["_time_num"] == latest_time].copy()

    result = pd.DataFrame({
        "urn": clean_text_series(current[urn_col]),
        "performance_year": clean_text_series(current[time_col]),
    })
    metrics = {
        "attainment8": "attainment8_average",
        "english_maths_grade5_pct": "engmath_95_percent",
        "english_maths_grade4_pct": "engmath_94_percent",
        "ebacc_entry_pct": "ebacc_entering_percent",
        "ebacc_aps": "ebacc_aps_average",
    }
    for output, source_name in metrics.items():
        col = find_column(current, source_name)
        result[output] = numeric_quality(current[col]) if col else pd.NA

    progress_col = find_column(headline, "progress8_average")
    progress = pd.DataFrame(columns=["urn", "progress8", "progress8_year"])
    if progress_col is not None:
        p8 = headline[[urn_col, time_col, "_time_num", progress_col]].copy()
        p8["progress8"] = numeric_quality(p8[progress_col])
        p8 = p8.dropna(subset=["progress8"]).sort_values(
            [urn_col, "_time_num"], kind="stable"
        ).drop_duplicates(urn_col, keep="last")
        progress = pd.DataFrame({
            "urn": clean_text_series(p8[urn_col]),
            "progress8": p8["progress8"].astype("float64"),
            "progress8_year": clean_text_series(p8[time_col]),
        })

    result = result[result["urn"].ne("")].drop_duplicates("urn", keep="last")
    result = result.merge(progress, on="urn", how="outer")
    return result.reset_index(drop=True)
