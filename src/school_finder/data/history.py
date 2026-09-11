"""Historical metric normalisation and school-lineage resolution."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

SCHOOL_HISTORY_COLUMNS = (
    "urn",
    "domain",
    "year",
    "metric",
    "value",
    "source_urn",
    "source_school_name",
    "source_kind",
    "source_link_depth",
)

BENCHMARK_HISTORY_COLUMNS = (
    "benchmark_level",
    "benchmark_code",
    "benchmark_name",
    "domain",
    "year",
    "metric",
    "value",
)


def normalise_school_history(
    frame: pd.DataFrame,
    *,
    domain: str,
    year_column: str,
    metric_columns: Iterable[str],
) -> pd.DataFrame:
    """Convert a wide school/year frame into a compact long metric history."""
    metrics = [column for column in metric_columns if column in frame.columns]
    required = {"urn", year_column}
    if frame.empty or not required.issubset(frame.columns) or not metrics:
        return pd.DataFrame(columns=["urn", "domain", "year", "metric", "value"])

    work = frame[["urn", year_column, *metrics]].copy()
    work["urn"] = work["urn"].fillna("").astype("string").str.strip()
    work[year_column] = work[year_column].fillna("").astype("string").str.strip()
    long = work.melt(
        id_vars=["urn", year_column],
        value_vars=metrics,
        var_name="metric",
        value_name="value",
    ).rename(columns={year_column: "year"})
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long["domain"] = domain
    long = long[
        long["urn"].ne("") & long["year"].ne("") & long["value"].notna()
    ]
    return (
        long[["urn", "domain", "year", "metric", "value"]]
        .drop_duplicates(["urn", "domain", "year", "metric"], keep="last")
        .reset_index(drop=True)
    )


def normalise_benchmark_history(
    frame: pd.DataFrame,
    *,
    domain: str,
    year_column: str,
    metric_columns: Iterable[str],
) -> pd.DataFrame:
    """Convert a wide geography/year frame into long benchmark history."""
    metrics = [column for column in metric_columns if column in frame.columns]
    identity = ["benchmark_level", "benchmark_code", "benchmark_name"]
    required = {*identity, year_column}
    if frame.empty or not required.issubset(frame.columns) or not metrics:
        return pd.DataFrame(columns=BENCHMARK_HISTORY_COLUMNS)

    work = frame[[*identity, year_column, *metrics]].copy()
    for column in identity:
        work[column] = work[column].fillna("").astype("string").str.strip()
    work[year_column] = work[year_column].fillna("").astype("string").str.strip()
    long = work.melt(
        id_vars=[*identity, year_column],
        value_vars=metrics,
        var_name="metric",
        value_name="value",
    ).rename(columns={year_column: "year"})
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long["domain"] = domain
    long = long[
        long["benchmark_code"].ne("")
        & long["year"].ne("")
        & long["value"].notna()
    ]
    return (
        long[list(BENCHMARK_HISTORY_COLUMNS)]
        .drop_duplicates(
            ["benchmark_level", "benchmark_code", "domain", "year", "metric"],
            keep="last",
        )
        .reset_index(drop=True)
    )


def _lineage_graph(
    schools: pd.DataFrame,
    links: pd.DataFrame,
) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str]]:
    predecessors: dict[str, list[str]] = {}
    predecessor_names: dict[str, str] = {}
    if not links.empty:
        for _, row in links.iterrows():
            successor = str(row.get("successor_urn", "")).strip()
            predecessor = str(row.get("predecessor_urn", "")).strip()
            if not successor or not predecessor:
                continue
            predecessors.setdefault(successor, [])
            if predecessor not in predecessors[successor]:
                predecessors[successor].append(predecessor)
            name = str(row.get("predecessor_name", "")).strip()
            if name:
                predecessor_names[predecessor] = name

    current_names = {
        str(row.get("urn", "")).strip(): str(row.get("school_name", "")).strip()
        for _, row in schools.iterrows()
        if str(row.get("urn", "")).strip()
    }
    return predecessors, predecessor_names, current_names


def resolve_school_history_lineage(
    schools: pd.DataFrame,
    links: pd.DataFrame,
    history: pd.DataFrame,
) -> pd.DataFrame:
    """Attach current URNs to history from unambiguous predecessor chains.

    For the same domain/year/metric, the current school wins over a predecessor and
    the nearest predecessor wins over an older one.
    """
    if history.empty:
        return pd.DataFrame(columns=SCHOOL_HISTORY_COLUMNS)

    predecessors, predecessor_names, current_names = _lineage_graph(schools, links)
    names = {**predecessor_names, **current_names}
    grouped = {
        str(urn).strip(): group.copy()
        for urn, group in history.groupby("urn", sort=False)
        if str(urn).strip()
    }

    resolved: list[pd.DataFrame] = []
    for current_urn, current_name in current_names.items():
        cursor = current_urn
        visited = {current_urn}
        depth = 0
        while True:
            source = grouped.get(cursor)
            if source is not None and not source.empty:
                work = source[["domain", "year", "metric", "value"]].copy()
                work["urn"] = current_urn
                work["source_urn"] = cursor
                work["source_school_name"] = names.get(cursor) or current_name or None
                work["source_kind"] = "current" if depth == 0 else "predecessor"
                work["source_link_depth"] = depth
                resolved.append(work)

            candidates = predecessors.get(cursor, [])
            if len(candidates) != 1:
                break
            predecessor_urn = candidates[0]
            if predecessor_urn in visited:
                break
            visited.add(predecessor_urn)
            cursor = predecessor_urn
            depth += 1

    if not resolved:
        return pd.DataFrame(columns=SCHOOL_HISTORY_COLUMNS)

    combined = pd.concat(resolved, ignore_index=True)
    return (
        combined[list(SCHOOL_HISTORY_COLUMNS)]
        .sort_values(
            ["urn", "domain", "year", "metric", "source_link_depth"],
            kind="stable",
        )
        .drop_duplicates(["urn", "domain", "year", "metric"], keep="first")
        .reset_index(drop=True)
    )


def combine_benchmark_history(*frames: pd.DataFrame) -> pd.DataFrame:
    """Combine domain histories and keep one metric value per geography/year."""
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        return pd.DataFrame(columns=BENCHMARK_HISTORY_COLUMNS)
    combined = pd.concat(usable, ignore_index=True)
    return (
        combined[list(BENCHMARK_HISTORY_COLUMNS)]
        .drop_duplicates(
            ["benchmark_level", "benchmark_code", "domain", "year", "metric"],
            keep="last",
        )
        .reset_index(drop=True)
    )
