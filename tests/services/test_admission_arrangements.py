from dataclasses import replace

import pytest
import requests

from school_finder.errors import SchoolFinderError
from school_finder.models.admissions import AdmissionArrangementSummary
from school_finder.models.school import AdmissionsInformation, SchoolIdentity, SchoolLocation, SchoolResult
from school_finder.services import admission_arrangements


def _school(
    *,
    establishment_type="Academy converter",
    local_authority_name="Hampshire",
    local_authority_code="E10000014",
    establishment_number="4182",
    policy="Non-selective",
    selective=None,
    data_year=None,
):
    return SchoolResult(
        identity=SchoolIdentity(
            urn="137403",
            name="Example School",
            establishment_type=establishment_type,
            establishment_number=establishment_number,
        ),
        location=SchoolLocation(
            local_authority_name=local_authority_name,
            local_authority_code=local_authority_code,
        ),
        admissions=AdmissionsInformation(policy=policy, selective=selective, data_year=data_year),
    )


class _Response:
    def __init__(
        self,
        text: str,
        error: Exception | None = None,
        *,
        content: bytes | None = None,
        content_type: str = "text/html",
    ):
        self.text = text
        self.error = error
        self.content = content if content is not None else text.encode()
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        if self.error:
            raise self.error


class _Session:
    def __init__(self, response):
        self.responses = list(response) if isinstance(response, (list, tuple)) else [response]
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def test_admission_authority_categories_and_selectivity():
    community = _school(establishment_type="Community school", local_authority_name="Hampshire")
    assert admission_arrangements.admission_authority_for_school(community) == "Hampshire"
    assert admission_arrangements.base_admission_arrangements(community).selective is False

    without_named_la = _school(establishment_type="Voluntary controlled school", local_authority_name=None)
    assert admission_arrangements.admission_authority_for_school(without_named_la) == "Local authority"

    assert admission_arrangements.admission_authority_for_school(
        _school(establishment_type="Free school")
    ) == "Academy trust"
    assert admission_arrangements.admission_authority_for_school(
        _school(establishment_type="Voluntary aided school")
    ) == "Governing body"
    assert admission_arrangements.admission_authority_for_school(
        _school(establishment_type="Other")
    ) is None

    selective = admission_arrangements.base_admission_arrangements(
        _school(policy="Selective", selective=None)
    )
    assert selective.selective is True
    explicit = admission_arrangements.base_admission_arrangements(
        _school(policy="Unknown", selective=True)
    )
    assert explicit.selective is True
    unknown = admission_arrangements.base_admission_arrangements(
        _school(policy=None, selective=None)
    )
    assert unknown.selective is None


def test_page_parser_and_hampshire_page_parsing():
    html = """
    <html><body>
      <div> 255 </div><div>Year 7 places for September 2027</div>
      <div>255 Year 7 places for September 2027</div>
      <div>60 Year R places for September 2027</div>
      <a href="/old.pdf">Admission policy 2026-2027</a>
      <a href="/new.pdf"><span>Admission policy 2027-2028</span></a>
      <a href="/sixth.pdf">Sixth-form admission policy 2027-2028</a>
      <a href="/other">Other link</a>
      <a href="/empty"></a>
      <a>No href</a>
    </body></html>
    """
    base = AdmissionArrangementSummary(
        admission_authority="Academy trust",
        selective=False,
        policy="Non-selective",
    )
    parsed = admission_arrangements._parse_hampshire_school_page(
        html,
        "https://www.hants.gov.uk/school",
        base,
    )
    assert [(item.year_group, item.entry_year, item.published_admission_number) for item in parsed.entry_points] == [
        ("7", 2027, 255),
        ("R", 2027, 60),
    ]
    assert parsed.arrangements_year == "2027/28"
    assert parsed.source_url == "https://www.hants.gov.uk/new.pdf"
    assert parsed.directory_url == "https://www.hants.gov.uk/school"
    assert parsed.source_name == "Hampshire County Council"


def test_policy_link_and_entry_point_helpers_cover_empty_cases():
    assert admission_arrangements._parse_entry_points("nothing here") == ()
    assert admission_arrangements._main_admission_policy_link(
        [("Other", "/other")], "https://example.com/base"
    ) == (None, None)

    parser = admission_arrangements._SchoolPageParser()
    parser.feed("<div> </div><a href='/x'> </a><p>Text</p>")
    assert parser.text == ["Text"]
    assert parser.links == []


def test_get_admission_arrangements_returns_national_context_for_unsupported_or_unidentified():
    unsupported = _school(local_authority_name="Surrey")
    result = admission_arrangements.get_admission_arrangements(unsupported, session=_Session(_Response("")))
    assert result.admission_authority == "Academy trust"
    assert result.entry_points == ()

    no_number = _school(establishment_number=None)
    result = admission_arrangements.get_admission_arrangements(no_number, session=_Session(_Response("")))
    assert result.policy == "Non-selective"


def test_hampshire_provider_can_be_selected_from_la_code_when_name_is_missing():
    html = "<div>255 Year 7 places for September 2027</div>"
    session = _Session(_Response(html))
    result = admission_arrangements.get_admission_arrangements(
        _school(local_authority_name=None, local_authority_code="E10000014"),
        session=session,
    )
    assert result.entry_points[0].published_admission_number == 255


def test_get_admission_arrangements_fetches_hampshire_official_page(monkeypatch):
    html = """
    <div>255</div><div>Year 7 places for September 2027</div>
    <a href="https://documents.hants.gov.uk/admissions-2027.pdf">Admission policy 2027-2028</a>
    """
    policy = """
    Oversubscription criteria
    1. Looked after children or children who were previously looked after (see definition i).
    2. Children living in the catchment area who have a sibling at the school.
    3. Other children.
    Definitions
    """
    monkeypatch.setattr(admission_arrangements, "_extract_pdf_text", lambda content: policy)
    session = _Session([
        _Response(html),
        _Response("", content=b"pdf", content_type="application/pdf"),
    ])
    result = admission_arrangements.get_admission_arrangements(_school(), session=session)

    assert result.entry_points[0].published_admission_number == 255
    assert result.arrangements_year == "2027/28"
    assert [criterion.priority for criterion in result.criteria] == [1, 2, 3]
    assert session.calls == [
        (
            "https://www.hants.gov.uk/educationandlearning/findaschool/schooldetails?dfesno=4182",
            {"timeout": (10, 30), "headers": admission_arrangements._REQUEST_HEADERS},
        ),
        (
            "https://documents.hants.gov.uk/admissions-2027.pdf",
            {"timeout": (10, 30), "headers": admission_arrangements._REQUEST_HEADERS},
        ),
    ]


def test_get_admission_arrangements_wraps_request_failures():
    session = _Session(_Response("", requests.HTTPError("boom")))
    with pytest.raises(SchoolFinderError, match="Could not retrieve Hampshire admission arrangements"):
        admission_arrangements.get_admission_arrangements(_school(), session=session)


def test_get_admission_arrangements_creates_default_session(monkeypatch):
    fake = _Session(_Response("<div>224 Year 7 places for September 2027</div>"))
    monkeypatch.setattr(admission_arrangements.requests, "Session", lambda: fake)
    result = admission_arrangements.get_admission_arrangements(_school(), session=None)
    assert result.entry_points[0].published_admission_number == 224


def test_criterion_parser_preserves_wording_and_structures_types():
    text = """
    Intro.
    Oversubscription criteria
    1. Looked after children or children who were previously looked after.
    2. Children or families with an exceptional medical and/or social need.
    3. Children of staff who have been employed for two or more years.
    4. Children living in the catchment area who have a sibling at the school.
    5. Children attending a linked junior school or feeder school.
    6. Children eligible for pupil premium or service premium.
    7. Catholic children living in the parish.
    8. Children selected by aptitude or an 11+ test.
    9. Children living nearest to the school by straight-line distance.
    10.Other children.
    Definitions
    This should not be included.
    """
    criteria = admission_arrangements._parse_oversubscription_criteria(text)
    from school_finder.models.admissions import AdmissionCriterionKind

    assert [item.priority for item in criteria] == list(range(1, 11))
    assert criteria[0].kinds == (AdmissionCriterionKind.LOOKED_AFTER,)
    assert criteria[1].kinds == (AdmissionCriterionKind.SOCIAL_MEDICAL,)
    assert criteria[2].kinds == (AdmissionCriterionKind.STAFF_CHILD,)
    assert criteria[3].kinds == (
        AdmissionCriterionKind.SIBLING,
        AdmissionCriterionKind.CATCHMENT,
    )
    assert criteria[4].kinds == (AdmissionCriterionKind.FEEDER,)
    assert criteria[5].kinds == (
        AdmissionCriterionKind.PUPIL_PREMIUM,
        AdmissionCriterionKind.SERVICE_PREMIUM,
    )
    assert criteria[6].kinds == (AdmissionCriterionKind.FAITH,)
    assert criteria[7].kinds == (AdmissionCriterionKind.SELECTIVE,)
    assert criteria[8].kinds == (AdmissionCriterionKind.DISTANCE,)
    assert criteria[9].kinds == (AdmissionCriterionKind.OTHER,)
    assert criteria[3].description == "Children living in the catchment area who have a sibling at the school."


def test_criterion_parser_handles_missing_section_and_empty_numbered_item():
    assert admission_arrangements._parse_oversubscription_criteria("Nothing relevant") == ()
    parsed = admission_arrangements._parse_oversubscription_criteria(
        "Oversubscription criteria 1. 2. Other children. Tie-breaker"
    )
    assert [(item.priority, item.description) for item in parsed] == [(2, "Other children.")]
    without_end_heading = admission_arrangements._parse_oversubscription_criteria(
        "Oversubscription criteria 1. Other children."
    )
    assert without_end_heading[0].description == "Other children."


def test_policy_response_text_supports_html_and_pdf(monkeypatch):
    html = _Response("<html><body><p>Oversubscription criteria</p><p>1. Other children.</p></body></html>")
    assert "Oversubscription criteria" in admission_arrangements._policy_response_text(
        html, "https://example.test/policy"
    )

    monkeypatch.setattr(admission_arrangements, "_extract_pdf_text", lambda content: "PDF TEXT")
    pdf = _Response("", content=b"pdf", content_type="application/octet-stream")
    assert admission_arrangements._policy_response_text(
        pdf, "https://example.test/policy.PDF"
    ) == "PDF TEXT"


def test_extract_pdf_text_joins_pages(monkeypatch):
    class _Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class _Reader:
        pages = [_Page("One"), _Page(None), _Page("Three")]

    monkeypatch.setattr(admission_arrangements, "PdfReader", lambda stream: _Reader())
    assert admission_arrangements._extract_pdf_text(b"anything") == "One\n\nThree"


def test_policy_failure_preserves_pan_and_arrangement_link():
    html = """
    <div>255 Year 7 places for September 2027</div>
    <a href="/policy.pdf">Admission policy 2027-2028</a>
    """
    session = _Session([
        _Response(html),
        _Response("", requests.HTTPError("policy offline")),
    ])
    result = admission_arrangements.get_admission_arrangements(_school(), session=session)
    assert result.entry_points[0].published_admission_number == 255
    assert result.source_url == "https://www.hants.gov.uk/policy.pdf"
    assert result.criteria == ()


def test_policy_parse_failure_preserves_arrangement(monkeypatch):
    html = """
    <div>255 Year 7 places for September 2027</div>
    <a href="/policy.pdf">Admission policy 2027-2028</a>
    """
    monkeypatch.setattr(
        admission_arrangements,
        "_extract_pdf_text",
        lambda content: (_ for _ in ()).throw(admission_arrangements.PdfReadError("bad pdf")),
    )
    session = _Session([
        _Response(html),
        _Response("", content=b"bad", content_type="application/pdf"),
    ])
    result = admission_arrangements.get_admission_arrangements(_school(), session=session)
    assert result.entry_points[0].published_admission_number == 255
    assert result.criteria == ()


def test_entry_year_and_policy_pan_helpers():
    assert admission_arrangements._entry_year_from_admissions_data(
        _school(data_year="2026/27")
    ) == 2027
    assert admission_arrangements._entry_year_from_admissions_data(
        _school(data_year="2026/2027")
    ) == 2027
    assert admission_arrangements._entry_year_from_admissions_data(
        _school(data_year="unknown")
    ) is None

    text = (
        "Published Admission Number (PAN). "
        "The PAN for Example School for 2027-28 is 255 in Year 7. "
        "The PAN for a sixth form is 40 in Year 12. "
        "The PAN for a duplicate route is 999 in Year 7."
    )
    points = admission_arrangements._parse_policy_pan(text, 2027)
    assert [(point.year_group, point.entry_year, point.published_admission_number) for point in points] == [
        ("7", 2027, 255),
        ("12", 2027, 40),
    ]


def test_hampshire_page_failure_falls_back_to_official_policy(monkeypatch):
    policy = """
    Admissions Policy 2027-2028
    Published Admission Number (PAN)
    The PAN for Example School for 2027- 28 is 255 in Year 7.
    Oversubscription criteria
    1. Looked after children or children who were previously looked after.
    2. Other children.
    Definitions
    """
    monkeypatch.setattr(admission_arrangements, "_extract_pdf_text", lambda content: policy)
    session = _Session(
        [
            _Response("", requests.HTTPError("directory blocked")),
            _Response("", content=b"pdf", content_type="application/pdf"),
        ]
    )

    result = admission_arrangements.get_admission_arrangements(
        _school(data_year="2026/27"), session=session
    )

    expected_policy_url = (
        "https://documents.hants.gov.uk/education/admissions/schoolpolicies/"
        "2027/41822027.pdf"
    )
    assert result.entry_points == (
        admission_arrangements.AdmissionEntryPoint(
            year_group="7", entry_year=2027, published_admission_number=255
        ),
    )
    assert result.arrangements_year == "2027/28"
    assert [criterion.priority for criterion in result.criteria] == [1, 2]
    assert result.source_url == expected_policy_url
    assert result.directory_url.endswith("dfesno=4182")
    assert [call[0] for call in session.calls] == [
        "https://www.hants.gov.uk/educationandlearning/findaschool/schooldetails?dfesno=4182",
        expected_policy_url,
    ]
    assert all(
        call[1]["headers"] == admission_arrangements._REQUEST_HEADERS
        for call in session.calls
    )


def test_hampshire_fallback_failure_still_raises_original_directory_error():
    page_error = requests.HTTPError("directory blocked")
    session = _Session(
        [
            _Response("", page_error),
            _Response(
                "", requests.HTTPError("policy blocked"), content_type="application/pdf"
            ),
        ]
    )
    with pytest.raises(
        SchoolFinderError,
        match="Could not retrieve Hampshire admission arrangements: directory blocked",
    ):
        admission_arrangements.get_admission_arrangements(
            _school(data_year="2026/27"), session=session
        )
