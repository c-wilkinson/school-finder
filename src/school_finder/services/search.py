"""Reusable school search service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from school_finder.config import METRES_PER_MILE, POSTCODES_FILENAME, SCHOOLS_FILENAME
from school_finder.data.parquet import require_pyarrow
from school_finder.errors import SchoolFinderError
from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolSortField,
    SelectionFilter,
    SortDirection,
)
from school_finder.models.ofsted import derive_equivalent_ofsted_rating
from school_finder.models.school import SchoolResult, school_result_from_flat_record
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.services.postcode import lookup_postcode

NON_MAINSTREAM_TYPE_TERMS = (
    "special",
    "pupil referral",
    "alternative provision",
    "secure unit",
    "hospital school",
)

NON_FAITH_CHARACTER_VALUES = {
    "does not apply",
    "none",
    "no religious character",
    "not applicable",
}

OFSTED_RATING_SCORES = {
    "inadequate": 1,
    "requires improvement": 2,
    "good": 3,
    "outstanding": 4,
}

OUTPUT_COLUMNS = [
    "school_name",
    "distance_miles",
    "sector",
    "establishment_type",
    "phase",
    "age_range",
    "gender",
    "religious_character",
    "religious_ethos",
    "faith_status",
    "admissions_policy",
    "ofsted_rating",
    "ofsted_equivalent_rating",
    "ofsted_equivalent_basis",
    "ofsted_equivalent_explanation",
    "ofsted_source_urn",
    "ofsted_source_school_name",
    "ofsted_source_kind",
    "ofsted_source_link_depth",
    "ofsted_inspection_date",
    "ofsted_publication_date",
    "ofsted_safeguarding",
    "ofsted_inclusion",
    "ofsted_curriculum_teaching",
    "ofsted_achievement",
    "ofsted_attendance_behaviour",
    "ofsted_personal_development",
    "ofsted_leadership",
    "performance_year",
    "attainment8",
    "english_maths_grade5_pct",
    "english_maths_grade4_pct",
    "ebacc_entry_pct",
    "ebacc_aps",
    "progress8",
    "progress8_year",
    "address",
    "town",
    "postcode",
    "easting",
    "northing",
    "urn",
    "website",
    "telephone",
    "source_date",
]


def is_mainstream(establishment_type: pd.Series) -> pd.Series:
    lowered = establishment_type.fillna("").str.casefold()
    mask = pd.Series(True, index=establishment_type.index)
    for term in NON_MAINSTREAM_TYPE_TERMS:
        mask &= ~lowered.str.contains(term, regex=False)
    return mask


def build_address(row: pd.Series) -> str:
    parts = [
        row.get("street", ""),
        row.get("locality", ""),
        row.get("address_3", ""),
        row.get("town", ""),
        row.get("county", ""),
        row.get("postcode", ""),
    ]
    return ", ".join(
        str(part).strip()
        for part in parts
        if pd.notna(part) and str(part).strip()
    )


def _normalised_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype("string").str.strip().str.casefold()


def _filter_enum_values(
    frame: pd.DataFrame,
    column: str,
    values: Iterable[str],
) -> pd.DataFrame:
    wanted = {str(value).casefold() for value in values}
    if not wanted:
        return frame
    return frame[_normalised_text(frame[column]).isin(wanted)].copy()


def _filter_faith(frame: pd.DataFrame, faith: FaithFilter) -> pd.DataFrame:
    if faith is FaithFilter.ANY:
        return frame

    if "faith_status" in frame.columns:
        status = _normalised_text(frame["faith_status"])
        expected = "non-faith" if faith is FaithFilter.NON_FAITH else "faith"
        return frame[status.eq(expected)].copy()

    raw = frame["religious_character"]
    lowered = _normalised_text(raw)
    known = raw.notna() & lowered.ne("")
    is_non_faith = known & lowered.isin(NON_FAITH_CHARACTER_VALUES)
    if faith is FaithFilter.NON_FAITH:
        return frame[is_non_faith].copy()
    return frame[known & ~is_non_faith].copy()


def _filter_selection(
    frame: pd.DataFrame,
    selection: SelectionFilter,
) -> pd.DataFrame:
    if selection is SelectionFilter.ANY:
        return frame
    lowered = _normalised_text(frame["admissions_policy"])
    expected = "selective" if selection is SelectionFilter.SELECTIVE else "non-selective"
    return frame[lowered.eq(expected)].copy()


def _filter_numeric_minimum(
    frame: pd.DataFrame,
    column: str,
    minimum: float | None,
) -> pd.DataFrame:
    if minimum is None:
        return frame
    values = pd.to_numeric(frame[column], errors="coerce")
    return frame[values.notna() & values.ge(minimum)].copy()


def _ofsted_scores(series: pd.Series) -> pd.Series:
    return _normalised_text(series).map(OFSTED_RATING_SCORES).astype("Float64")




def _with_ofsted_provenance(row: pd.Series, explanation: str) -> str:
    if str(row.get("ofsted_source_kind", "")).casefold() != "predecessor":
        return explanation
    source_urn = row.get("ofsted_source_urn")
    source_name = row.get("ofsted_source_school_name")
    source_urn_text = str(source_urn).strip() if pd.notna(source_urn) else "unknown"
    source_name_text = (
        str(source_name).strip()
        if pd.notna(source_name) and str(source_name).strip()
        else f"predecessor URN {source_urn_text}"
    )
    return (
        f"Historical Ofsted inspection from predecessor {source_name_text} "
        f"(URN {source_urn_text}). {explanation}"
    )

def _add_equivalent_ofsted(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()

    equivalents = enriched.apply(
        lambda row: derive_equivalent_ofsted_rating(
            official_rating=row.get("ofsted_rating"),
            safeguarding=row.get("ofsted_safeguarding"),
            inclusion=row.get("ofsted_inclusion"),
            curriculum_teaching=row.get("ofsted_curriculum_teaching"),
            achievement=row.get("ofsted_achievement"),
            attendance_behaviour=row.get("ofsted_attendance_behaviour"),
            personal_development=row.get("ofsted_personal_development"),
            leadership=row.get("ofsted_leadership"),
        ),
        axis=1,
    )
    enriched["ofsted_equivalent_rating"] = equivalents.map(
        lambda result: result.rating.value if result.rating is not None else pd.NA
    )
    enriched["ofsted_equivalent_basis"] = equivalents.map(lambda result: result.basis.value)
    enriched["ofsted_equivalent_explanation"] = [
        _with_ofsted_provenance(row, result.explanation)
        for (_, row), result in zip(enriched.iterrows(), equivalents, strict=True)
    ]
    return enriched


def _filter_minimum_ofsted(
    frame: pd.DataFrame,
    minimum: OfstedRating | None,
) -> pd.DataFrame:
    if minimum is None:
        return frame
    minimum_score = OFSTED_RATING_SCORES[minimum.value.casefold()]
    scores = _ofsted_scores(frame["ofsted_equivalent_rating"])
    return frame[scores.notna() & scores.ge(minimum_score)].copy()


def _apply_filters(frame: pd.DataFrame, request: SchoolSearchRequest) -> pd.DataFrame:
    filtered = frame
    if request.radius_miles is not None:
        filtered = filtered[filtered["distance_miles"] <= request.radius_miles].copy()

    filtered = _filter_enum_values(filtered, "phase", request.phases)
    filtered = _filter_enum_values(filtered, "sector", request.sectors)
    filtered = _filter_enum_values(filtered, "gender", request.genders)
    filtered = _filter_faith(filtered, request.faith)
    filtered = _filter_selection(filtered, request.selection)
    filtered = _filter_minimum_ofsted(filtered, request.minimum_ofsted_rating)
    filtered = _filter_numeric_minimum(filtered, "attainment8", request.minimum_attainment8)
    filtered = _filter_numeric_minimum(filtered, "progress8", request.minimum_progress8)
    filtered = _filter_numeric_minimum(
        filtered,
        "english_maths_grade5_pct",
        request.minimum_grade5_english_maths_pct,
    )
    return _filter_numeric_minimum(filtered, "ebacc_aps", request.minimum_ebacc_aps)


def _sort_schools(frame: pd.DataFrame, request: SchoolSearchRequest) -> pd.DataFrame:
    sort = request.sort
    ascending = sort.direction is SortDirection.ASC

    if sort.field is SchoolSortField.OFSTED:
        sortable = frame.assign(_primary_sort=_ofsted_scores(frame["ofsted_equivalent_rating"]))
        primary = "_primary_sort"
    else:
        primary = {
            SchoolSortField.DISTANCE: "distance_miles",
            SchoolSortField.NAME: "school_name",
            SchoolSortField.ATTAINMENT8: "attainment8",
            SchoolSortField.PROGRESS8: "progress8",
            SchoolSortField.GRADE5_ENGLISH_MATHS: "english_maths_grade5_pct",
            SchoolSortField.EBACC_APS: "ebacc_aps",
        }[sort.field]
        sortable = frame

    if sort.field is SchoolSortField.DISTANCE:
        by = [primary, "school_name"]
        directions = [ascending, True]
    elif sort.field is SchoolSortField.NAME:
        by = [primary, "distance_miles"]
        directions = [ascending, True]
    else:
        by = [primary, "distance_miles", "school_name"]
        directions = [ascending, True, True]

    result = sortable.sort_values(
        by=by,
        ascending=directions,
        na_position="last",
        kind="stable",
    )
    if "_primary_sort" in result.columns:
        result = result.drop(columns="_primary_sort")
    return result


def find_schools(
    schools_path: Path,
    postcode: PostcodeLocation,
    request: SchoolSearchRequest,
) -> pd.DataFrame:
    require_pyarrow()
    try:
        schools = pd.read_parquet(schools_path, engine="pyarrow")
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {schools_path}: {exc}") from exc

    eligible = schools[
        schools["low_age"].notna()
        & schools["high_age"].notna()
        & (schools["low_age"] <= request.entry_age)
        & (schools["high_age"] >= request.minimum_exit_age)
    ].copy()
    if not request.include_special:
        eligible = eligible[is_mainstream(eligible["establishment_type"])].copy()

    delta_easting = eligible["easting"] - float(postcode.easting)
    delta_northing = eligible["northing"] - float(postcode.northing)
    eligible["distance_metres"] = (
        delta_easting.pow(2) + delta_northing.pow(2)
    ).pow(0.5)
    eligible["distance_miles"] = eligible["distance_metres"] / METRES_PER_MILE

    eligible = _add_equivalent_ofsted(eligible)
    eligible = _apply_filters(eligible, request)
    eligible = _sort_schools(eligible, request).head(request.limit).copy()
    eligible["distance_miles"] = eligible["distance_miles"].round(2)
    eligible["address"] = eligible.apply(build_address, axis=1)
    eligible["age_range"] = (
        eligible["low_age"].astype("Int64").astype("string")
        + "–"
        + eligible["high_age"].astype("Int64").astype("string")
    )
    return eligible[OUTPUT_COLUMNS].reset_index(drop=True)


def serialisable_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = frame.copy()
    for column in records.columns:
        if pd.api.types.is_datetime64_any_dtype(records[column]):
            records[column] = records[column].dt.strftime("%Y-%m-%d")
    records = records.astype(object).where(pd.notna(records), None)
    return records.to_dict(orient="records")


def school_results_from_frame(frame: pd.DataFrame) -> list[SchoolResult]:
    return [
        school_result_from_flat_record(record)
        for record in serialisable_records(frame)
    ]


def search_schools(
    data_dir: Path,
    request: SchoolSearchRequest,
) -> SchoolSearchResult:
    postcodes_path = data_dir / POSTCODES_FILENAME
    schools_path = data_dir / SCHOOLS_FILENAME
    if not postcodes_path.exists() or not schools_path.exists():
        raise SchoolFinderError(
            f"Datasets are missing from {data_dir}. Run 'school-finder build' first."
        )

    postcode = lookup_postcode(postcodes_path, request.postcode)
    frame = find_schools(schools_path, postcode, request)
    records = tuple(serialisable_records(frame))
    schools = tuple(school_result_from_flat_record(record) for record in records)
    return SchoolSearchResult(
        request=request,
        postcode=postcode,
        schools=schools,
        flat_records=records,
    )
