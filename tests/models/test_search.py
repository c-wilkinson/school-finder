import pytest

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
from school_finder.models.preferences import SchoolPreferences
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.models.school import SchoolBenchmarks, SchoolIdentity, SchoolResult


def test_search_contract_defaults_and_result_storage():
    request = SchoolSearchRequest("SW1A 2AA")
    assert request.limit == 20
    assert request.entry_age == 11
    assert request.minimum_exit_age == 16
    assert request.include_special is False
    assert request.radius_miles is None
    assert request.phases == ()
    assert request.sectors == ()
    assert request.genders == ()
    assert request.faith is FaithFilter.ANY
    assert request.selection is SelectionFilter.ANY
    assert request.minimum_ofsted_rating is None
    assert request.minimum_pastoral_score is None
    assert request.sort == SchoolSort()
    assert request.preferences is None

    postcode = PostcodeLocation("SW1A 2AA", 1, 2, True)
    school = SchoolResult(SchoolIdentity("1", "Example"))
    result = SchoolSearchResult(request, postcode, (school,), ({"urn": "1"},))
    assert result.schools == (school,)
    assert result.flat_records[0]["urn"] == "1"
    assert result.benchmarks == ()


def test_search_result_can_store_benchmark_context():
    request = SchoolSearchRequest("SW1A 2AA")
    postcode = PostcodeLocation("SW1A 2AA", 1, 2, True)
    benchmark = SchoolBenchmarks(label="England", level="National", code="E92000001")
    result = SchoolSearchResult(request, postcode, (), (), (benchmark,))
    assert result.benchmarks == (benchmark,)


def test_search_contract_accepts_full_filter_set():
    request = SchoolSearchRequest(
        postcode="SW1A 2AA",
        radius_miles=5,
        phases=(SchoolPhase.SECONDARY,),
        sectors=(SchoolSector.STATE_FUNDED,),
        genders=(SchoolGender.MIXED,),
        faith=FaithFilter.NON_FAITH,
        selection=SelectionFilter.NON_SELECTIVE,
        minimum_ofsted_rating=OfstedRating.GOOD,
        minimum_attainment8=45,
        minimum_progress8=-0.2,
        minimum_grade5_english_maths_pct=50,
        minimum_ebacc_aps=4.1,
        minimum_pastoral_score=70,
        sort=SchoolSort(SchoolSortField.ATTAINMENT8, SortDirection.DESC),
        preferences=SchoolPreferences(distance=2, ofsted=1),
    )
    assert request.radius_miles == 5
    assert request.minimum_progress8 == -0.2
    assert request.sort.direction is SortDirection.DESC
    assert request.preferences.distance == 2


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"postcode": "   "}, "postcode is required"),
        ({"postcode": "X", "limit": 0}, "limit must be at least 1"),
        ({"postcode": "X", "entry_age": -1}, "entry_age cannot be negative"),
        ({"postcode": "X", "entry_age": 12, "minimum_exit_age": 11}, "minimum_exit_age must be at least entry_age"),
        ({"postcode": "X", "radius_miles": 0}, "radius_miles must be greater than 0"),
        ({"postcode": "X", "radius_miles": -1}, "radius_miles must be greater than 0"),
        ({"postcode": "X", "minimum_attainment8": -0.1}, "minimum_attainment8 cannot be negative"),
        ({"postcode": "X", "minimum_grade5_english_maths_pct": -1}, "minimum_grade5_english_maths_pct must be between 0 and 100"),
        ({"postcode": "X", "minimum_grade5_english_maths_pct": 101}, "minimum_grade5_english_maths_pct must be between 0 and 100"),
        ({"postcode": "X", "minimum_ebacc_aps": -0.1}, "minimum_ebacc_aps must be between 0 and 10"),
        ({"postcode": "X", "minimum_ebacc_aps": 10.1}, "minimum_ebacc_aps must be between 0 and 10"),
        ({"postcode": "X", "minimum_pastoral_score": -0.1}, "minimum_pastoral_score must be between 0 and 100"),
        ({"postcode": "X", "minimum_pastoral_score": 100.1}, "minimum_pastoral_score must be between 0 and 100"),
    ],
)
def test_search_request_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SchoolSearchRequest(**kwargs)


def test_search_request_accepts_threshold_boundaries():
    SchoolSearchRequest(
        "X",
        radius_miles=0.01,
        minimum_attainment8=0,
        minimum_grade5_english_maths_pct=0,
        minimum_ebacc_aps=0,
        minimum_pastoral_score=0,
    )
    SchoolSearchRequest(
        "X",
        minimum_grade5_english_maths_pct=100,
        minimum_ebacc_aps=10,
        minimum_pastoral_score=100,
    )
