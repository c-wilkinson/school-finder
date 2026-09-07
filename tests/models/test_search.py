from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.models.school import SchoolIdentity, SchoolResult


def test_search_contract_defaults_and_result_storage():
    request = SchoolSearchRequest("RG22 6SX")
    assert request.limit == 20
    assert request.entry_age == 11
    assert request.minimum_exit_age == 16
    assert request.include_special is False
    postcode = PostcodeLocation("RG22 6SX", 1, 2, True)
    school = SchoolResult(SchoolIdentity("1", "Example"))
    result = SchoolSearchResult(request, postcode, (school,), ({"urn":"1"},))
    assert result.schools == (school,)
    assert result.flat_records[0]["urn"] == "1"
