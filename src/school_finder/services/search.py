"""Reusable school search service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from school_finder.config import (
    METRES_PER_MILE,
    POSTCODES_FILENAME,
    SCHOOLS_FILENAME,
)
from school_finder.data.parquet import require_pyarrow
from school_finder.errors import SchoolFinderError
from school_finder.models.school import SchoolResult, school_result_from_flat_record
from school_finder.models.search import (
    PostcodeLocation,
    SchoolSearchRequest,
    SchoolSearchResult,
)
from school_finder.services.postcode import lookup_postcode

NON_MAINSTREAM_TYPE_TERMS = (
    "special",
    "pupil referral",
    "alternative provision",
    "secure unit",
    "hospital school",
)


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


def find_nearest_schools(
    schools_path: Path,
    postcode: PostcodeLocation,
    *,
    limit: int,
    entry_age: int,
    minimum_exit_age: int,
    include_special: bool,
) -> pd.DataFrame:
    require_pyarrow()
    try:
        schools = pd.read_parquet(schools_path, engine="pyarrow")
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {schools_path}: {exc}") from exc

    eligible = schools[
        schools["low_age"].notna()
        & schools["high_age"].notna()
        & (schools["low_age"] <= entry_age)
        & (schools["high_age"] >= minimum_exit_age)
    ].copy()
    if not include_special:
        eligible = eligible[is_mainstream(eligible["establishment_type"])].copy()

    delta_easting = eligible["easting"] - float(postcode.easting)
    delta_northing = eligible["northing"] - float(postcode.northing)
    eligible["distance_metres"] = (
        delta_easting.pow(2) + delta_northing.pow(2)
    ).pow(0.5)
    eligible["distance_miles"] = (
        eligible["distance_metres"] / METRES_PER_MILE
    ).round(2)

    nearest = eligible.nsmallest(limit, "distance_metres").copy()
    nearest["address"] = nearest.apply(build_address, axis=1)
    nearest["age_range"] = (
        nearest["low_age"].astype("Int64").astype("string")
        + "–"
        + nearest["high_age"].astype("Int64").astype("string")
    )
    return nearest[
        [
            "school_name",
            "distance_miles",
            "sector",
            "establishment_type",
            "phase",
            "age_range",
            "gender",
            "religious_character",
            "admissions_policy",
            "ofsted_rating",
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
    ].reset_index(drop=True)


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
    """Resolve a postcode and return nearby schools using the canonical models."""
    if request.limit < 1:
        raise SchoolFinderError("limit must be at least 1.")

    postcodes_path = data_dir / POSTCODES_FILENAME
    schools_path = data_dir / SCHOOLS_FILENAME
    if not postcodes_path.exists() or not schools_path.exists():
        raise SchoolFinderError(
            f"Datasets are missing from {data_dir}. Run 'school-finder build' first."
        )

    postcode = lookup_postcode(postcodes_path, request.postcode)
    frame = find_nearest_schools(
        schools_path,
        postcode,
        limit=request.limit,
        entry_age=request.entry_age,
        minimum_exit_age=request.minimum_exit_age,
        include_special=request.include_special,
    )
    records = tuple(serialisable_records(frame))
    schools = tuple(school_result_from_flat_record(record) for record in records)
    return SchoolSearchResult(
        request=request,
        postcode=postcode,
        schools=schools,
        flat_records=records,
    )
