import pytest
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


def test_compare_school_state_round_trip_limit_and_cleanup():
    from school_finder.ui.state import (
        COMPARE_URNS_KEY,
        MAX_COMPARE_SCHOOLS,
        add_compare_school,
        clear_compare_schools,
        get_compare_urns,
        remove_compare_school,
    )

    state = {COMPARE_URNS_KEY: [" 100001 ", "100001", "", 123, "100002"]}
    assert get_compare_urns(state) == ("100001", "100002")
    assert get_compare_urns({COMPARE_URNS_KEY: "bad"}) == ()

    state = {}
    with pytest.raises(ValueError, match="urn is required"):
        add_compare_school(state, "   ")
    for index in range(MAX_COMPARE_SCHOOLS):
        add_compare_school(state, f"{index}")
    assert add_compare_school(state, "0") == tuple(str(index) for index in range(MAX_COMPARE_SCHOOLS))
    with pytest.raises(ValueError, match="up to 4"):
        add_compare_school(state, "extra")

    assert remove_compare_school(state, "1") == ("0", "2", "3")
    remove_compare_school(state, "0")
    remove_compare_school(state, "2")
    assert remove_compare_school(state, "3") == ()
    assert COMPARE_URNS_KEY not in state
    clear_compare_schools(state)


def test_new_search_prunes_comparison_selection():
    from school_finder.ui.state import COMPARE_URNS_KEY, get_compare_urns

    keep = SchoolResult(identity=SchoolIdentity("100001", "Keep"))
    state = {COMPARE_URNS_KEY: ["100001", "999999"]}
    result = SchoolSearchResult(
        request=SchoolSearchRequest("SW1A 2AA"),
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, True, None),
        schools=(keep,),
    )
    set_latest_search(state, result)
    assert get_compare_urns(state) == ("100001",)

    empty = SchoolSearchResult(
        request=SchoolSearchRequest("SW1A 2AA"),
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, True, None),
        schools=(),
    )
    set_latest_search(state, empty)
    assert COMPARE_URNS_KEY not in state


def test_personal_school_state_helpers_round_trip_and_filter_invalid_state():
    from school_finder.models.personalisation import PersonalSchoolState, SchoolDisposition
    from school_finder.ui.state import (
        PERSONAL_SCHOOLS_KEY,
        get_personal_school,
        get_personal_schools,
        get_rejected_urns,
        get_shortlisted_urns,
        set_school_disposition,
        set_school_notes,
        set_school_rating,
    )

    assert get_personal_schools({PERSONAL_SCHOOLS_KEY: "bad"}) == {}
    shortlisted = PersonalSchoolState(SchoolDisposition.SHORTLISTED)
    rejected = PersonalSchoolState(SchoolDisposition.NOT_FOR_US)
    state = {
        PERSONAL_SCHOOLS_KEY: {
            " 100001 ": shortlisted,
            "100002": rejected,
            "": shortlisted,
            123: shortlisted,
            "100003": "bad",
        }
    }
    assert get_personal_schools(state) == {
        "100001": shortlisted,
        "100002": rejected,
    }
    assert get_shortlisted_urns(state) == ("100001",)
    assert get_rejected_urns(state) == ("100002",)
    assert get_personal_school(state, " 100001 ") == shortlisted
    assert get_personal_school(state, "999999").is_default is True

    state = {}
    changed = set_school_disposition(state, " 100001 ", "shortlisted")
    assert changed.disposition is SchoolDisposition.SHORTLISTED
    changed = set_school_rating(state, "100001", 5)
    assert changed.rating == 5
    changed = set_school_notes(state, "100001", "  Great visit  ")
    assert changed.notes == "Great visit"
    assert get_personal_school(state, "100001") == changed

    changed = set_school_disposition(state, "100001", SchoolDisposition.NOT_FOR_US)
    assert changed.disposition is SchoolDisposition.NOT_FOR_US
    assert changed.rating == 5
    assert changed.notes == "Great visit"

    with pytest.raises(ValueError, match="is not a valid SchoolDisposition"):
        set_school_disposition(state, "100001", "maybe")
    with pytest.raises(ValueError, match="integer from 1 to 5"):
        set_school_rating(state, "100001", 0)
    with pytest.raises(ValueError, match="urn is required"):
        get_personal_school(state, "   ")


def test_personal_school_fields_can_be_cleared_without_losing_other_fields():
    from school_finder.models.personalisation import SchoolDisposition
    from school_finder.ui.state import (
        PERSONAL_SCHOOLS_KEY,
        get_personal_school,
        set_school_disposition,
        set_school_notes,
        set_school_rating,
    )

    state = {}
    set_school_disposition(state, "100001", SchoolDisposition.SHORTLISTED)
    set_school_rating(state, "100001", 4)
    set_school_notes(state, "100001", "Visit notes")

    assert set_school_rating(state, "100001", None).notes == "Visit notes"
    assert set_school_notes(state, "100001", "   ").disposition is SchoolDisposition.SHORTLISTED
    neutral = set_school_disposition(state, "100001", SchoolDisposition.NEUTRAL)
    assert neutral.is_default is True
    assert PERSONAL_SCHOOLS_KEY not in state
    assert get_personal_school(state, "100001").is_default is True


def test_clear_school_personalisation_removes_only_requested_school():
    from school_finder.models.personalisation import SchoolDisposition
    from school_finder.ui.state import (
        PERSONAL_SCHOOLS_KEY,
        clear_school_personalisation,
        get_personal_schools,
        set_school_disposition,
    )

    state = {}
    set_school_disposition(state, "100001", SchoolDisposition.SHORTLISTED)
    set_school_disposition(state, "100002", SchoolDisposition.NOT_FOR_US)

    clear_school_personalisation(state, "100001")
    assert tuple(get_personal_schools(state)) == ("100002",)
    clear_school_personalisation(state, "100001")
    clear_school_personalisation(state, "100002")
    assert PERSONAL_SCHOOLS_KEY not in state

    with pytest.raises(ValueError, match="urn is required"):
        clear_school_personalisation(state, "")


def test_personal_school_state_survives_new_and_cleared_searches():
    from school_finder.models.personalisation import PersonalSchoolState, SchoolDisposition
    from school_finder.ui.state import (
        PERSONAL_SCHOOLS_KEY,
        clear_latest_search,
        get_personal_school,
        set_school_disposition,
        set_school_notes,
    )

    state = {}
    set_school_disposition(state, "999999", SchoolDisposition.SHORTLISTED)
    set_school_notes(state, "999999", "Keep this even when it is outside the next search")
    expected = get_personal_school(state, "999999")

    keep = SchoolResult(identity=SchoolIdentity("100001", "Current result"))
    result = SchoolSearchResult(
        request=SchoolSearchRequest("SW1A 2AA"),
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, True, None),
        schools=(keep,),
    )
    set_latest_search(state, result)
    assert get_personal_school(state, "999999") == expected

    clear_latest_search(state)
    assert state == {PERSONAL_SCHOOLS_KEY: {"999999": expected}}
    assert isinstance(expected, PersonalSchoolState)
