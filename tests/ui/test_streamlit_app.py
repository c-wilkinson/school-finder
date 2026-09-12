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
    DestinationStatistics,
    InspectionSummary,
    PastoralCareStatistics,
    SchoolBenchmarks,
    SchoolIdentity,
    SchoolLocation,
    SchoolResult,
    SubjectResult,
    TravelInformation,
    WorkforceStatistics,
)
from school_finder.models.scoring import SchoolScore
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.ui import streamlit_app
from school_finder.ui.state import LATEST_SEARCH_KEY, SELECTED_SCHOOL_URN_KEY


class FakeColumn:
    def __init__(self, parent):
        self.parent = parent

    def markdown(self, text):
        self.parent.calls.append(("markdown", text))

    def metric(self, label, value, **kwargs):
        self.parent.calls.append(("metric", label, value, kwargs))

    def button(self, label, **kwargs):
        return self.parent.button(label, **kwargs)


class FakePage:
    def __init__(self, parent, page, **kwargs):
        self.parent = parent
        self.page = page
        self.kwargs = kwargs

    def run(self):
        self.parent.calls.append(("page_run", self.kwargs))
        return self.page()


class FakeStreamlit:
    def __init__(self, answers=None, submitted=False):
        self.answers = answers or {}
        self.submitted = submitted
        self.calls = []
        self.sidebar = self
        self.session_state = {}

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

    def Page(self, page, **kwargs):
        self.calls.append(("Page", kwargs))
        return FakePage(self, page, **kwargs)

    def navigation(self, pages, **kwargs):
        self.calls.append(("navigation", len(pages), kwargs))
        return pages[0]

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

    def line_chart(self, frame, **kwargs):
        self.calls.append(("line_chart", tuple(frame.columns), kwargs))

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

    def button(self, label, **kwargs):
        self.calls.append(("button", label, kwargs))
        return self._answer(label, False)

    def switch_page(self, page):
        self.calls.append(("switch_page", page))

    def rerun(self):
        self.calls.append(("rerun",))

    def tabs(self, labels):
        self.calls.append(("tabs", tuple(labels)))
        return [self for _ in labels]

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
        "SW1A 2AA",
        radius_miles=5,
        preferences=(
            streamlit_app.build_search_request(
                postcode="SW1A 2AA",
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
        postcode=PostcodeLocation("SW1A 2AA", 1, 2, current, termination_date),
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
    fake = FakeStreamlit({"Postcode": "SW1A 2AA"}, submitted=True)
    monkeypatch.setattr(streamlit_app, "st", fake)
    submitted, request = streamlit_app._sidebar_form()
    assert submitted is True
    assert request.postcode == "SW1A 2AA"
    assert request.radius_miles == 5
    assert request.limit == 10
    assert request.preferences == streamlit_app.build_search_request(
        postcode="SW1A 2AA", radius_miles=5, limit=10
    ).preferences


def test_sidebar_form_supports_custom_weights_and_all_filters(monkeypatch):
    answers = {
        "Postcode": "SW1A 2AA",
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
            "Postcode": "SW1A 2AA",
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
    monkeypatch.setattr(streamlit_app, "_render_school_card", lambda i, school, result, detail_page=None, compare_page=None: rendered.append((i, school)))
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
    answers = {"Postcode": "SW1A 2AA", "What matters most?": "Custom"}
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
    request = SchoolSearchRequest("SW1A 2AA")
    expected = _result(preferences=False)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (True, request))
    monkeypatch.setenv("SCHOOL_FINDER_DATA_DIR", str(tmp_path))
    searched = []
    monkeypatch.setattr(streamlit_app, "_cached_search", lambda data_dir, req: searched.append((data_dir, req)) or expected)
    rendered = []
    monkeypatch.setattr(streamlit_app, "_render_results", lambda result, detail_page=None, compare_page=None: rendered.append(result))
    streamlit_app.main()
    assert searched == [(str(tmp_path), request)]
    assert rendered == [expected]


def test_main_shows_search_errors(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    request = SchoolSearchRequest("SW1A 2AA")
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (True, request))
    monkeypatch.setattr(streamlit_app, "_cached_search", lambda *args: (_ for _ in ()).throw(ValueError("bad search")))
    streamlit_app.main()
    assert any(call[0] == "error" and "bad search" in call[1] for call in fake.calls)


def test_main_uses_page_navigation_shell(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (False, None))

    streamlit_app.main()

    page_calls = [call for call in fake.calls if call[0] == "Page"]
    assert page_calls == [
        (
            "Page",
            {
                "title": "Find schools",
                "icon": "🔎",
                "url_path": "find-schools",
                "default": True,
            },
        ),
        (
            "Page",
            {
                "title": "Compare schools",
                "icon": "⚖️",
                "url_path": "compare-schools",
            },
        ),
        (
            "Page",
            {
                "title": "School detail",
                "icon": "🏫",
                "url_path": "school-detail",
            },
        ),
    ]
    assert ("navigation", 3, {}) in fake.calls
    assert any(call[0] == "page_run" for call in fake.calls)


def test_search_page_renders_stored_result_without_resubmitting(monkeypatch):
    fake = FakeStreamlit()
    expected = _result(preferences=False)
    fake.session_state[LATEST_SEARCH_KEY] = expected
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (False, None))
    rendered = []
    monkeypatch.setattr(streamlit_app, "_render_results", lambda result, detail_page=None, compare_page=None: rendered.append(result))

    streamlit_app._search_page()

    assert rendered == [expected]
    assert not any(call[0] == "info" and "get started" in call[1] for call in fake.calls)


def test_failed_search_preserves_and_renders_previous_result(monkeypatch):
    fake = FakeStreamlit()
    previous = _result(preferences=False)
    fake.session_state[LATEST_SEARCH_KEY] = previous
    request = SchoolSearchRequest("SW1A 2AA")
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_sidebar_form", lambda: (True, request))
    monkeypatch.setattr(
        streamlit_app,
        "_cached_search",
        lambda *args: (_ for _ in ()).throw(ValueError("bad search")),
    )
    rendered = []
    monkeypatch.setattr(streamlit_app, "_render_results", lambda result, detail_page=None, compare_page=None: rendered.append(result))

    streamlit_app._search_page()

    assert rendered == [previous]
    assert any(call[0] == "error" and "bad search" in call[1] for call in fake.calls)



def test_cached_subjects_impl_uses_data_directory(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(
        streamlit_app,
        "get_school_subject_results",
        lambda path, urn: called.append((path, urn)) or ("subject",),
    )
    assert streamlit_app._cached_subjects_impl(str(tmp_path), "100001") == ("subject",)
    assert called == [(tmp_path, "100001")]


def test_school_card_view_details_selects_school_and_switches(monkeypatch):
    fake = FakeStreamlit({"View details": True})
    monkeypatch.setattr(streamlit_app, "st", fake)
    school = _school()
    result = _result(schools=[school])
    detail_page = object()

    streamlit_app._render_school_card(1, school, result, detail_page)

    assert fake.session_state[SELECTED_SCHOOL_URN_KEY] == "100001"
    assert ("switch_page", detail_page) in fake.calls


def test_render_detail_table_handles_rows_and_empty(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)

    streamlit_app._render_detail_table([{"A": "B"}], "Nothing here")
    streamlit_app._render_detail_table([], "Nothing here")

    assert any(call[0] == "dataframe" and call[1] == ("A",) for call in fake.calls)
    assert any(call[0] == "info" and call[1] == "Nothing here" for call in fake.calls)


def test_render_overview_and_academics_show_sources_and_years(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    school = _school()
    academics = replace(
        school.academics,
        data_year="2024/25",
        progress8_year="2023/24",
    )
    school = replace(school, academics=academics)

    streamlit_app._render_overview(school)
    streamlit_app._render_academics(school, ())

    assert any(call[0] == "markdown" and "School website" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "Performance data: 2024/25" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "Progress 8" in call[1] and "2023/24" in call[1] for call in fake.calls)

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    no_website = replace(school, identity=replace(school.identity, website=None))
    streamlit_app._render_overview(no_website)
    assert not any(call[0] == "markdown" and "School website" in call[1] for call in fake.calls)


def test_render_subjects_handles_success_and_failure(monkeypatch, tmp_path):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setenv("SCHOOL_FINDER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        streamlit_app,
        "_cached_subjects",
        lambda data_dir, urn: (
            SubjectResult(urn, data_year="2024/25", subject="Maths", entries=100),
        ),
    )
    streamlit_app._render_subjects(_school())
    assert any(call[0] == "dataframe" and "Subject" in call[1] for call in fake.calls)

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(
        streamlit_app,
        "_cached_subjects",
        lambda *args: (_ for _ in ()).throw(ValueError("subject failure")),
    )
    streamlit_app._render_subjects(_school())
    assert any(call[0] == "warning" and "subject failure" in call[1] for call in fake.calls)


def test_render_ofsted_explains_equivalents_and_linked_source(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    school = _school()
    derived = replace(
        school,
        inspection=InspectionSummary(
            equivalent_rating="Good",
            source_school_name="Predecessor School",
            source_urn="999999",
        ),
    )
    streamlit_app._render_ofsted(derived)
    assert any(call[0] == "info" and "No official overall" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "Predecessor School" in call[1] and "999999" in call[1] for call in fake.calls)

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    different = replace(
        school,
        inspection=InspectionSummary(
            rating="Requires improvement",
            equivalent_rating="Good",
            equivalent_explanation="Derived explanation",
            source_school_name="Predecessor School",
        ),
    )
    streamlit_app._render_ofsted(different)
    assert any(call[0] == "caption" and "shown separately" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "Predecessor School" in call[1] for call in fake.calls)

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    explained = replace(
        school,
        inspection=InspectionSummary(equivalent_rating="Good", equivalent_explanation="My explanation"),
    )
    streamlit_app._render_ofsted(explained)
    assert ("info", "My explanation") in fake.calls


def test_render_pastoral_staffing_and_destinations_show_metadata(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    school = _school()
    school = replace(
        school,
        pastoral=replace(
            school.pastoral,
            survey_year="2025",
            source_url="https://example.com/parent-view",
        ),
        attendance=replace(school.attendance, data_year="2024/25"),
        behaviour=replace(school.behaviour, data_year="2024/25"),
        workforce=replace(school.workforce, data_year="2024/25"),
        destinations=DestinationStatistics(
            destination_year="2024/25",
            leaver_year="2022/23",
            sustained_destination_pct=94,
        ),
    )

    streamlit_app._render_pastoral_behaviour(school, ())
    streamlit_app._render_staffing(school, ())
    streamlit_app._render_destinations(school, ())

    captions = [call[1] for call in fake.calls if call[0] == "caption"]
    assert any("Parent View survey year: 2025" in value for value in captions)
    assert any("Attendance data: 2024/25" in value for value in captions)
    assert any("Behaviour data: 2024/25" in value for value in captions)
    assert any("Workforce data: 2024/25" in value for value in captions)
    assert any("Destination data: 2024/25 for 2022/23 leavers" in value for value in captions)
    assert any(call[0] == "markdown" and "Parent View source" in call[1] for call in fake.calls)

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    no_leaver = replace(
        school,
        destinations=replace(school.destinations, leaver_year=None),
    )
    streamlit_app._render_destinations(no_leaver, ())
    assert any(call[0] == "caption" and call[1] == "Destination data: 2024/25" for call in fake.calls)


def test_detail_page_without_selection_can_return_to_search(monkeypatch):
    search_page = object()
    fake = FakeStreamlit({"← Back to find schools": True})
    monkeypatch.setattr(streamlit_app, "st", fake)

    streamlit_app._detail_page(search_page)

    assert ("title", "School detail") in fake.calls
    assert any(call[0] == "info" and "Choose a school" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "latest successful search" in call[1] for call in fake.calls)
    assert ("switch_page", search_page) in fake.calls


def test_detail_page_with_selected_school_renders_every_section(monkeypatch):
    search_page = object()
    fake = FakeStreamlit({"← Back to results": True})
    school = _school(coverage=80)
    school = replace(
        school,
        academics=replace(school.academics, data_year="2024/25"),
        destinations=DestinationStatistics(destination_year="2024/25", sustained_destination_pct=94),
    )
    england = SchoolBenchmarks(
        label="England",
        level="National",
        code="E92000001",
        academics=AcademicPerformance(attainment8=47),
    )
    result = _result(schools=[school], benchmarks=[_benchmark(), england])
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[SELECTED_SCHOOL_URN_KEY] = school.identity.urn
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_cached_subjects", lambda *args: ())

    streamlit_app._detail_page(search_page)

    assert ("switch_page", search_page) in fake.calls
    assert ("title", "Example School") in fake.calls
    assert any(call[0] == "caption" and "80%" in call[1] for call in fake.calls)
    assert any(call[0] == "caption" and "Benchmark columns" in call[1] for call in fake.calls)
    tabs = next(call for call in fake.calls if call[0] == "tabs")
    assert tabs[1] == (
        "Overview",
        "Academics",
        "Subjects",
        "Ofsted",
        "Pastoral & behaviour",
        "Staffing",
        "Destinations",
    )


def test_detail_page_handles_stale_selection_without_no_search_caption(monkeypatch):
    fake = FakeStreamlit()
    fake.session_state[LATEST_SEARCH_KEY] = _result(schools=[_school()])
    fake.session_state[SELECTED_SCHOOL_URN_KEY] = "missing"
    monkeypatch.setattr(streamlit_app, "st", fake)

    streamlit_app._detail_page()

    assert any(call[0] == "info" and "Choose a school" in call[1] for call in fake.calls)
    assert not any(call[0] == "caption" and "latest successful search" in call[1] for call in fake.calls)


def test_detail_renderers_cover_missing_optional_metadata(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    school = _school(score=None)
    school = replace(
        school,
        academics=replace(school.academics, data_year=None, progress8_year=None),
        inspection=InspectionSummary(rating="Good", equivalent_rating="Good"),
        pastoral=replace(school.pastoral, score=72, response_count=None, survey_year=None, source_url=None),
        attendance=replace(school.attendance, data_year=None),
        behaviour=replace(school.behaviour, data_year=None),
        workforce=replace(school.workforce, data_year=None),
        destinations=DestinationStatistics(sustained_destination_pct=94),
    )

    streamlit_app._render_academics(school, ())
    streamlit_app._render_ofsted(school)
    streamlit_app._render_pastoral_behaviour(school, ())
    streamlit_app._render_staffing(school, ())
    streamlit_app._render_destinations(school, ())

    assert not any(call[0] == "caption" and "Performance data:" in call[1] for call in fake.calls)
    assert not any(call[0] == "info" and "official overall" in call[1] for call in fake.calls)


def test_detail_page_without_optional_score_benchmarks_or_back_page(monkeypatch):
    fake = FakeStreamlit()
    school = _school(score=None)
    result = _result(schools=[school], benchmarks=[])
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[SELECTED_SCHOOL_URN_KEY] = school.identity.urn
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_cached_subjects", lambda *args: ())

    streamlit_app._detail_page()

    assert ("title", "Example School") in fake.calls
    assert not any(call[0] == "switch_page" for call in fake.calls)
    assert not any(call[0] == "caption" and "Benchmark columns" in call[1] for call in fake.calls)
    assert not any(call[0] == "caption" and "requested preference data" in call[1] for call in fake.calls)


def _trend_history():
    import pandas as pd

    rows = []
    for year, school, local, national in (
        ("202223", 48.0, 47.0, 46.0),
        ("202324", 50.0, 48.0, 47.0),
        ("202425", 52.0, 49.0, 48.0),
        ("202526", 53.0, 50.0, 49.0),
    ):
        rows.extend(
            [
                {"domain": "academics", "year": year, "metric": "attainment8", "series": "School", "value": school, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0},
                {"domain": "academics", "year": year, "metric": "attainment8", "series": "Hampshire", "value": local, "source_urn": None, "source_school_name": None, "source_kind": None, "source_link_depth": None},
                {"domain": "academics", "year": year, "metric": "attainment8", "series": "England", "value": national, "source_urn": None, "source_school_name": None, "source_kind": None, "source_link_depth": None},
            ]
        )
    rows[0]["source_kind"] = "predecessor"
    rows[0]["source_school_name"] = "Old School"
    return pd.DataFrame(rows)


def test_render_trends_charts_metric_period_benchmarks_and_lineage(monkeypatch):
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)

    streamlit_app._render_trends(_trend_history(), "academics")

    charts = [call for call in fake.calls if call[0] == "line_chart"]
    assert len(charts) == 1
    assert charts[0][1] == ("Year", "School", "England", "Hampshire")
    assert charts[0][2]["width"] == "stretch"
    captions = [call[1] for call in fake.calls if call[0] == "caption"]
    assert any("local-authority and England" in caption for caption in captions)
    assert any("predecessor school: Old School" in caption for caption in captions)


def test_render_trends_handles_error_empty_and_insufficient_history(monkeypatch):
    import pandas as pd

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._render_trends(None, "academics", error="broken")
    streamlit_app._render_trends(pd.DataFrame(), "academics")
    streamlit_app._render_trends(
        pd.DataFrame(
            [
                {"domain": "academics", "year": "202425", "metric": "attainment8", "series": "School", "value": 52.0, "source_kind": "current", "source_school_name": "Example"}
            ]
        ),
        "academics",
    )

    captions = [call[1] for call in fake.calls if call[0] == "caption"]
    assert "Trend data unavailable: broken" in captions
    assert "No historical data is currently available for this area." in captions
    assert "There are not yet two comparable published years for this area." in captions
    assert not any(call[0] == "line_chart" for call in fake.calls)


def test_detail_page_loads_history_once_and_uses_it_for_trend_tabs(monkeypatch):
    fake = FakeStreamlit()
    school = _school()
    result = _result(schools=[school], benchmarks=[_benchmark()])
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[SELECTED_SCHOOL_URN_KEY] = school.identity.urn
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_cached_subjects", lambda *args: ())
    calls = []
    monkeypatch.setattr(
        streamlit_app,
        "_cached_history",
        lambda data_dir, urn, la: calls.append((data_dir, urn, la)) or _trend_history(),
    )

    streamlit_app._detail_page()

    assert len(calls) == 1
    assert calls[0][1:] == ("100001", "E10000014")
    assert any(call[0] == "line_chart" for call in fake.calls)


def test_detail_page_degrades_when_history_lookup_fails(monkeypatch):
    fake = FakeStreamlit()
    school = _school()
    result = _result(schools=[school], benchmarks=[_benchmark()])
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[SELECTED_SCHOOL_URN_KEY] = school.identity.urn
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_cached_subjects", lambda *args: ())
    monkeypatch.setattr(
        streamlit_app,
        "_cached_history",
        lambda *args: (_ for _ in ()).throw(ValueError("history failed")),
    )

    streamlit_app._detail_page()

    assert any(
        call[0] == "caption" and "Trend data unavailable: history failed" in call[1]
        for call in fake.calls
    )


def test_render_trends_two_year_school_only_series_skips_period_and_benchmark_caption(monkeypatch):
    import pandas as pd

    history = pd.DataFrame(
        [
            {"domain": "academics", "year": "202324", "metric": "pupil_count", "series": "School", "value": 170, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0},
            {"domain": "academics", "year": "202425", "metric": "pupil_count", "series": "School", "value": 180, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0},
        ]
    )
    fake = FakeStreamlit(answers={"Metric": "pupil_count"})
    monkeypatch.setattr(streamlit_app, "st", fake)

    streamlit_app._render_trends(history, "academics")

    assert not any(call[0] == "selectbox" and call[1] == "Period" for call in fake.calls)
    assert any(call[0] == "line_chart" for call in fake.calls)
    assert not any(
        call[0] == "caption" and "local-authority and England" in call[1]
        for call in fake.calls
    )
    assert not any(
        call[0] == "caption" and "predecessor" in call[1]
        for call in fake.calls
    )


def test_render_trends_handles_selected_metric_with_less_than_two_chart_rows(monkeypatch):
    import pandas as pd

    history = pd.DataFrame(
        [
            {"domain": "academics", "year": "202324", "metric": "attainment8", "series": "School", "value": 50.0, "source_kind": "current", "source_school_name": "Example"},
            {"domain": "academics", "year": "202425", "metric": "attainment8", "series": "School", "value": 52.0, "source_kind": "current", "source_school_name": "Example"},
        ]
    )
    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    one_row = pd.DataFrame({"Year": ["2024/25"], "School": [52.0]})
    monkeypatch.setattr(streamlit_app, "trend_frame", lambda *args, **kwargs: one_row)

    streamlit_app._render_trends(history, "academics")

    assert any(
        call[0] == "caption" and "not yet two comparable published years for this metric" in call[1]
        for call in fake.calls
    )
    assert not any(call[0] == "line_chart" for call in fake.calls)


def test_school_card_adds_removes_and_warns_at_compare_limit(monkeypatch):
    from school_finder.ui.state import COMPARE_URNS_KEY

    school = _school()
    result = _result(schools=[school])

    fake = FakeStreamlit({"Add to compare": True})
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._render_school_card(1, school, result)
    assert fake.session_state[COMPARE_URNS_KEY] == ["100001"]

    fake = FakeStreamlit({"Remove from compare": True})
    fake.session_state[COMPARE_URNS_KEY] = ["100001"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._render_school_card(1, school, result)
    assert COMPARE_URNS_KEY not in fake.session_state

    fake = FakeStreamlit({"Add to compare": True})
    fake.session_state[COMPARE_URNS_KEY] = ["1", "2", "3", "4"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._render_school_card(1, school, result)
    assert any(call[0] == "warning" and "up to 4" in call[1] for call in fake.calls)


def test_school_card_can_select_four_schools_sequentially(monkeypatch):
    from dataclasses import replace
    from school_finder.ui.state import COMPARE_URNS_KEY

    first = _school()
    schools = [
        replace(
            first,
            identity=replace(
                first.identity,
                urn=f"10000{index}",
                name=f"School {index}",
            ),
        )
        for index in range(1, 5)
    ]
    result = _result(schools=schools)
    fake = FakeStreamlit({"Add to compare": True})
    monkeypatch.setattr(streamlit_app, "st", fake)

    for index, school in enumerate(schools, start=1):
        streamlit_app._render_school_card(index, school, result)

    assert fake.session_state[COMPARE_URNS_KEY] == [
        "100001",
        "100002",
        "100003",
        "100004",
    ]
    assert len([call for call in fake.calls if call == ("rerun",)]) == 4


def test_render_results_compare_selection_prompt_and_navigation(monkeypatch):
    from school_finder.ui.state import COMPARE_URNS_KEY

    school = _school()
    result = _result(schools=[school])
    monkeypatch.setattr(streamlit_app, "_render_school_card", lambda *args, **kwargs: None)

    fake = FakeStreamlit()
    fake.session_state[COMPARE_URNS_KEY] = ["100001"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._render_results(result, compare_page=object())
    assert any(call[0] == "caption" and "Select at least 2" in call[1] for call in fake.calls)

    compare_page = object()
    fake = FakeStreamlit({"Compare selected (2)": True})
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._render_results(result, compare_page=compare_page)
    assert ("switch_page", compare_page) in fake.calls


def test_detail_compare_actions_add_remove_open_and_limit(monkeypatch):
    from school_finder.ui.state import COMPARE_URNS_KEY, LATEST_SEARCH_KEY, SELECTED_SCHOOL_URN_KEY

    school = _school()
    result = _result(schools=[school])
    compare_page = object()

    def prepare(fake):
        fake.session_state[LATEST_SEARCH_KEY] = result
        fake.session_state[SELECTED_SCHOOL_URN_KEY] = "100001"
        monkeypatch.setattr(streamlit_app, "st", fake)
        monkeypatch.setattr(streamlit_app, "_cached_history", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_overview", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_academics", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_subjects", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_ofsted", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_pastoral_behaviour", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_staffing", lambda *args: None)
        monkeypatch.setattr(streamlit_app, "_render_destinations", lambda *args: None)

    fake = FakeStreamlit({"Add to compare": True})
    prepare(fake)
    streamlit_app._detail_page(compare_page=compare_page)
    assert fake.session_state[COMPARE_URNS_KEY] == ["100001"]

    fake = FakeStreamlit({"Remove from compare": True})
    prepare(fake)
    fake.session_state[COMPARE_URNS_KEY] = ["100001"]
    streamlit_app._detail_page(compare_page=compare_page)
    assert COMPARE_URNS_KEY not in fake.session_state

    fake = FakeStreamlit({"Compare selected": True})
    prepare(fake)
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    streamlit_app._detail_page(compare_page=compare_page)
    assert ("switch_page", compare_page) in fake.calls

    fake = FakeStreamlit({"Add to compare": True})
    prepare(fake)
    fake.session_state[COMPARE_URNS_KEY] = ["1", "2", "3", "4"]
    streamlit_app._detail_page(compare_page=compare_page)
    assert any(call[0] == "warning" and "up to 4" in call[1] for call in fake.calls)


def test_compare_page_empty_and_insufficient_selection(monkeypatch):
    from school_finder.ui.state import COMPARE_URNS_KEY, LATEST_SEARCH_KEY

    search_page = object()
    fake = FakeStreamlit({"← Find schools": True})
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page)
    assert ("switch_page", search_page) in fake.calls

    fake = FakeStreamlit({"← Back to results": True})
    fake.session_state[LATEST_SEARCH_KEY] = _result(schools=[_school()])
    fake.session_state[COMPARE_URNS_KEY] = ["100001"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page)
    assert ("switch_page", search_page) in fake.calls


def test_compare_page_renders_opens_details_removes_and_navigates(monkeypatch):
    from dataclasses import replace
    from school_finder.ui.state import COMPARE_URNS_KEY, LATEST_SEARCH_KEY, SELECTED_SCHOOL_URN_KEY

    first = _school()
    second = replace(first, identity=replace(first.identity, urn="100002", name="Second School"))
    result = _result(schools=[first, second])
    search_page = object()
    detail_page = object()

    fake = FakeStreamlit({"View details": True})
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page, detail_page=detail_page)
    assert fake.session_state[SELECTED_SCHOOL_URN_KEY] in {"100001", "100002"}
    assert ("switch_page", detail_page) in fake.calls
    assert len([call for call in fake.calls if call[0] == "dataframe"]) == len(streamlit_app.COMPARISON_SECTIONS)

    fake = FakeStreamlit({"Remove": True})
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page()
    assert streamlit_app.get_compare_urns(fake.session_state) == ()

    fake = FakeStreamlit({"← Back to results": True})
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page)
    assert ("switch_page", search_page) in fake.calls

    fake = FakeStreamlit({"Clear comparison": True})
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page)
    assert streamlit_app.get_compare_urns(fake.session_state) == ()
    assert ("switch_page", search_page) in fake.calls

    fake = FakeStreamlit({"Clear comparison": True})
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page()
    assert streamlit_app.get_compare_urns(fake.session_state) == ()


def test_compare_navigation_buttons_can_be_left_unpressed(monkeypatch):
    from dataclasses import replace
    from school_finder.ui.state import COMPARE_URNS_KEY, LATEST_SEARCH_KEY

    first = _school()
    second = replace(first, identity=replace(first.identity, urn="100002", name="Second School"))
    result = _result(schools=[first, second])
    search_page = object()
    compare_page = object()

    fake = FakeStreamlit()
    fake.session_state[COMPARE_URNS_KEY] = ["100001", "100002"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    monkeypatch.setattr(streamlit_app, "_render_school_card", lambda *args, **kwargs: None)
    streamlit_app._render_results(result, compare_page=compare_page)
    assert ("switch_page", compare_page) not in fake.calls

    fake = FakeStreamlit()
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page)
    assert ("switch_page", search_page) not in fake.calls

    fake = FakeStreamlit()
    fake.session_state[LATEST_SEARCH_KEY] = result
    fake.session_state[COMPARE_URNS_KEY] = ["100001"]
    monkeypatch.setattr(streamlit_app, "st", fake)
    streamlit_app._compare_page(search_page=search_page)
    assert ("switch_page", search_page) not in fake.calls
