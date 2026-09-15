"""DfE school-level applications and offers source adapter."""

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

ADMISSIONS_SOURCE_URL = (
    "https://content.explore-education-statistics.service.gov.uk/api/releases/"
    "0bf4f9cf-721d-44e3-8473-266c87e17e00/files/"
    "42d0d4e4-9604-413a-8275-00b829ffbdcb"
)
ADMISSIONS_SOURCE_NAME = "DfE school applications and offers - school level"
ADMISSIONS_RELEASE_LABEL = "School level applications and offers 2026 (2014 to 2026)"

ADMISSIONS_METRICS = {
    "first_preferences": (
        "first_preferences", "first preference", "1st preferences", "1st preferences expressed", "preference1", "pref1", "firstprefs", "first_pref"
    ),
    "second_preferences": (
        "second_preferences", "second preference", "2nd preferences", "2nd preferences expressed", "preference2", "pref2", "secondprefs", "second_pref"
    ),
    "third_preferences": (
        "third_preferences", "third preference", "3rd preferences", "3rd preferences expressed", "preference3", "pref3", "thirdprefs", "third_pref"
    ),
    "total_preferences": (
        "total_preferences", "total preference", "total preferences", "any preferences", "all preferences", "preferences_total", "totalprefs"
    ),
    "first_preference_offers": (
        "first_preference_offers", "first preference offers", "1st preference offers", "1st preference offers made", "offer1", "offers1", "firstoffers"
    ),
    "second_preference_offers": (
        "second_preference_offers", "second preference offers", "2nd preference offers", "2nd preference offers made", "offer2", "offers2", "secondoffers"
    ),
    "third_preference_offers": (
        "third_preference_offers", "third preference offers", "3rd preference offers", "3rd preference offers made", "offer3", "offers3", "thirdoffers"
    ),
    "total_offers": (
        "total_offers", "total offers", "any offers", "all offers", "offers_total", "totaloffers"
    ),
    "outside_la_preferences": (
        "outside_la_preferences", "outside la preferences", "preferences outside la", "out of la preferences", "preferences from outside la"
    ),
    "outside_la_offers": (
        "outside_la_offers", "outside la offers", "offers outside la", "out of la offers", "offers to outside la applicants"
    ),
}


def _source() -> CsvSource:
    return CsvSource(
        name=ADMISSIONS_SOURCE_NAME,
        url=ADMISSIONS_SOURCE_URL,
        release_label=ADMISSIONS_RELEASE_LABEL,
    )


def discover_admissions_source(session: requests.Session) -> CsvSource:
    """Validate the currently configured DfE school-level supporting file."""
    source = _source()
    try:
        response = session.get(source.url, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(
            f"Could not retrieve DfE school admissions data: {exc}"
        ) from exc
    return source


def _column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    return find_column(frame, *aliases)


def _required_column(frame: pd.DataFrame, label: str, *aliases: str) -> str:
    column = find_column(frame, *aliases)
    if column is None:
        raise SchoolFinderError(f"DfE admissions CSV is missing {label}.")
    return column


def _metric_values(frame: pd.DataFrame) -> dict[str, pd.Series]:
    values: dict[str, pd.Series] = {}
    for output, aliases in ADMISSIONS_METRICS.items():
        column = _column(frame, aliases)
        values[output] = (
            numeric_quality(frame[column])
            if column is not None
            else pd.Series(pd.NA, index=frame.index, dtype="object")
        )
    return values


def _normalise_year(series: pd.Series) -> pd.Series:
    values = clean_text_series(series)
    # Some historic files use a plain entry year, while others use an academic-year label.
    return values.str.replace(r"\.0$", "", regex=True)


def _is_secondary(frame: pd.DataFrame) -> pd.Series:
    phase_col = find_column(
        frame,
        "school_phase",
        "phase",
        "phase_type_grouping",
        "school_type",
        "primary_secondary",
        "phase_of_education",
    )
    if phase_col is None:
        raise SchoolFinderError("DfE admissions CSV is missing school phase.")
    phase = clean_text_series(frame[phase_col]).str.casefold()
    return phase.str.contains("secondary", na=False)


def _aggregate(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate split admission routes to one school/year where a URN is known."""
    metric_columns = tuple(ADMISSIONS_METRICS)
    grouped = (
        frame.groupby(["urn", "admission_year"], as_index=False, sort=False)
        .agg(
            school_name=("school_name", "last"),
            laestab=("laestab", "last"),
            **{column: (column, lambda values: values.sum(min_count=1)) for column in metric_columns},
        )
    )
    offers = pd.to_numeric(grouped["total_offers"], errors="coerce")
    first = pd.to_numeric(grouped["first_preferences"], errors="coerce")
    grouped["first_preferences_per_offer"] = first.div(offers.where(offers > 0))

    # Percentiles are deliberately calculated within each entry year so the band
    # describes demand relative to other secondary schools in the same cycle.
    grouped["admissions_demand_percentile"] = grouped.groupby("admission_year")[
        "first_preferences_per_offer"
    ].rank(method="average", pct=True) * 100

    percentile = grouped["admissions_demand_percentile"]
    grouped["admissions_demand_band"] = pd.Series(pd.NA, index=grouped.index, dtype="string")
    grouped.loc[percentile.notna() & (percentile <= 25), "admissions_demand_band"] = "Low"
    grouped.loc[percentile.notna() & (percentile > 25) & (percentile <= 75), "admissions_demand_band"] = "Moderate"
    grouped.loc[percentile.notna() & (percentile > 75) & (percentile <= 90), "admissions_demand_band"] = "High"
    grouped.loc[percentile.notna() & (percentile > 90), "admissions_demand_band"] = "Very high"
    grouped["admissions_source"] = ADMISSIONS_SOURCE_NAME
    grouped["admissions_source_url"] = ADMISSIONS_SOURCE_URL
    return grouped


def read_admissions_history(path: Path) -> pd.DataFrame:
    """Return all usable secondary-school applications/offers rows by entry year."""
    frame = read_public_csv(path, "DfE school applications and offers")
    urn_col = _required_column(frame, "school URN", "school_urn", "urn", "urn_gias")
    year_col = _required_column(
        frame,
        "entry year",
        "admission_year",
        "entry_year",
        "time_period",
        "year",
        "academic_year",
        "entryyear",
        "collection_year",
    )
    name_col = find_column(frame, "school_name", "establishment_name", "school", "establishmentname")
    laestab_col = find_column(frame, "school_laestab", "laestab", "la_estab", "laestab_gias")

    rows = frame[_is_secondary(frame)].copy()
    if rows.empty:
        raise SchoolFinderError("DfE admissions CSV contained no secondary-school rows.")

    result = pd.DataFrame(
        {
            "urn": clean_text_series(rows[urn_col]),
            "admission_year": _normalise_year(rows[year_col]),
            "school_name": (
                clean_text_series(rows[name_col])
                if name_col is not None
                else pd.Series("", index=rows.index, dtype="string")
            ),
            "laestab": (
                clean_text_series(rows[laestab_col])
                if laestab_col is not None
                else pd.Series("", index=rows.index, dtype="string")
            ),
            **_metric_values(rows),
        },
        index=rows.index,
    )
    result = result[result["urn"].ne("") & result["admission_year"].ne("")].copy()
    if result.empty:
        raise SchoolFinderError("DfE admissions CSV contained no identifiable secondary schools.")
    return _aggregate(result).reset_index(drop=True)


def _year_key(value: object) -> int:
    text = str(value or "").strip()
    digits = "".join(character for character in text if character.isdigit())
    return int(digits[:4] or 0)


def read_admissions_school(path: Path) -> pd.DataFrame:
    """Return the latest published applications/offers row for each school."""
    history = read_admissions_history(path).copy()
    history["_year_key"] = history["admission_year"].map(_year_key)
    return (
        history.sort_values(["urn", "_year_key"], kind="stable")
        .drop_duplicates("urn", keep="last")
        .drop(columns="_year_key")
        .reset_index(drop=True)
    )
