"""Streamlit application shell for School Finder."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

try:
    import streamlit as st
except ImportError:  # Streamlit is an optional web dependency.
    st = None

from school_finder.config import DEFAULT_DATA_DIR
from school_finder.errors import SchoolFinderError
from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SelectionFilter,
)
from school_finder.models.preferences import PreferenceMetric, PreferencePreset
from school_finder.models.school import SchoolResult
from school_finder.models.search import SchoolSearchResult
from school_finder.services.history import get_school_history
from school_finder.services.search import search_schools
from school_finder.services.subjects import get_school_subject_results
from school_finder.ui.controls import (
    CUSTOM_DEFAULT_WEIGHTS,
    PRESET_LABELS,
    SORT_LABELS,
    build_search_request,
)
from school_finder.ui.detail import (
    DEFAULT_TREND_METRIC,
    TREND_METRIC_LABELS,
    available_trend_metrics,
    academic_rows,
    attendance_rows,
    behaviour_rows,
    destination_rows,
    find_school,
    inspection_rows,
    overview_rows,
    pastoral_rows,
    relevant_benchmarks,
    subject_rows,
    trend_frame,
    trend_lineage_note,
    workforce_ratio_rows,
    workforce_rows,
)
from school_finder.ui.formatting import (
    benchmark_comparisons,
    benchmark_for_school,
    benchmark_rows,
    MEASURE_HELP,
    format_distance,
    format_match_score,
    format_number,
    format_percent,
    format_progress8,
    format_ratio,
    normalise_website,
    ofsted_display,
    pastoral_note,
)
from school_finder.ui.state import (
    get_latest_search,
    get_selected_school_urn,
    select_school,
    set_latest_search,
)

REPO_URL = "https://github.com/c-wilkinson/school-finder"
BLOG_URL = "https://www.cadavre.co.uk/"
LINKEDIN_URL = "https://www.linkedin.com/in/craigawilkinson/"
BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/craigwilkinson"
PAYPAL_URL = "https://paypal.me/craigwilkinson1"

_WEIGHT_LABELS = {
    PreferenceMetric.DISTANCE: "Distance",
    PreferenceMetric.OFSTED: "Ofsted",
    PreferenceMetric.ATTAINMENT8: "Attainment 8",
    PreferenceMetric.PROGRESS8: "Progress 8",
    PreferenceMetric.GRADE5_ENGLISH_MATHS: "English & Maths Grade 5+",
    PreferenceMetric.EBACC_APS: "EBacc APS",
    PreferenceMetric.PASTORAL_CARE: "Pastoral care",
}


def _cached_search_impl(data_dir: str, request):
    return search_schools(Path(data_dir), request)


def _cached_subjects_impl(data_dir: str, urn: str):
    return get_school_subject_results(Path(data_dir), urn)


def _cached_history_impl(data_dir: str, urn: str, local_authority_code: str | None):
    return get_school_history(Path(data_dir), urn, local_authority_code)


if st is not None:
    _cached_search = st.cache_data(ttl=900, show_spinner=False)(_cached_search_impl)
    _cached_subjects = st.cache_data(ttl=900, show_spinner=False)(_cached_subjects_impl)
    _cached_history = st.cache_data(ttl=900, show_spinner=False)(_cached_history_impl)
else:
    _cached_search = _cached_search_impl
    _cached_subjects = _cached_subjects_impl
    _cached_history = _cached_history_impl


def _optional_number(label: str, **kwargs) -> float | None:
    return st.number_input(label, value=None, placeholder="Any", **kwargs)


def _sidebar_form():
    with st.sidebar:
        st.header("Find schools")
        with st.form("school-search"):
            postcode = st.text_input("Postcode", placeholder="e.g. SW1A 2AA")
            radius = st.slider("Radius (miles)", 1.0, 20.0, 5.0, 0.5)
            limit = st.slider("Maximum results", 5, 25, 10)
            preset_label = st.selectbox("What matters most?", tuple(PRESET_LABELS), index=0)
            preset = PRESET_LABELS[preset_label]
            st.caption(
                "Choose Pastoral focused, or Custom, if Parent View pastoral care should influence the ranking."
            )

            custom_weights = None
            if preset is PreferencePreset.CUSTOM:
                st.caption("Weights are relative and do not need to add up to 100.")
                custom_weights = {
                    metric: st.slider(
                        label,
                        0,
                        100,
                        int(CUSTOM_DEFAULT_WEIGHTS[metric]),
                        key=f"weight-{metric.value}",
                        help=MEASURE_HELP.get(label),
                    )
                    for metric, label in _WEIGHT_LABELS.items()
                }

            sort_field = next(iter(SORT_LABELS.values()))
            descending = False
            with st.expander("Advanced filters"):
                phases = tuple(st.multiselect("Phase", list(SchoolPhase), format_func=str))
                sectors = tuple(st.multiselect("Sector", list(SchoolSector), format_func=str))
                genders = tuple(st.multiselect("Gender", list(SchoolGender), format_func=str))
                faith = st.selectbox("Faith", list(FaithFilter), format_func=lambda value: value.value.title())
                selection = st.selectbox(
                    "Selection",
                    list(SelectionFilter),
                    format_func=lambda value: value.value.title(),
                )
                include_special = st.checkbox("Include special/alternative provision")
                ofsted_options = [None, *list(OfstedRating)]
                minimum_ofsted = st.selectbox(
                    "Minimum Ofsted equivalent",
                    ofsted_options,
                    format_func=lambda value: "Any" if value is None else value.value,
                    help=MEASURE_HELP["Ofsted"],
                )
                minimum_attainment8 = _optional_number(
                    "Minimum Attainment 8", min_value=0.0, step=1.0, help=MEASURE_HELP["Attainment 8"]
                )
                minimum_progress8 = _optional_number(
                    "Minimum Progress 8", step=0.1, format="%.2f", help=MEASURE_HELP["Progress 8"]
                )
                minimum_grade5 = _optional_number(
                    "Minimum Grade 5+ English & Maths (%)",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    help=MEASURE_HELP["English & Maths Grade 5+"],
                )
                minimum_ebacc = _optional_number(
                    "Minimum EBacc APS",
                    min_value=0.0,
                    max_value=10.0,
                    step=0.1,
                    help=MEASURE_HELP["EBacc APS"],
                )
                minimum_pastoral = _optional_number(
                    "Minimum pastoral care score",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    help=MEASURE_HELP["Pastoral care"],
                )
                if preset is None:
                    sort_label = st.selectbox("Sort by", tuple(SORT_LABELS), index=0)
                    sort_field = SORT_LABELS[sort_label]
                    descending = st.checkbox("Descending")

            submitted = st.form_submit_button("Find schools", type="primary", width="stretch")

        st.markdown("---")
        st.markdown(f"[View the project on GitHub]({REPO_URL})")
        st.markdown(f"[Read my blog]({BLOG_URL})")
        st.markdown(f"[Connect on LinkedIn]({LINKEDIN_URL})")

        st.markdown("---")
        st.markdown("**Support the project**")
        st.markdown(f"☕ [Buy me a coffee]({BUY_ME_A_COFFEE_URL})")
        st.markdown(f"💙 [PayPal]({PAYPAL_URL})")

    if not submitted:
        return False, None
    if not postcode.strip():
        st.error("Enter a postcode to search.")
        return True, None
    if custom_weights is not None and sum(custom_weights.values()) <= 0:
        st.error("Choose at least one preference weight greater than zero.")
        return True, None
    return True, build_search_request(
        postcode=postcode,
        radius_miles=radius,
        limit=limit,
        phases=phases,
        sectors=sectors,
        genders=genders,
        faith=faith,
        selection=selection,
        include_special=include_special,
        minimum_ofsted_rating=minimum_ofsted,
        minimum_attainment8=minimum_attainment8,
        minimum_progress8=minimum_progress8,
        minimum_grade5_english_maths_pct=minimum_grade5,
        minimum_ebacc_aps=minimum_ebacc,
        minimum_pastoral_score=minimum_pastoral,
        preset=preset,
        custom_weights=custom_weights,
        sort_field=sort_field,
        descending=descending,
    )


def _render_school_card(
    index: int,
    school: SchoolResult,
    result: SchoolSearchResult,
    detail_page=None,
) -> None:
    with st.container(border=True):
        title, distance, match = st.columns([6, 2, 2])
        title.markdown(f"### {index}. {school.identity.name}")
        website = normalise_website(school.identity.website)
        if website:
            title.markdown(f"[School website]({website})")
        distance.metric("Distance", format_distance(school.travel.distance_miles), help=MEASURE_HELP["Distance"])
        match_value = school.preference_score.overall if school.preference_score else None
        match.metric("Match", format_match_score(match_value), help=MEASURE_HELP["Match"])

        details = [
            school.identity.sector,
            school.identity.age_range,
            school.identity.gender,
            school.identity.faith_status,
            school.location.local_authority_name,
        ]
        st.caption(" • ".join(value for value in details if value))

        metrics = st.columns(4)
        metrics[0].metric("Ofsted", ofsted_display(school), help=MEASURE_HELP["Ofsted"])
        metrics[1].metric("Attainment 8", format_number(school.academics.attainment8), help=MEASURE_HELP["Attainment 8"])
        metrics[2].metric("Progress 8", format_progress8(school.academics.progress8), help=MEASURE_HELP["Progress 8"])
        metrics[3].metric("Grade 5+ E&M", format_percent(school.academics.english_maths_grade5_pct), help=MEASURE_HELP["Grade 5+ E&M"])

        metrics = st.columns(4)
        metrics[0].metric("Pastoral care", format_number(school.pastoral.score), help=MEASURE_HELP["Pastoral care"])
        metrics[1].metric("Absence", format_percent(school.attendance.overall_absence_pct), help=MEASURE_HELP["Absence"])
        metrics[2].metric("Suspension rate", format_number(school.behaviour.suspension_rate), help=MEASURE_HELP["Suspension rate"])
        metrics[3].metric("Pupil/teacher", format_ratio(school.workforce.pupil_teacher_ratio), help=MEASURE_HELP["Pupil/teacher"])

        note = pastoral_note(school)
        if note and school.pastoral.score is None:
            st.caption(note)
        if school.preference_score and school.preference_score.coverage_pct < 100:
            st.caption(
                f"Match score uses {school.preference_score.coverage_pct:.0f}% of the requested preference data."
            )

        benchmark = benchmark_for_school(school, result.benchmarks)
        comparisons = benchmark_comparisons(school, benchmark)
        if benchmark and comparisons:
            st.caption(f"Compared with {benchmark.label}: " + " • ".join(comparisons))

        if detail_page is not None and st.button(
            "View details",
            key=f"school-details-{school.identity.urn}",
        ):
            select_school(st.session_state, school.identity.urn)
            st.switch_page(detail_page)


def _render_results(result: SchoolSearchResult, detail_page=None) -> None:
    if not result.postcode.is_current:
        detail = f" ({result.postcode.termination_date})" if result.postcode.termination_date else ""
        st.warning(f"The supplied postcode is marked as terminated{detail}; using its last known coordinates.")

    if not result.schools:
        st.info("No schools matched the search criteria.")
        return

    st.subheader(f"Found {len(result.schools)} schools")
    if result.request.preferences is not None:
        st.caption("Schools are ranked using your selected preferences. Missing data is not treated as zero.")

    for index, school in enumerate(result.schools, start=1):
        _render_school_card(index, school, result, detail_page)

    with st.expander("What do these measures mean?"):
        for label in (
            "Distance",
            "Match",
            "Ofsted",
            "Pupil count",
            "Attainment 8",
            "Progress 8",
            "English & Maths Grade 5+",
            "EBacc APS",
            "EBacc entry",
            "EBacc Grade 5+",
            "Triple science entry",
            "Pastoral care",
            "Parent View responses",
            "Absence",
            "Persistent absence",
            "Suspension rate",
            "Permanent exclusion rate",
            "Pupil/teacher",
            "Sustained destination",
        ):
            st.markdown(f"**{label}** — {MEASURE_HELP[label]}")

    if result.benchmarks:
        with st.expander("Benchmark context"):
            st.caption("National and local-authority comparison figures where available.")
            st.dataframe(pd.DataFrame(benchmark_rows(result.benchmarks)), hide_index=True, width="stretch")

    st.caption("Ofsted values may be School Finder equivalents where no official overall grade is available.")


def _search_page(detail_page=None) -> None:
    """Render the school search page and preserve the latest successful result."""
    st.title("School Finder")
    st.markdown(
        "Find, compare and rank secondary schools in England using public DfE, Ofsted and ONS data."
    )
    st.caption("Choose what matters to you, then School Finder ranks the schools that match your filters.")

    submitted, request = _sidebar_form()
    search_failed = False
    if submitted and request is not None:
        data_dir = os.environ.get("SCHOOL_FINDER_DATA_DIR", str(DEFAULT_DATA_DIR))
        try:
            with st.spinner("Finding schools..."):
                result = _cached_search(data_dir, request)
            set_latest_search(st.session_state, result)
        except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
            search_failed = True
            st.error(str(exc))

    result = get_latest_search(st.session_state)
    if result is not None:
        _render_results(result, detail_page)
    elif not submitted and not search_failed:
        st.info("Enter a postcode in the sidebar to get started.")


def _render_detail_table(rows: list[dict[str, str]], empty_message: str) -> None:
    if not rows:
        st.info(empty_message)
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _render_trends(
    history: pd.DataFrame | None,
    domain: str,
    *,
    heading: str = "Trends",
    error: str | None = None,
) -> None:
    st.markdown(f"#### {heading}")
    if error:
        st.caption(f"Trend data unavailable: {error}")
        return
    if history is None or history.empty:
        st.caption("No historical data is currently available for this area.")
        return

    metrics = available_trend_metrics(history, domain)
    if not metrics:
        st.caption("There are not yet two comparable published years for this area.")
        return

    default_metric = DEFAULT_TREND_METRIC.get(domain)
    index = metrics.index(default_metric) if default_metric in metrics else 0
    metric = st.selectbox(
        "Metric",
        metrics,
        index=index,
        format_func=lambda value: TREND_METRIC_LABELS[domain][value],
        key=f"trend-metric-{domain}",
    )

    all_years = trend_frame(history, domain, metric)
    year_count = len(all_years)
    period_options: list[int | None] = [
        years for years in (3, 5, 10) if year_count > years
    ]
    period_options.append(None)
    period = None
    if len(period_options) > 1:
        period = st.selectbox(
            "Period",
            period_options,
            index=0,
            format_func=lambda value: (
                "All available" if value is None else f"Last {value} years"
            ),
            key=f"trend-period-{domain}",
        )

    chart = trend_frame(history, domain, metric, years=period)
    if chart.empty or len(chart) < 2:
        st.caption("There are not yet two comparable published years for this metric.")
        return

    series = [column for column in chart.columns if column != "Year"]
    st.line_chart(chart, x="Year", y=series, width="stretch")
    if len(series) > 1:
        st.caption("School, local-authority and England trends are shown where the benchmark is comparable.")
    note = trend_lineage_note(history, domain, metric)
    if note:
        st.caption(note)


def _render_overview(school: SchoolResult) -> None:
    website = normalise_website(school.identity.website)
    if website:
        st.markdown(f"[School website]({website})")
    _render_detail_table(overview_rows(school), "No school information is currently available.")


def _render_academics(
    school: SchoolResult,
    benchmarks,
    history: pd.DataFrame | None = None,
    history_error: str | None = None,
) -> None:
    if school.academics.data_year:
        st.caption(f"Performance data: {school.academics.data_year}")
    if school.academics.progress8_year and school.academics.progress8_year != school.academics.data_year:
        st.caption(f"Progress 8 uses the latest valid published cohort: {school.academics.progress8_year}.")
    _render_detail_table(
        academic_rows(school, benchmarks),
        "No academic performance data is currently available for this school.",
    )
    _render_trends(history, "academics", error=history_error)


def _render_subjects(school: SchoolResult) -> None:
    data_dir = os.environ.get("SCHOOL_FINDER_DATA_DIR", str(DEFAULT_DATA_DIR))
    try:
        subjects = _cached_subjects(data_dir, school.identity.urn)
    except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
        st.warning(f"Subject-level results are unavailable: {exc}")
        return
    _render_detail_table(
        subject_rows(subjects),
        "No subject-level KS4 results are currently available for this school.",
    )


def _render_ofsted(school: SchoolResult) -> None:
    rows = inspection_rows(school)
    _render_detail_table(rows, "No Ofsted inspection detail is currently available for this school.")
    inspection = school.inspection
    if inspection.equivalent_rating and not inspection.rating:
        explanation = inspection.equivalent_explanation or (
            "No official overall effectiveness grade is published for this inspection. "
            "School Finder derives an equivalent from Ofsted's published judgements."
        )
        st.info(explanation)
    elif inspection.equivalent_rating and inspection.equivalent_rating != inspection.rating:
        st.caption("The School Finder equivalent is shown separately from the official overall grade.")
    if inspection.source_school_name and inspection.source_school_name != school.identity.name:
        st.caption(
            f"Inspection data source: {inspection.source_school_name}"
            + (f" (URN {inspection.source_urn})" if inspection.source_urn else "")
            + "."
        )


def _render_pastoral_behaviour(
    school: SchoolResult,
    benchmarks,
    history: pd.DataFrame | None = None,
    history_error: str | None = None,
) -> None:
    st.subheader("Parent View")
    _render_detail_table(
        pastoral_rows(school),
        "No usable Ofsted Parent View data is currently available for this school.",
    )
    note = pastoral_note(school)
    if note:
        st.caption(note)
    if school.pastoral.survey_year:
        st.caption(f"Parent View survey year: {school.pastoral.survey_year}")
    if school.pastoral.source_url:
        st.markdown(f"[Parent View source]({school.pastoral.source_url})")

    st.subheader("Attendance")
    if school.attendance.data_year:
        st.caption(f"Attendance data: {school.attendance.data_year}")
    _render_detail_table(
        attendance_rows(school, benchmarks),
        "No attendance data is currently available for this school.",
    )
    _render_trends(
        history,
        "attendance",
        heading="Attendance trends",
        error=history_error,
    )

    st.subheader("Suspensions & exclusions")
    if school.behaviour.data_year:
        st.caption(f"Behaviour data: {school.behaviour.data_year}")
    _render_detail_table(
        behaviour_rows(school, benchmarks),
        "No suspension or exclusion data is currently available for this school.",
    )
    _render_trends(
        history,
        "behaviour",
        heading="Behaviour trends",
        error=history_error,
    )


def _render_staffing(
    school: SchoolResult,
    benchmarks,
    history: pd.DataFrame | None = None,
    history_error: str | None = None,
) -> None:
    if school.workforce.data_year:
        st.caption(f"Workforce data: {school.workforce.data_year}")
    st.subheader("Ratios")
    _render_detail_table(
        workforce_ratio_rows(school, benchmarks),
        "No staffing ratios are currently available for this school.",
    )
    st.subheader("Workforce")
    _render_detail_table(
        workforce_rows(school),
        "No workforce totals are currently available for this school.",
    )
    _render_trends(history, "workforce", error=history_error)


def _render_destinations(
    school: SchoolResult,
    benchmarks,
    history: pd.DataFrame | None = None,
    history_error: str | None = None,
) -> None:
    destination = school.destinations
    if destination.destination_year:
        cohort = f" for {destination.leaver_year} leavers" if destination.leaver_year else ""
        st.caption(f"Destination data: {destination.destination_year}{cohort}")
    _render_detail_table(
        destination_rows(school, benchmarks),
        "No destination data is currently available for this school.",
    )
    _render_trends(history, "destinations", error=history_error)


def _detail_page(search_page=None) -> None:
    """Render the selected school using the latest in-session search result."""
    result = get_latest_search(st.session_state)
    selected_urn = get_selected_school_urn(st.session_state)
    school = find_school(result, selected_urn)

    if school is None:
        st.title("School detail")
        st.info("Choose a school from your search results to view its full detail.")
        if result is None:
            st.caption("Your latest successful search will remain available while this session is open.")
        if search_page is not None and st.button("← Back to find schools"):
            st.switch_page(search_page)
        return

    if search_page is not None and st.button("← Back to results"):
        st.switch_page(search_page)

    st.title(school.identity.name)
    details = [
        school.identity.sector,
        school.identity.age_range,
        school.identity.gender,
        school.identity.faith_status,
        school.location.local_authority_name,
    ]
    st.caption(" • ".join(value for value in details if value))

    metrics = st.columns(3)
    metrics[0].metric("Distance", format_distance(school.travel.distance_miles), help=MEASURE_HELP["Distance"])
    match_value = school.preference_score.overall if school.preference_score else None
    metrics[1].metric("Match", format_match_score(match_value), help=MEASURE_HELP["Match"])
    metrics[2].metric("Ofsted", ofsted_display(school), help=MEASURE_HELP["Ofsted"])

    if school.preference_score and school.preference_score.coverage_pct < 100:
        st.caption(
            f"Match score uses {school.preference_score.coverage_pct:.0f}% of the requested preference data."
        )

    benchmarks = relevant_benchmarks(school, result.benchmarks)
    if benchmarks:
        st.caption("Benchmark columns use the matching local authority and England where available.")

    data_dir = os.environ.get("SCHOOL_FINDER_DATA_DIR", str(DEFAULT_DATA_DIR))
    history = None
    history_error = None
    try:
        history = _cached_history(
            data_dir,
            school.identity.urn,
            school.location.local_authority_code,
        )
    except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
        history_error = str(exc)

    tabs = st.tabs(
        [
            "Overview",
            "Academics",
            "Subjects",
            "Ofsted",
            "Pastoral & behaviour",
            "Staffing",
            "Destinations",
        ]
    )
    with tabs[0]:
        _render_overview(school)
    with tabs[1]:
        _render_academics(school, benchmarks, history, history_error)
    with tabs[2]:
        _render_subjects(school)
    with tabs[3]:
        _render_ofsted(school)
    with tabs[4]:
        _render_pastoral_behaviour(school, benchmarks, history, history_error)
    with tabs[5]:
        _render_staffing(school, benchmarks, history, history_error)
    with tabs[6]:
        _render_destinations(school, benchmarks, history, history_error)


def main() -> None:
    if st is None:
        raise ImportError(
            "Streamlit is not installed. Install School Finder with the web extra: "
            "python -m pip install -e \".[web]\""
        )

    st.set_page_config(page_title="School Finder", page_icon="🏫", layout="wide")

    pages = {}
    search_page = st.Page(
        lambda: _search_page(pages["detail"]),
        title="Find schools",
        icon="🔎",
        url_path="find-schools",
        default=True,
    )
    detail_page = st.Page(
        lambda: _detail_page(pages["search"]),
        title="School detail",
        icon="🏫",
        url_path="school-detail",
    )
    pages.update(search=search_page, detail=detail_page)

    navigation = st.navigation([search_page, detail_page])
    navigation.run()

    st.markdown("---")
    st.caption("Built by Craig Wilkinson using public DfE, Ofsted and ONS data.")


if __name__ == "__main__":
    main()
