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
        admissions=AdmissionsInformation(policy=policy, selective=selective),
    )


class _Response:
    def __init__(self, text: str, error: Exception | None = None):
        self.text = text
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


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


def test_get_admission_arrangements_fetches_hampshire_official_page():
    html = """
    <div>255</div><div>Year 7 places for September 2027</div>
    <a href="https://documents.hants.gov.uk/admissions-2027.pdf">Admission policy 2027-2028</a>
    """
    session = _Session(_Response(html))
    result = admission_arrangements.get_admission_arrangements(_school(), session=session)

    assert result.entry_points[0].published_admission_number == 255
    assert result.arrangements_year == "2027/28"
    assert session.calls == [(
        "https://www.hants.gov.uk/educationandlearning/findaschool/schooldetails?dfesno=4182",
        {"timeout": (10, 30)},
    )]


def test_get_admission_arrangements_wraps_request_failures():
    session = _Session(_Response("", requests.HTTPError("boom")))
    with pytest.raises(SchoolFinderError, match="Could not retrieve Hampshire admission arrangements"):
        admission_arrangements.get_admission_arrangements(_school(), session=session)


def test_get_admission_arrangements_creates_default_session(monkeypatch):
    fake = _Session(_Response("<div>224 Year 7 places for September 2027</div>"))
    monkeypatch.setattr(admission_arrangements.requests, "Session", lambda: fake)
    result = admission_arrangements.get_admission_arrangements(_school(), session=None)
    assert result.entry_points[0].published_admission_number == 224
