"""DfE Key Stage 4 national and local-authority benchmark adapter."""

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
from school_finder.data.sources.ks4 import CURRENT_METRICS, PROGRESS_METRICS
from school_finder.errors import SchoolFinderError

EES_KS4_BENCHMARK_DATASET_ID = "19e39901-560d-f972-b6f3-dd085539c095"
EES_KS4_BENCHMARK_CSV_URL = (
    "https://api.education.gov.uk/statistics/v1/data-sets/"
    f"{EES_KS4_BENCHMARK_DATASET_ID}/csv"
)
BENCHMARK_SOURCE_NAME = "DfE Key stage 4 performance benchmarks"


def discover_ks4_benchmark_source(session: requests.Session) -> CsvSource:
    try:
        response = session.get(
            EES_KS4_BENCHMARK_CSV_URL,
            stream=True,
            timeout=(15, 60),
        )
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(
            f"Could not retrieve DfE KS4 benchmark data: {exc}"
        ) from exc
    return CsvSource(
        name=BENCHMARK_SOURCE_NAME,
        url=EES_KS4_BENCHMARK_CSV_URL,
        release_label=f"EES dataset {EES_KS4_BENCHMARK_DATASET_ID} (latest)",
    )


def _headline_rows(frame: pd.DataFrame) -> pd.DataFrame:
    time_col = find_column(frame, "time_period")
    level_col = find_column(frame, "geographic_level")
    if time_col is None or level_col is None:
        raise SchoolFinderError(
            "DfE KS4 benchmark CSV is missing time_period or geographic_level."
        )

    total = pd.Series(True, index=frame.index)
    for dimension in ("breakdown_topic", "breakdown"):
        col = find_column(frame, dimension)
        if col is not None:
            total &= clean_text_series(frame[col]).str.casefold().eq("total")

    establishment_col = find_column(frame, "establishment_type_group")
    if establishment_col is not None:
        total &= (
            clean_text_series(frame[establishment_col])
            .str.casefold()
            .eq("all state-funded")
        )

    levels = clean_text_series(frame[level_col]).str.casefold()
    total &= levels.isin({"national", "local authority"})

    headline = frame[total].copy()
    if headline.empty:
        raise SchoolFinderError(
            "DfE KS4 benchmark CSV contained no all-pupils national or local-authority rows."
        )
    headline["_time_num"] = pd.to_numeric(headline[time_col], errors="coerce")
    headline = headline.dropna(subset=["_time_num"])
    if headline.empty:
        raise SchoolFinderError(
            "DfE KS4 benchmark CSV contained no valid time periods."
        )
    return headline


def _benchmark_identity(frame: pd.DataFrame) -> pd.DataFrame:
    level_col = find_column(frame, "geographic_level")
    country_code_col = find_column(frame, "country_code")
    country_name_col = find_column(frame, "country_name")
    la_code_col = find_column(frame, "new_la_code", "local_authority_code")
    la_name_col = find_column(frame, "la_name", "local_authority_name")
    if any(
        column is None
        for column in (
            level_col,
            country_code_col,
            country_name_col,
            la_code_col,
            la_name_col,
        )
    ):
        raise SchoolFinderError(
            "DfE KS4 benchmark CSV is missing national/local-authority identity columns."
        )

    levels = clean_text_series(frame[level_col])
    national = levels.str.casefold().eq("national")
    return pd.DataFrame(
        {
            "benchmark_level": levels,
            "benchmark_code": clean_text_series(frame[la_code_col]).where(
                ~national,
                clean_text_series(frame[country_code_col]),
            ),
            "benchmark_name": clean_text_series(frame[la_name_col]).where(
                ~national,
                clean_text_series(frame[country_name_col]),
            ),
        },
        index=frame.index,
    )


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


def read_ks4_benchmarks(path: Path) -> pd.DataFrame:
    """Return current England/LA benchmarks plus latest published Progress 8."""

    frame = read_public_csv(path, "DfE KS4 benchmarks")
    headline = _headline_rows(frame)
    time_col = find_column(headline, "time_period")
    assert time_col is not None

    latest_time = int(headline["_time_num"].max())
    current = headline[headline["_time_num"] == latest_time].copy()
    result = _benchmark_identity(current)
    result["performance_year"] = clean_text_series(current[time_col])
    for name, values in _metric_values(current, CURRENT_METRICS).items():
        result[name] = values

    progress_columns = ["progress8_year", *PROGRESS_METRICS]
    for column in progress_columns:
        result[column] = pd.NA

    progress_col = find_column(headline, "progress8_average")
    if progress_col is not None:
        p8 = headline.copy()
        p8["_progress8"] = numeric_quality(p8[progress_col])
        p8 = p8[p8["_progress8"].notna()].copy()
        if not p8.empty:
            identity = _benchmark_identity(p8)
            p8 = pd.concat(
                [
                    identity.reset_index(drop=True),
                    p8.reset_index(drop=True),
                ],
                axis=1,
            )
            p8 = (
                p8.sort_values(
                    ["benchmark_level", "benchmark_code", "_time_num"],
                    kind="stable",
                )
                .drop_duplicates(["benchmark_level", "benchmark_code"], keep="last")
            )
            progress = p8[["benchmark_level", "benchmark_code"]].copy()
            progress["progress8_year"] = clean_text_series(p8[time_col])
            for name, values in _metric_values(p8, PROGRESS_METRICS).items():
                progress[name] = values
            result = result.drop(columns=progress_columns).merge(
                progress,
                on=["benchmark_level", "benchmark_code"],
                how="left",
                validate="one_to_one",
            )

    result["source"] = BENCHMARK_SOURCE_NAME
    result["source_dataset_id"] = EES_KS4_BENCHMARK_DATASET_ID
    result = result[result["benchmark_code"].ne("")].drop_duplicates(
        ["benchmark_level", "benchmark_code"], keep="last"
    )
    level_order = result["benchmark_level"].str.casefold().map(
        {"national": 0, "local authority": 1}
    )
    return (
        result.assign(_level_order=level_order.fillna(2))
        .sort_values(["_level_order", "benchmark_name"], kind="stable")
        .drop(columns="_level_order")
        .reset_index(drop=True)
    )
