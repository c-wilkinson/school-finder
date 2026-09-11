"""Translate Streamlit form values into the reusable search contract."""

from __future__ import annotations

from collections.abc import Mapping

from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SchoolSort,
    SchoolSortField,
    SelectionFilter,
    SortDirection,
)
from school_finder.models.preferences import PreferenceMetric, PreferencePreset, SchoolPreferences
from school_finder.models.search import SchoolSearchRequest


PRESET_LABELS: dict[str, PreferencePreset | None] = {
    "Balanced": PreferencePreset.BALANCED,
    "Academic": PreferencePreset.ACADEMIC,
    "Closest": PreferencePreset.CLOSEST,
    "Ofsted focused": PreferencePreset.OFSTED_FOCUSED,
    "Pastoral focused": PreferencePreset.PASTORAL_FOCUSED,
    "Custom": PreferencePreset.CUSTOM,
    "No preference scoring": None,
}

SORT_LABELS: dict[str, SchoolSortField] = {
    "Distance": SchoolSortField.DISTANCE,
    "School name": SchoolSortField.NAME,
    "Ofsted": SchoolSortField.OFSTED,
    "Attainment 8": SchoolSortField.ATTAINMENT8,
    "Progress 8": SchoolSortField.PROGRESS8,
    "English & Maths Grade 5+": SchoolSortField.GRADE5_ENGLISH_MATHS,
    "EBacc APS": SchoolSortField.EBACC_APS,
    "Pastoral care": SchoolSortField.PASTORAL_CARE,
}

CUSTOM_DEFAULT_WEIGHTS: dict[PreferenceMetric, float] = {
    PreferenceMetric.DISTANCE: 20,
    PreferenceMetric.OFSTED: 15,
    PreferenceMetric.ATTAINMENT8: 15,
    PreferenceMetric.PROGRESS8: 15,
    PreferenceMetric.GRADE5_ENGLISH_MATHS: 10,
    PreferenceMetric.EBACC_APS: 5,
    PreferenceMetric.PASTORAL_CARE: 20,
}


def build_preferences(
    preset: PreferencePreset | None,
    custom_weights: Mapping[PreferenceMetric, float] | None = None,
) -> SchoolPreferences | None:
    if preset is None:
        return None
    if preset is not PreferencePreset.CUSTOM:
        return SchoolPreferences.from_preset(preset)

    weights = dict(CUSTOM_DEFAULT_WEIGHTS)
    if custom_weights is not None:
        weights.update(custom_weights)
    return SchoolPreferences(
        distance=weights[PreferenceMetric.DISTANCE],
        ofsted=weights[PreferenceMetric.OFSTED],
        attainment8=weights[PreferenceMetric.ATTAINMENT8],
        progress8=weights[PreferenceMetric.PROGRESS8],
        grade5_english_maths=weights[PreferenceMetric.GRADE5_ENGLISH_MATHS],
        ebacc_aps=weights[PreferenceMetric.EBACC_APS],
        pastoral_care=weights[PreferenceMetric.PASTORAL_CARE],
    )


def build_search_request(
    *,
    postcode: str,
    radius_miles: float,
    limit: int,
    phases: tuple[SchoolPhase, ...] = (),
    sectors: tuple[SchoolSector, ...] = (),
    genders: tuple[SchoolGender, ...] = (),
    faith: FaithFilter = FaithFilter.ANY,
    selection: SelectionFilter = SelectionFilter.ANY,
    include_special: bool = False,
    minimum_ofsted_rating: OfstedRating | None = None,
    minimum_attainment8: float | None = None,
    minimum_progress8: float | None = None,
    minimum_grade5_english_maths_pct: float | None = None,
    minimum_ebacc_aps: float | None = None,
    minimum_pastoral_score: float | None = None,
    preset: PreferencePreset | None = PreferencePreset.BALANCED,
    custom_weights: Mapping[PreferenceMetric, float] | None = None,
    sort_field: SchoolSortField = SchoolSortField.DISTANCE,
    descending: bool = False,
) -> SchoolSearchRequest:
    return SchoolSearchRequest(
        postcode=postcode,
        radius_miles=radius_miles,
        limit=limit,
        phases=phases,
        sectors=sectors,
        genders=genders,
        faith=faith,
        selection=selection,
        include_special=include_special,
        minimum_ofsted_rating=minimum_ofsted_rating,
        minimum_attainment8=minimum_attainment8,
        minimum_progress8=minimum_progress8,
        minimum_grade5_english_maths_pct=minimum_grade5_english_maths_pct,
        minimum_ebacc_aps=minimum_ebacc_aps,
        minimum_pastoral_score=minimum_pastoral_score,
        sort=SchoolSort(
            field=sort_field,
            direction=SortDirection.DESC if descending else SortDirection.ASC,
        ),
        preferences=build_preferences(preset, custom_weights),
    )
