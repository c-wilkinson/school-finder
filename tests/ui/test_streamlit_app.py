from __future__ import annotations

from dataclasses import replace
import runpy
import sys

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
from school_finder.models.school import (
    AcademicPerformance,
    AttendanceStatistics,
    BehaviourStatistics,
    InspectionSummary,
    PastoralCareStatistics,
    SchoolBenchmarks,
    SchoolIdentity,
    SchoolLocation,
    SchoolResult,
    TravelInformation,
    WorkforceStatistics,
)
from school_finder.models.scoring import SchoolScore
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.ui import streamlit_app


class FakeColumn:
    def __init__(self, parent):
        self.parent = parent

    def markdown(self, text):
        self.parent.calls.append(("markdown", text))

    def metric(self, label, value, **kwargs):
        self.parent.calls.append(("metric", label, value, kwargs))


class FakeStreamlit:
    def __init__(self, answers=None, submitted=False):
        self.answers = answers or {}
        self.submitted = submitted
        self.calls = []
        self.sidebar = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _answer(self, label, default):
        return self.answers.get(label, default)

    def cache_data(self, **kwargs):
        self.calls.append(("cache_data", kwargs))
        return lambda func: func

    def set_page_config(self, **kwargs):
        self.calls.append(("set_page_config", kwargs))

    def title(self, text):
        self.calls.append(("title", text))

    def header(self, text):
        self.calls.append(("header", text))

    def markdown(self, text):
        self.calls.append(("markdown", text))

    def caption(self, text):
        self.calls.append(("caption", text))

    def info(self, text):
        self.calls.append(("info", text))

    def warning(self, text):
        self.calls.append(("warning", text))

    def error(self, text):
        self.calls.append(("error", text))

    def subheader(self, text):
        self.calls.append(("subheader", text))

    def dataframe(self, frame, **kwargs):
        self.calls.append(("dataframe", tuple(frame.columns), kwargs))

    def form(self, name):
        self.calls.append(("form", name))
        return self

    def expander(self, label):
        self.calls.append(("expander", label))
        return self

    def container(self, **kwargs):
        self.calls.append(("container", kwargs))
        return self

    def spinner(self, text):
        self.calls.append(("spinner", text))
        return self

    def text_input(self, label, **kwargs):
        return self._answer(label, "")

    def slider(self, label, minimum, maximum, value, *args, **kwargs):
        return self._answer(label, value)

    def selectbox(self, label, options, index=0, **kwargs):
        return self._answer(label, options[index])

    def multiselect(self, label, options, **kwargs):
        return self._answer(label, [])

    def checkbox(self, label, **kwargs):
        return self._answer(label, False)

    def number_input(self, label, value=None, **kwargs):
        return self._answer(label, value)

    def form_submit_button(self, *args, **kwargs):
        return self.submitted

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeColumn(self) for _ in range(count)]


def _school(*, score=80.0, coverage=100.0, pastoral=72.0, responses=50, website="school.example"):
    preference = (
        SchoolScore(overall=score, coverage_pct=coverage, components=())
        if score is not None
        else None
    )
    return SchoolResult(
        identity=SchoolIdentity(
            "100001",
            "Example School",
            sector="State-funded",
            age_range="11–16",
            gender="Mixed",
            faith_status="Non-faith",
            website=website,
        ),
        location=SchoolLocation(
            local_authority_code="E10000014",
            local_authority_name="Hampshire",
        ),
        academics=AcademicPerformance(
            attainment8=52.0,
            progress8=0.2,
            english_maths_grade5_pct=61.0,
        ),
        inspection=InspectionSummary(equivalent_rating="Good"),
        pastoral=PastoralCareStatistics(score=pastoral, response_count=responses),
        attendance=AttendanceStatistics(overall_absence_pct=6.0),
        behaviour=BehaviourStatistics(suspension_rate=4.0),
        workforce=WorkforceStatistics(pupil_teacher_ratio=16.0),
        travel=TravelInformation(distance_miles=1.2),
        preference_score=preference,
    )


def _benchmark():
    return SchoolBenchmarks(
        label="Hampshire",
        level="Local authority",
        code="E10000014",
        academics=AcademicPerformance(attainment8=48.0),
        attendance=AttendanceStatistics(overall_absence_pct=7.0),
        behaviour=BehaviourStatistics(suspension_rate=5.0),
        workforce=WorkforceStatistics(pupil_teacher_ratio=17.0),
    )


def _result(*, schools=None, current=True, termination_date=None, preferences=True, benchmarks=None):
    request = SchoolSearchRequest(
        "RG22 6SX",
        radius_miles=5,
        preferences=(
            streamlit_app.build_search_request(
                postcode="RG22 6SX",
                radius_miles=5,
                limit=10,
                preset=PreferencePreset.BALANCED,
            ).preferences
            if preferences
            else None
        ),
    )
    return SchoolSearchResult(
        request=request,
        postcode=PostcodeLocation("RG22 6SX", 1, 2, current, termination_date),
        schools=tuple(schools if schools is not None else [_school()]),
        benchmarks=tuple(benchmarks if benchmarks is not None else [_benchmark()]),
    )


def test_public_links_and_weight_labels_are_present():
    assert streamlit_app.REPO_URL == "https://github.com/c-wilkinson/school-finder"
    assert streamlit_app.BLOG_URL == "https://www.cadavre.co.uk/"
    assert streamlit_app.LINKEDIN_URL == "https://www.linkedin.com/in/craigawilkinson/"
    assert streamlit_app.BUY_ME_A_COFFEE_URL == "https://buymeacoffee.com/craigwilkinson"
    assert streamlit_app.PAYPAL_URL == "https://paypal.me/craigwilkinson1"
    assert "Pastoral care" in set(streamlit_app._WEIGHT_LABELS.values())


def test_measure_help_covers_parent_facing_metrics():
    expected = {
        "Distance",
        "Match",
        "Ofsted",
        "Attainment 8",
        "Progress 8",
        "Grade 5+ E&M",
        "English & Maths Grade 5+",
        "EBacc APS",
        "EBacc entry",
        "EBacc Grade 5+",
        "Triple science entry",
        "Pastoral care",
        "Absence",
        "Persistent absence",
        "Suspension rate",
        "Permanent exclusion rate",
        "Pupil/teacher",
        "Sustained destination",
    }
    assert expected <= set(streamlit_app.MEASURE_HELP)
    assert "0 is broadly average" in streamlit_app.MEASURE_HELP["Progress 8"]
    assert "not an Ofsted rating" in streamlit_app.MEASURE_HELP["Pastoral care"]


def test_cached_search_impl_delegates_to_core_service(monkeypatch, tmp_path):
    request = SchoolSearchRequest("X")
    expected = object()
    monkeypatch.setattr(streamlit_app, "search_schools", lambda path, req: (path, req, expected))
    path, returned_request, marker = streamlit_app._cached_search_impl(str(tmp_path), request)
    assert path == tmp_path
    assert returned_request is request
    assert marker is expected


def test_optional_number_uses_empty_value(monkeypatch):
    fake = FakeStreamlit({"Minimum": 42.0})
    monkeypatch.setattr(streamlit_app, "st", fake)
    assert streamlit_app._optional_number("Minimum", min_value=0.0) == 42.0


def test_sidebar_form_not_submitted_still_renders_links(monkeypatch):
    fake = FakeStreamlit(submitted=False)
    monkeypatch.setattr(streamlit_app, "st", fake)
    assert streamlit_app._sidebar_form() == (False, None)
    markdown = [call[1] for call in fake.calls if call[0] == "markdown"]
    assert any(streamlit_app.REPO_URL in value for value in markdown)
    assert any(streamlit_app.BLOG_URL in value for value in markdown)
    assert any(streamlit_app.LINKEDIN_URL in value for value in markdown)
    assert any(streamlit_app.BUY_ME_A_COFFEE_URL in value for value in markdown)
    assert any(streamlit_app.PAYPAL_URL in value for value in markdown)
    assert any("Support the project" in value for value in markdown)


def test_sidebar_form_builds_balanced_request(monkeypatch):
    fake = FakeStreamlit({"Postcode": "RG22 6SX"}, submitted=True)
    monkeypatch.setattr(streamlit_app, "st", fake)
    submitted, request = streamlit_app._sidebar_form()
    assert submitted is True
    assert request.postcode == "RG22 6SX"
    assert request.radius_miles == 5
    assert request.limit == 10
    assert request.preferences == streamlit_app.build_search_request(
        postcode="RG22 6SX", radius_miles=5, limit=10
    ).preferences


def test_sidebar_form_supports_custom_weights_and_all_filters(monkeypatch):
    answers = {
        "Postcode": "RG22 6SX",
        "Radius (miles)": 7.5,
        "Maximum results": 15,
        "What matters most?": "Custom",
        "Pastoral care": 80,
        "Distance": 20,
        "Ofsted": 0,
        "Attainment 8": 0,
        "Progress 8": 0,
        "English & Maths Grade 5+": 0,
        "EBacc APS": 0,
        "Phase": [SchoolPhase.SECONDARY],
        "Sector": [SchoolSector.STATE_FUNDED],
        "Gender": [SchoolGender.MIXED],
        "Faith": FaithFilter.NON_FAITH,
        "Selection": SelectionFilter.NON_SELECTIVE,
        "Include special/alternative provision": True,
        "Minimum Ofsted equivalent": OfstedRating.GOOD,
        "Minimum Attainment 8": 45.0,
        "Minimum Progress 8": 0.1,
        "Minimum Grade 5+ English & Maths (%)": 50.0,
        "Minimum EBacc APS": 4.0,
        "Minimum pastoral care score": 70.0,
    }
    fake = FakeStreamlit(answers, submitted=True)
    monkeypatch.setattr(streamlit_app, "st", fake)
    submitted, request = streamlit_app._sidebar_form()
    assert submitted is True
    assert request.radius_miles == 7.5
    assert request.limit == 15
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
    assert request.preferences.pastoral_care == 80


def test_sidebar_form_supports_sort_only(monkeypatch):
    fake = FakeStreamlit(
        {
            "Postcode": "RG22 6SX",
            "What matters most?": "No preference scoring",
            "Sort by": "Pastoral care",
            "Descending": True,
        },
        submitted=True,
    )
    monkeypatch.setattr(streamlit_app, "st", fake)
    submitted, request = streamlit_app._sidebar_form()
    assert submitted is True
    assert request.preferences is None
    assert request.sort.field is SchoolSortField.PASTORAL_CARE
    assert request.sort.direction is SortDirection.DESC


def test_render_school_card_shows_metrics_website_context_and_coverage(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    result = _result(schools=[_school(coverage=80, pastoral=None, responses=5)])
    streamlit_app._render_school_card(1, result.schools[0], result)
    text = "\n".join(str(call) for call in fake.calls)
    assert "School website" in text
    assert "Insufficient Parent View responses (5)" in text
    assert "80% of the requested preference data" in text
    assert "Compared with Hampshire" in text
    metric_calls = [call for call in fake.calls if call[0] == "metric"]
    assert metric_calls
    assert all(call[3].get("help") for call in metric_calls)
    assert any(call[1] == "Progress 8" and "0 is broadly average" in call[3]["help"] for call in metric_calls)


def test_render_school_card_handles_no_website_score_or_benchmark(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    school = _school(score=None, website=None)
    result = _result(schools=[school], preferences=False, benchmarks=[])
    streamlit_app._render_school_card(1, school, result)
    text = "\n".join(str(call) for call in fake.calls)
    assert "School website" not in text
    assert "Compared with" not in text


def test_render_results_handles_terminated_and_empty_search(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    result = _result(schools=[], current=False, termination_date="202401")
    streamlit_app._render_results(result)
    text = "\n".join(str(call) for call in fake.calls)
    assert "terminated" in text
    assert "No schools matched" in text


def test_render_results_renders_cards_and_benchmarks(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    rendered = []
    monkeypatch.setattr(streamlit_app, "_render_school_card", lambda i, school, result: rendered.append((i, school)))
    result = _result(schools=[_school(), _school()], benchmarks=[_benchmark()])
    streamlit_app._render_results(result)
    assert [item[0] for item in rendered] == [1, 2]
    assert any(call[0] == "dataframe" for call in fake.calls)
    markdown = [call[1] for call in fake.calls if call[0] == "markdown"]
    assert any("Attainment 8" in value and "eight GCSE-level" in value for value in markdown)
    assert any("Persistent absence" in value and "10%" in value for value in markdown)
    assert any("Sustained destination" in value for value in markdown)


def test_render_results_without_preferences_or_benchmarks(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_render_school_card", lambda *args: None)
    result = _result(preferences=False, benchmarks=[])
    streamlit_app._render_results(result)
    captions = [call[1] for call in fake.calls if call[0] == "caption"]
    assert not any("selected preferences" in value for value in captions)


def test_module_uses_streamlit_cache_and_runs_as_script(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)

    namespace = runpy.run_path(streamlit_app.__file__, run_name="__main__")

    assert namespace["_cached_search"] is namespace["_cached_search_impl"]
    assert any(call[0] == "cache_data" for call in fake.calls)
    assert ("title", "School Finder") in fake.calls


def test_module_without_streamlit_uses_uncached_search(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def import_without_streamlit(name, *args, **kwargs):
        if name == "streamlit":
            raise ImportError("streamlit intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_streamlit)

    namespace = runpy.run_path(streamlit_app.__file__, run_name="streamlit_app_without_web_extra")

    assert namespace["st"] is None
    assert namespace["_cached_search"] is namespace["_cached_search_impl"]



def test_main_requires_streamlit_when_web_extra_missing(monkeypatch):
    monkeypatch.setattr(streamlit_app, "st", None)
    with pytest.raises(ImportError, match="web extra"):
        streamlit_app.main()


def test_main_initial_state(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (False, None))
    streamlit_app.main()
    assert ("title", "School Finder") in fake.calls
    assert any(call[0] == "info" and "sidebar" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "Craig Wilkinson" in call[1] for call in fake.calls)


def test_sidebar_form_rejects_blank_postcode(monkeypatch):
    fake = FakeStreamlit({"Postcode": "   "}, submitted=True)
    monkeypatch.setattr(streamlit_app, "st", fake)
    assert streamlit_app._sidebar_form() == (True, None)
    assert any(call[0] == "error" and "Enter a postcode" in call[1] for call in fake.calls)


def test_sidebar_form_rejects_all_zero_custom_weights(monkeypatch):
    answers = {"Postcode": "RG22 6SX", "What matters most?": "Custom"}
    answers.update({label: 0 for label in streamlit_app._WEIGHT_LABELS.values()})
    fake = FakeStreamlit(answers, submitted=True)
    monkeypatch.setattr(streamlit_app, "st", fake)
    assert streamlit_app._sidebar_form() == (True, None)
    assert any(call[0] == "error" and "preference weight" in call[1] for call in fake.calls)


def test_main_submitted_invalid_form_does_not_search(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (True, None))
    monkeypatch.setattr(streamlit_app, "_cached_search", lambda *args: pytest.fail("should not search"))
    streamlit_app.main()


def test_main_runs_search_and_renders_results(monkeypatch, tmp_path):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    request = SchoolSearchRequest("RG22 6SX")
    expected = _result(preferences=False)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (True, request))
    monkeypatch.setenv("SCHOOL_FINDER_DATA_DIR", str(tmp_path))
    searched = []
    monkeypatch.setattr(streamlit_app, "_cached_search", lambda data_dir, req: searched.append((data_dir, req)) or expected)
    rendered = []
    monkeypatch.setattr(streamlit_app, "_render_results", lambda result: rendered.append(result))
    streamlit_app.main()
    assert searched == [(str(tmp_path), request)]
    assert rendered == [expected]


def test_main_shows_search_errors(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    request = SchoolSearchRequest("RG22 6SX")
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (True, request))
    monkeypatch.setattr(streamlit_app, "_cached_search", lambda *args: (_ for _ in ()).throw(ValueError("bad search")))
    streamlit_app.main()
    assert any(call[0] == "error" and "bad search" in call[1] for call in fake.calls)
