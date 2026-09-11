import pytest

from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SchoolSortField,
    SelectionFilter,
    SortDirection,
)
from school_finder.models.preferences import PreferenceMetric, PreferencePreset
from school_finder.ui.controls import (
    CUSTOM_DEFAULT_WEIGHTS,
    PRESET_LABELS,
    SORT_LABELS,
    build_preferences,
    build_search_request,
)


def test_ui_label_maps_cover_presets_and_sort_fields():
    assert PRESET_LABELS["Pastoral focused"] is PreferencePreset.PASTORAL_FOCUSED
    assert PRESET_LABELS["No preference scoring"] is None
    assert SORT_LABELS["Pastoral care"] is SchoolSortField.PASTORAL_CARE


def test_build_preferences_supports_named_custom_and_none():
    assert build_preferences(None) is None
    balanced = build_preferences(PreferencePreset.BALANCED)
    assert balanced is not None
    assert balanced.distance == 20

    default_custom = build_preferences(PreferencePreset.CUSTOM)
    assert default_custom is not None
    assert default_custom.distance == CUSTOM_DEFAULT_WEIGHTS[PreferenceMetric.DISTANCE]

    custom = build_preferences(
        PreferencePreset.CUSTOM,
        {
            PreferenceMetric.DISTANCE: 5,
            PreferenceMetric.PASTORAL_CARE: 95,
        },
    )
    assert custom is not None
    assert custom.distance == 5
    assert custom.pastoral_care == 95
    assert custom.ofsted == CUSTOM_DEFAULT_WEIGHTS[PreferenceMetric.OFSTED]


def test_build_preferences_rejects_all_zero_custom_weights():
    with pytest.raises(ValueError, match="At least one preference weight"):
        build_preferences(
            PreferencePreset.CUSTOM,
            {metric: 0 for metric in PreferenceMetric},
        )


def test_build_search_request_maps_all_ui_controls():
    request = build_search_request(
        postcode="RG22 6SX",
        radius_miles=5,
        limit=12,
        phases=(SchoolPhase.SECONDARY,),
        sectors=(SchoolSector.STATE_FUNDED,),
        genders=(SchoolGender.MIXED,),
        faith=FaithFilter.NON_FAITH,
        selection=SelectionFilter.NON_SELECTIVE,
        include_special=True,
        minimum_ofsted_rating=OfstedRating.GOOD,
        minimum_attainment8=45,
        minimum_progress8=0.1,
        minimum_grade5_english_maths_pct=50,
        minimum_ebacc_aps=4,
        minimum_pastoral_score=70,
        preset=PreferencePreset.PASTORAL_FOCUSED,
        sort_field=SchoolSortField.PASTORAL_CARE,
        descending=True,
    )
    assert request.postcode == "RG22 6SX"
    assert request.radius_miles == 5
    assert request.limit == 12
    assert request.phases == (SchoolPhase.SECONDARY,)
    assert request.sectors == (SchoolSector.STATE_FUNDED,)
    assert request.genders == (SchoolGender.MIXED,)
    assert request.faith is FaithFilter.NON_FAITH
    assert request.selection is SelectionFilter.NON_SELECTIVE
    assert request.include_special is True
    assert request.minimum_ofsted_rating is OfstedRating.GOOD
    assert request.minimum_attainment8 == 45
    assert request.minimum_progress8 == 0.1
    assert request.minimum_grade5_english_maths_pct == 50
    assert request.minimum_ebacc_aps == 4
    assert request.minimum_pastoral_score == 70
    assert request.preferences is not None
    assert request.preferences.pastoral_care == 50
    assert request.sort.field is SchoolSortField.PASTORAL_CARE
    assert request.sort.direction is SortDirection.DESC


def test_build_search_request_supports_sort_only():
    request = build_search_request(
        postcode="RG22 6SX",
        radius_miles=3,
        limit=5,
        preset=None,
        sort_field=SchoolSortField.ATTAINMENT8,
    )
    assert request.preferences is None
    assert request.sort.field is SchoolSortField.ATTAINMENT8
    assert request.sort.direction is SortDirection.ASC
