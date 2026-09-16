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

# The DfE publishes this as a supporting CSV rather than a data-catalogue dataset.
# The 2026 release contains the complete school-level time series from 2014 onwards.
ADMISSIONS_SOURCE_URL = (
    "https://content.explore-education-statistics.service.gov.uk/api/releases/"
    "0bf4f9cf-721d-44e3-8473-266c87e17e00/files/"
    "42d0d4e4-9604-413a-8275-00b829ffbdcb"
)
ADMISSIONS_SOURCE_NAME = "DfE school applications and offers - school level"
ADMISSIONS_RELEASE_LABEL = "School level applications and offers 2026 (2014 to 2026)"

ADMISSIONS_METRICS = {
    "first_preferences": (
        "first_preferences", "first preference", "first preferences", "1st preference",
        "1st preferences", "1st preferences expressed", "number of first preferences",
        "number of 1st preferences", "first prefs", "1st prefs", "preference1", "pref1",
        "firstprefs", "first_pref", "firstpref", "times_put_as_1st_preference",
    ),
    "second_preferences": (
        "second_preferences", "second preference", "second preferences", "2nd preference",
        "2nd preferences", "2nd preferences expressed", "number of second preferences",
        "number of 2nd preferences", "second prefs", "2nd prefs", "preference2", "pref2",
        "secondprefs", "second_pref", "secondpref", "times_put_as_2nd_preference",
    ),
    "third_preferences": (
        "third_preferences", "third preference", "third preferences", "3rd preference",
        "3rd preferences", "3rd preferences expressed", "number of third preferences",
        "number of 3rd preferences", "third prefs", "3rd prefs", "preference3", "pref3",
        "thirdprefs", "third_pref", "thirdpref", "times_put_as_3rd_preference",
    ),
    "total_preferences": (
        "total_preferences", "total preference", "total preferences", "number of total preferences",
        "any preferences", "all preferences", "preferences_total", "totalprefs", "total prefs",
        "times_put_as_any_preferred_school",
    ),
    "first_preference_offers": (
        "first_preference_offers", "first preference offers", "1st preference offers",
        "1st preference offers made", "number of first preference offers",
        "number of 1st preference offers", "first pref offers", "1st pref offers",
        "offer1", "offers1", "firstoffers", "first_offer", "number_1st_preference_offers",
    ),
    "second_preference_offers": (
        "second_preference_offers", "second preference offers", "2nd preference offers",
        "2nd preference offers made", "number of second preference offers",
        "number of 2nd preference offers", "second pref offers", "2nd pref offers",
        "offer2", "offers2", "secondoffers", "second_offer", "number_2nd_preference_offers",
    ),
    "third_preference_offers": (
        "third_preference_offers", "third preference offers", "3rd preference offers",
        "3rd preference offers made", "number of third preference offers",
        "number of 3rd preference offers", "third pref offers", "3rd pref offers",
        "offer3", "offers3", "thirdoffers", "third_offer", "number_3rd_preference_offers",
    ),
    "total_offers": (
        "total_offers", "total offers", "number of total offers", "any offers", "all offers",
        "offers_total", "totaloffers", "total_number_places_offered",
    ),
    "outside_la_preferences": (
        "outside_la_preferences", "outside la preferences", "preferences outside la",
        "out of la preferences", "preferences from outside la", "preferences from other la",
        "outside home la preferences", "all_applications_from_another_la",
    ),
    "outside_la_offers": (
        "outside_la_offers", "outside la offers", "offers outside la", "out of la offers",
        "offers to outside la applicants", "offers to applicants from outside la",
        "outside home la offers", "offers_to_applicants_from_another_la",
    ),
}

_MISSING_IDENTIFIERS = {"", "na", "n/a", "none", "not applicable", "z", "c", "-"}


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
    columns = {
        output: _column(frame, aliases)
        for output, aliases in ADMISSIONS_METRICS.items()
    }
    missing_core = [
        output
        for output in ("first_preferences", "total_offers")
        if columns[output] is None
    ]
    if missing_core:
        missing = ", ".join(missing_core)
        raise SchoolFinderError(
            "DfE admissions CSV is missing core school-level admissions fields "
            f"({missing}). The publisher schema may have changed."
        )

    values: dict[str, pd.Series] = {}
    for output, column in columns.items():
        values[output] = (
            numeric_quality(frame[column])
            if column is not None
            else pd.Series(pd.NA, index=frame.index, dtype="object")
        )
    return values


def _normalise_year(series: pd.Series) -> pd.Series:
    values = clean_text_series(series)
    return values.str.replace(r"\.0$", "", regex=True)


def _clean_identifier(series: pd.Series) -> pd.Series:
    values = clean_text_series(series).str.replace(r"\.0$", "", regex=True)
    lowered = values.str.casefold()
    return values.mask(lowered.isin(_MISSING_IDENTIFIERS), "")


def _normalise_laestab(series: pd.Series) -> pd.Series:
    values = _clean_identifier(series)
    digits = values.str.replace(r"[^0-9]", "", regex=True)
    return digits.where(values.ne(""), "")


def _laestab_values(frame: pd.DataFrame) -> pd.Series:
    combined_col = find_column(
        frame,
        "school_laestab",
        "laestab",
        "la_estab",
        "laestab_gias",
        "school laestab",
        "school la estab",
    )
    if combined_col is not None:
        return _normalise_laestab(frame[combined_col])

    la_col = find_column(
        frame,
        "school_la",
        "la",
        "la_code",
        "la code",
        "school_la_code",
        "local_authority_code",
    )
    estab_col = find_column(
        frame,
        "school_estab",
        "estab",
        "establishment_number",
        "establishment number",
        "school_establishment_number",
        "dfe_estab",
        "dfe estab",
    )
    if la_col is None or estab_col is None:
        return pd.Series("", index=frame.index, dtype="string")

    la = _clean_identifier(frame[la_col]).str.replace(r"[^0-9]", "", regex=True)
    estab = _clean_identifier(frame[estab_col]).str.replace(r"[^0-9]", "", regex=True)
    valid = la.ne("") & estab.ne("")
    result = pd.Series("", index=frame.index, dtype="string")
    result.loc[valid] = la.loc[valid].str.zfill(3) + estab.loc[valid].str.zfill(4)
    return result


def _is_secondary(frame: pd.DataFrame) -> pd.Series:
    phase_col = find_column(
        frame,
        "school_phase",
        "phase",
        "phase_type_grouping",
        "school_type",
        "primary_secondary",
        "phase_of_education",
        "school phase",
    )
    if phase_col is None:
        raise SchoolFinderError("DfE admissions CSV is missing school phase.")
    phase = clean_text_series(frame[phase_col]).str.casefold()
    return phase.str.contains("secondary", na=False)


def _last_nonblank(values: pd.Series) -> str:
    cleaned = _clean_identifier(values)
    nonblank = cleaned[cleaned.ne("")]
    return str(nonblank.iloc[-1]) if not nonblank.empty else ""


def _apply_demand_metrics(grouped: pd.DataFrame) -> pd.DataFrame:
    grouped = grouped.copy()
    offers = pd.to_numeric(grouped["total_offers"], errors="coerce")
    first = pd.to_numeric(grouped["first_preferences"], errors="coerce")
    grouped["first_preferences_per_offer"] = first.div(offers.where(offers > 0))
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


def _aggregate(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate split routes without collapsing LAEstab-only schools together."""
    metric_columns = tuple(ADMISSIONS_METRICS)
    source_key = _clean_identifier(frame["urn"])
    source_key = source_key.where(source_key.ne(""), "laestab:" + _normalise_laestab(frame["laestab"]))
    working = frame.assign(_school_key=source_key)
    working = working[working["_school_key"].ne("laestab:")].copy()
    grouped = (
        working.groupby(["_school_key", "admission_year"], as_index=False, sort=False)
        .agg(
            urn=("urn", _last_nonblank),
            school_name=("school_name", "last"),
            laestab=("laestab", "last"),
            **{column: (column, lambda values: values.sum(min_count=1)) for column in metric_columns},
        )
        .drop(columns="_school_key")
    )
    return _apply_demand_metrics(grouped)


def resolve_admissions_to_gias(admissions: pd.DataFrame, schools: pd.DataFrame) -> pd.DataFrame:
    """Resolve school-level admissions rows to School Finder URNs using GIAS LAEstab.

    DfE documents LAEstab as the primary link between the school-level applications
    file and GIAS. Source URNs are retained as a fallback for historic/predecessor rows.
    """
    if admissions.empty:
        return admissions.copy()

    resolved = admissions.copy()
    if "urn" not in resolved.columns:
        resolved["urn"] = pd.Series("", index=resolved.index, dtype="string")
    if "laestab" not in resolved.columns:
        resolved["laestab"] = pd.Series("", index=resolved.index, dtype="string")
    if "school_name" not in resolved.columns:
        resolved["school_name"] = pd.Series("", index=resolved.index, dtype="string")
    for metric in ADMISSIONS_METRICS:
        if metric not in resolved.columns:
            resolved[metric] = pd.Series(pd.NA, index=resolved.index, dtype="object")

    resolved["urn"] = _clean_identifier(resolved["urn"])
    resolved["laestab"] = _normalise_laestab(resolved["laestab"])

    if {"urn", "laestab"}.issubset(schools.columns):
        lookup = schools[["urn", "laestab"]].copy()
        lookup["urn"] = _clean_identifier(lookup["urn"])
        lookup["laestab"] = _normalise_laestab(lookup["laestab"])
        lookup = lookup[lookup["urn"].ne("") & lookup["laestab"].ne("")]
        # Do not guess when an identifier is ambiguous in GIAS.
        lookup = lookup[~lookup["laestab"].duplicated(keep=False)]
        mapping = lookup.set_index("laestab")["urn"]
        mapped = resolved["laestab"].map(mapping).fillna("").astype("string")
        resolved["urn"] = mapped.where(mapped.ne(""), resolved["urn"])

    resolved = resolved[resolved["urn"].ne("")].copy()
    if resolved.empty:
        return resolved

    # Multiple historic/dummy identifiers can resolve to one current school. Combine
    # them before recomputing the demand metric and percentile.
    metric_columns = tuple(ADMISSIONS_METRICS)
    grouped = (
        resolved.groupby(["urn", "admission_year"], as_index=False, sort=False)
        .agg(
            school_name=("school_name", "last"),
            laestab=("laestab", "last"),
            **{column: (column, lambda values: values.sum(min_count=1)) for column in metric_columns},
        )
    )
    return _apply_demand_metrics(grouped).reset_index(drop=True)


def read_admissions_history(path: Path) -> pd.DataFrame:
    """Return all usable secondary-school applications/offers rows by entry year."""
    frame = read_public_csv(path, "DfE school applications and offers")
    urn_col = find_column(frame, "school_urn", "urn", "urn_gias", "school urn")
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

    rows = frame[_is_secondary(frame)].copy()
    if rows.empty:
        raise SchoolFinderError("DfE admissions CSV contained no secondary-school rows.")

    urn_values = (
        _clean_identifier(rows[urn_col])
        if urn_col is not None
        else pd.Series("", index=rows.index, dtype="string")
    )
    laestab_values = _laestab_values(rows)
    if urn_col is None and laestab_values.eq("").all():
        raise SchoolFinderError("DfE admissions CSV is missing school identifier (URN or LAEstab).")

    result = pd.DataFrame(
        {
            "urn": urn_values,
            "admission_year": _normalise_year(rows[year_col]),
            "school_name": (
                clean_text_series(rows[name_col])
                if name_col is not None
                else pd.Series("", index=rows.index, dtype="string")
            ),
            "laestab": laestab_values,
            **_metric_values(rows),
        },
        index=rows.index,
    )
    identifiable = result["urn"].ne("") | result["laestab"].ne("")
    result = result[identifiable & result["admission_year"].ne("")].copy()
    if result.empty:
        raise SchoolFinderError("DfE admissions CSV contained no identifiable secondary schools.")
    return _aggregate(result).reset_index(drop=True)


def _year_key(value: object) -> int:
    text = str(value or "").strip()
    digits = "".join(character for character in text if character.isdigit())
    return int(digits[:4] or 0)


def read_admissions_school(path: Path) -> pd.DataFrame:
    """Return the latest published applications/offers row for each source school."""
    history = read_admissions_history(path).copy()
    history["_year_key"] = history["admission_year"].map(_year_key)
    history["_school_key"] = _clean_identifier(history["urn"])
    history["_school_key"] = history["_school_key"].where(
        history["_school_key"].ne(""),
        "laestab:" + _normalise_laestab(history["laestab"]),
    )
    return (
        history.sort_values(["_school_key", "_year_key"], kind="stable")
        .drop_duplicates("_school_key", keep="last")
        .drop(columns=["_year_key", "_school_key"])
        .reset_index(drop=True)
    )
