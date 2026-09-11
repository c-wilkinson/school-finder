from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.ui.state import (
    LATEST_SEARCH_KEY,
    clear_latest_search,
    get_latest_search,
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
