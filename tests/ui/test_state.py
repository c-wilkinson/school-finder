from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.models.school import SchoolIdentity, SchoolResult
from school_finder.ui.state import (
    LATEST_SEARCH_KEY,
    SELECTED_SCHOOL_URN_KEY,
    clear_latest_search,
    clear_selected_school,
    get_latest_search,
    get_selected_school_urn,
    select_school,
    set_latest_search,
)


def _result() -> SchoolSearchResult:
    request = SchoolSearchRequest("SW1A 2AA")
    return SchoolSearchResult(
        request=request,
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, True, None),
        schools=(),
    )


def test_latest_search_round_trip():
    state = {}
    result = _result()

    assert get_latest_search(state) is None
    assert set_latest_search(state, result) is result
    assert get_latest_search(state) is result


def test_latest_search_ignores_unexpected_value():
    state = {LATEST_SEARCH_KEY: "not a result"}
    assert get_latest_search(state) is None


def test_clear_latest_search_is_idempotent():
    state = {LATEST_SEARCH_KEY: _result()}
    clear_latest_search(state)
    clear_latest_search(state)
    assert LATEST_SEARCH_KEY not in state


def test_selected_school_round_trip_and_validation():
    state = {}
    assert get_selected_school_urn(state) is None
    assert get_selected_school_urn({SELECTED_SCHOOL_URN_KEY: 123}) is None
    assert get_selected_school_urn({SELECTED_SCHOOL_URN_KEY: "   "}) is None
    assert select_school(state, " 100001 ") == "100001"
    assert get_selected_school_urn(state) == "100001"
    clear_selected_school(state)
    clear_selected_school(state)
    assert get_selected_school_urn(state) is None

    import pytest
    with pytest.raises(ValueError, match="urn is required"):
        select_school(state, "   ")


def test_new_search_preserves_or_clears_selected_school():
    keep = SchoolResult(identity=SchoolIdentity("100001", "Keep"))
    state = {SELECTED_SCHOOL_URN_KEY: "100001"}
    result = SchoolSearchResult(
        request=SchoolSearchRequest("SW1A 2AA"),
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, True, None),
        schools=(keep,),
    )
    set_latest_search(state, result)
    assert get_selected_school_urn(state) == "100001"

    replacement = SchoolSearchResult(
        request=SchoolSearchRequest("SW1A 2AA"),
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, True, None),
        schools=(),
    )
    set_latest_search(state, replacement)
    assert get_selected_school_urn(state) is None


def test_clear_latest_search_also_clears_selected_school():
    state = {LATEST_SEARCH_KEY: _result(), SELECTED_SCHOOL_URN_KEY: "100001"}
    clear_latest_search(state)
    assert state == {}
