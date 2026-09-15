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
from school_finder.models.personalisation import SchoolDisposition
from school_finder.models.school import SchoolResult
from school_finder.models.search import SchoolSearchResult
from school_finder.services.history import get_school_history
from school_finder.services.search import get_schools_by_urn, search_schools
from school_finder.services.subjects import get_school_subject_results
from school_finder.ui.browser_storage import run_storage_command
from school_finder.ui.comparison import COMPARISON_SECTIONS, comparison_rows, selected_schools
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
    admissions_rows,
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
from school_finder.ui.personalisation_storage import (
    enable_persistence,
    forget_persistence,
    handle_storage_response,
    is_persistence_enabled,
    is_persistence_hydrated,
    is_persistence_synced,
    next_storage_command,
    persistence_warning,
)
from school_finder.ui.match import (
    comparison_match_rows,
    match_breakdown_rows,
    preference_profile,
    priorities_summary,
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
    MAX_COMPARE_SCHOOLS,
    add_compare_school,
    clear_all_personalisation,
    clear_compare_schools,
    get_compare_urns,
    get_latest_search,
    get_personal_school,
    get_personalised_urns,
    get_rejected_urns,
    get_shortlisted_urns,
    get_selected_school_urn,
    remove_compare_school,
    select_school,
    set_school_disposition,
    set_school_notes,
    set_school_rating,
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

_CLEAR_PERSONALISATION_CONFIRM_KEY = "school_finder.clear_personalisation_confirm"


def _render_personal_disposition(urn: str, *, key_prefix: str) -> None:
    """Render shortlist / not-for-us controls for one school."""
    personal = get_personal_school(st.session_state, urn)
    disposition = personal.disposition

    if disposition is SchoolDisposition.SHORTLISTED:
        st.caption("♥ Shortlisted")
    elif disposition is SchoolDisposition.NOT_FOR_US:
        st.caption('🚫 Marked "Not for us"')

    shortlisted = disposition is SchoolDisposition.SHORTLISTED
    not_for_us = disposition is SchoolDisposition.NOT_FOR_US
    actions = st.columns(2)
    if actions[0].button(
        "♥ Shortlisted" if shortlisted else "♡ Shortlist",
        key=f"{key_prefix}-shortlist-{urn}",
        type="primary" if shortlisted else "secondary",
    ):
        set_school_disposition(
            st.session_state,
            urn,
            SchoolDisposition.NEUTRAL if shortlisted else SchoolDisposition.SHORTLISTED,
        )
        st.rerun()
        return

    if actions[1].button(
        "✓ Not for us" if not_for_us else "Not for us",
        key=f"{key_prefix}-not-for-us-{urn}",
        type="primary" if not_for_us else "secondary",
    ):
        set_school_disposition(
            st.session_state,
            urn,
            SchoolDisposition.NEUTRAL if not_for_us else SchoolDisposition.NOT_FOR_US,
        )
        st.rerun()


def _rating_display(rating: int | None) -> str:
    """Return a compact five-star display for a saved personal rating."""
    if rating is None:
        return "Not rated"
    return f"{'★' * rating}{'☆' * (5 - rating)} ({rating}/5)"


def _render_personal_summary(urn: str) -> None:
    """Render any saved rating and note for a school."""
    personal = get_personal_school(st.session_state, urn)
    if personal.rating is not None:
        st.caption(f"My rating: {_rating_display(personal.rating)}")
    if personal.notes:
        preview = personal.notes if len(personal.notes) <= 180 else f"{personal.notes[:177]}..."
        st.caption(f"My notes: {preview}")


def _render_match_explanation(
    school: SchoolResult, result: SchoolSearchResult | None
) -> None:
    """Explain how the selected preference score was calculated."""
    score = school.preference_score
    preferences = result.request.preferences if result is not None else None
    if score is None or preferences is None:
        st.info("No preference score is available for this search.")
        return

    metrics = st.columns(2)
    metrics[0].metric("Match score", format_match_score(score.overall), help=MEASURE_HELP["Match"])
    metrics[1].metric("Data coverage", format_percent(score.coverage_pct, decimals=0))

    st.caption(f"Your priorities: {preference_profile(preferences)}")
    st.caption(priorities_summary(preferences))

    if score.coverage_pct < 100:
        st.info(
            f"{score.coverage_pct:.0f}% of your requested preference data was available. "
            "Missing measures are excluded and their weighting is redistributed across the "
            "available measures."
        )

    rows = match_breakdown_rows(score)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No contributing preference measures are available for this school.")

    st.caption(
        "Most component scores compare this school with the other schools in your current "
        "search. Ofsted and pastoral care use fixed scoring scales. The contribution column "
        "shows how much each available measure adds to the overall match score."
    )


def _comparison_personal_rows(schools: tuple[SchoolResult, ...]) -> list[dict[str, str]]:
    """Build the personal-state summary shown at the top of Compare."""
    rows = [
        {"My view": "Status"},
        {"My view": "My rating"},
        {"My view": "Match"},
        {"My view": "Match coverage"},
    ]
    for school in schools:
        personal = get_personal_school(st.session_state, school.identity.urn)
        status = {
            SchoolDisposition.NEUTRAL: "—",
            SchoolDisposition.SHORTLISTED: "♥ Shortlisted",
            SchoolDisposition.NOT_FOR_US: "🚫 Not for us",
        }[personal.disposition]
        score = school.preference_score
        rows[0][school.identity.name] = status
        rows[1][school.identity.name] = _rating_display(personal.rating)
        rows[2][school.identity.name] = format_match_score(score.overall if score else None)
        rows[3][school.identity.name] = (
            format_percent(score.coverage_pct, decimals=0) if score else "—"
        )
    return rows


def _personal_storage_caption() -> str:
    """Return context-sensitive copy for personal ratings and notes."""
    if is_persistence_enabled(st.session_state):
        return (
            "Saved in this browser when you save your view. Clear the rating or notes and "
            "save again to remove them."
        )
    return (
        "Saved for this Streamlit session only. Use My schools → Remember my schools on "
        "this device if you want to keep personalisation between visits."
    )


def _render_personal_view(urn: str) -> None:
    """Render the editable personal rating and notes for one school."""
    personal = get_personal_school(st.session_state, urn)
    rating_options = (None, 1, 2, 3, 4, 5)
    rating = st.selectbox(
        "My rating",
        rating_options,
        index=rating_options.index(personal.rating),
        format_func=_rating_display,
        key=f"personal-rating-{urn}",
    )
    notes = st.text_area(
        "Notes",
        value=personal.notes or "",
        placeholder="Add anything you want to remember about this school...",
        key=f"personal-notes-{urn}",
        height=180,
    )
    st.caption(_personal_storage_caption())
    if st.button("Save my view", key=f"personal-save-{urn}", type="primary"):
        set_school_rating(st.session_state, urn, rating)
        set_school_notes(st.session_state, urn, notes)
        st.rerun()


def _sync_personalisation_storage() -> None:
    """Run at most one localStorage operation required by the current session."""
    command = next_storage_command(st.session_state)
    if command is None:
        return
    try:
        response = run_storage_command(st, command)
    except RuntimeError:
        response = {
            "action": command.action,
            "request_id": command.request_id,
            "ok": False,
        }
    handle_storage_response(st.session_state, response)


def _render_personalisation_storage_controls() -> None:
    """Render explicit opt-in/forget controls for browser persistence."""
    st.subheader("Remember my schools")
    warning = persistence_warning(st.session_state)
    if warning:
        st.warning(warning)

    if not is_persistence_hydrated(st.session_state):
        st.caption("Checking this browser for previously saved schools…")
        return

    if is_persistence_enabled(st.session_state):
        if is_persistence_synced(st.session_state):
            st.caption("✓ Your shortlist, ratings and notes are saved on this device.")
        else:
            st.caption("Saving your shortlist, ratings and notes on this device…")
        st.caption(
            "This information stays in this browser and is not synced to another device or account. "
            "Anyone using this browser profile may be able to see saved notes."
        )
        if st.button("Forget saved personalisation", key="forget-personalisation"):
            forget_persistence(st.session_state)
            st.rerun()
            return
        _render_clear_all_personalisation_control()
        return

    st.caption(
        "By default your shortlist, ratings and notes are available only for this Streamlit session."
    )
    st.caption(
        "Choose to remember them and School Finder will store only this personal school state in "
        "this browser. It is not synced to an account or another device."
    )
    if st.button(
        "Remember my schools on this device",
        key="remember-personalisation",
        type="primary",
    ):
        enable_persistence(st.session_state)
        st.rerun()
        return
    _render_clear_all_personalisation_control()


def _render_clear_all_personalisation_control() -> None:
    """Offer a confirmed destructive reset of all personal school state."""
    if not get_personalised_urns(st.session_state):
        st.session_state.pop(_CLEAR_PERSONALISATION_CONFIRM_KEY, None)
        return

    st.markdown("#### Clear personalisation")
    if st.session_state.get(_CLEAR_PERSONALISATION_CONFIRM_KEY) is not True:
        st.caption(
            "Remove every shortlist decision, rating and note from this session and any "
            "saved browser copy."
        )
        if st.button("Clear all personalisation", key="clear-all-personalisation"):
            st.session_state[_CLEAR_PERSONALISATION_CONFIRM_KEY] = True
            st.rerun()
        return

    st.warning(
        "This will permanently remove all shortlist / not-for-us decisions, ratings and "
        "notes from this session and this browser."
    )
    actions = st.columns(2)
    if actions[0].button(
        "Yes, clear everything",
        key="confirm-clear-all-personalisation",
        type="primary",
    ):
        clear_all_personalisation(st.session_state)
        forget_persistence(st.session_state)
        st.session_state.pop(_CLEAR_PERSONALISATION_CONFIRM_KEY, None)
        st.rerun()
        return
    if actions[1].button(
        "Cancel",
        key="cancel-clear-all-personalisation",
    ):
        st.session_state.pop(_CLEAR_PERSONALISATION_CONFIRM_KEY, None)
        st.rerun()


def _cached_search_impl(data_dir: str, request):
    return search_schools(Path(data_dir), request)


def _cached_subjects_impl(data_dir: str, urn: str):
    return get_school_subject_results(Path(data_dir), urn)


def _cached_history_impl(data_dir: str, urn: str, local_authority_code: str | None):
    return get_school_history(Path(data_dir), urn, local_authority_code)


def _cached_schools_by_urn_impl(data_dir: str, urns: tuple[str, ...]):
    return get_schools_by_urn(Path(data_dir), urns)


if st is not None:
    _cached_search = st.cache_data(ttl=900, show_spinner=False)(_cached_search_impl)
    _cached_subjects = st.cache_data(ttl=900, show_spinner=False)(_cached_subjects_impl)
    _cached_history = st.cache_data(ttl=900, show_spinner=False)(_cached_history_impl)
    _cached_schools_by_urn = st.cache_data(ttl=60, show_spinner=False)(
        _cached_schools_by_urn_impl
    )
else:
    _cached_search = _cached_search_impl
    _cached_subjects = _cached_subjects_impl
    _cached_history = _cached_history_impl
    _cached_schools_by_urn = _cached_schools_by_urn_impl


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
    compare_page=None,
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
        if school.admissions.demand_band:
            demand = f"Admissions demand: {school.admissions.demand_band}"
            if school.admissions.first_preferences_per_offer is not None:
                demand += f" • {school.admissions.first_preferences_per_offer:.2f} first preferences per offer"
            if school.admissions.data_year:
                demand += f" ({school.admissions.data_year} entry)"
            st.caption(demand)

        _render_personal_disposition(
            school.identity.urn,
            key_prefix="school",
        )

        benchmark = benchmark_for_school(school, result.benchmarks)
        comparisons = benchmark_comparisons(school, benchmark)
        if benchmark and comparisons:
            st.caption(f"Compared with {benchmark.label}: " + " • ".join(comparisons))

        actions = st.columns(2)
        if detail_page is not None and actions[0].button(
            "View details",
            key=f"school-details-{school.identity.urn}",
        ):
            select_school(st.session_state, school.identity.urn)
            st.switch_page(detail_page)

        compare_urns = get_compare_urns(st.session_state)
        in_compare = school.identity.urn in compare_urns
        label = "Remove from compare" if in_compare else "Add to compare"
        if actions[1].button(label, key=f"school-compare-{school.identity.urn}"):
            if in_compare:
                remove_compare_school(st.session_state, school.identity.urn)
                st.rerun()
            else:
                try:
                    add_compare_school(st.session_state, school.identity.urn)
                except ValueError as exc:
                    st.warning(str(exc))
                else:
                    st.rerun()


def _render_results(
    result: SchoolSearchResult,
    detail_page=None,
    compare_page=None,
    my_schools_page=None,
) -> None:
    if not result.postcode.is_current:
        detail = f" ({result.postcode.termination_date})" if result.postcode.termination_date else ""
        st.warning(f"The supplied postcode is marked as terminated{detail}; using its last known coordinates.")

    if not result.schools:
        st.info("No schools matched the search criteria.")
        return

    st.subheader(f"Found {len(result.schools)} schools")
    if result.request.preferences is not None:
        st.caption("Schools are ranked using your selected preferences. Missing data is not treated as zero.")

    personalised_count = len(get_personalised_urns(st.session_state))
    if my_schools_page is not None and st.button(
        f"My schools ({personalised_count})",
        key="open-my-schools",
    ):
        st.switch_page(my_schools_page)

    compare_urns = get_compare_urns(st.session_state)
    if compare_page is not None and len(compare_urns) >= 2:
        if st.button(f"Compare selected ({len(compare_urns)})", type="primary"):
            st.switch_page(compare_page)
    elif compare_urns:
        st.caption(f"Select at least 2 schools to compare ({len(compare_urns)}/{MAX_COMPARE_SCHOOLS} selected).")

    for index, school in enumerate(result.schools, start=1):
        _render_school_card(index, school, result, detail_page, compare_page)

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


def _search_page(detail_page=None, compare_page=None, my_schools_page=None) -> None:
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
        _render_results(result, detail_page, compare_page, my_schools_page)
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


def _render_admissions(
    school: SchoolResult,
    history: pd.DataFrame | None = None,
    history_error: str | None = None,
) -> None:
    admissions = school.admissions
    if admissions.data_year:
        st.caption(f"Admissions data: {admissions.data_year} entry")
    _render_detail_table(
        admissions_rows(school),
        "No school-level applications and offers data is currently available for this school.",
    )
    if admissions.demand_band:
        st.info(
            "Admissions demand is based on first preferences per total offer and shows "
            "historical demand relative to other secondary schools in the same entry year. "
            "It is not a probability of admission."
        )
    else:
        st.caption(
            "Applications and offers describe historical demand, not a child's chance of admission. "
            "Published admissions criteria and the applicant cohort still determine offers."
        )
    if admissions.source_school_name and admissions.source_school_name != school.identity.name:
        st.caption(
            f"Admissions history source: {admissions.source_school_name}"
            + (f" (URN {admissions.source_urn})" if admissions.source_urn else "")
            + "."
        )
    _render_trends(
        history,
        "admissions",
        heading="Admissions demand trends",
        error=history_error,
    )


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


def _detail_page(search_page=None, compare_page=None) -> None:
    """Render the selected school, reloading saved schools from the canonical dataset."""
    result = get_latest_search(st.session_state)
    selected_urn = get_selected_school_urn(st.session_state)
    school = find_school(result, selected_urn)
    dynamic_error = None

    if school is None and selected_urn:
        data_dir = os.environ.get("SCHOOL_FINDER_DATA_DIR", str(DEFAULT_DATA_DIR))
        try:
            loaded = _cached_schools_by_urn(data_dir, (selected_urn,))
        except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
            dynamic_error = str(exc)
        else:
            if loaded:
                school = loaded[0]

    if school is None:
        st.title("School detail")
        if dynamic_error:
            st.warning(f"Could not reload the selected school: {dynamic_error}")
        elif selected_urn:
            st.info(
                f"URN {selected_urn} could not be found in the current School Finder dataset. "
                "The school may have closed or changed URN."
            )
        else:
            st.info("Choose a school from your search results or My schools to view its full detail.")
        if result is None:
            st.caption("Your latest successful search will remain available while this session is open.")
        if search_page is not None and st.button("← Back to find schools"):
            st.switch_page(search_page)
        return

    if search_page is not None and st.button("← Back to results"):
        st.switch_page(search_page)

    search_school = find_school(result, school.identity.urn)
    if search_school is not None:
        compare_urns = get_compare_urns(st.session_state)
        in_compare = school.identity.urn in compare_urns
        action_columns = st.columns(2)
        if action_columns[0].button(
            "Remove from compare" if in_compare else "Add to compare",
            key=f"detail-compare-{school.identity.urn}",
        ):
            if in_compare:
                remove_compare_school(st.session_state, school.identity.urn)
                st.rerun()
            else:
                try:
                    add_compare_school(st.session_state, school.identity.urn)
                except ValueError as exc:
                    st.warning(str(exc))
                else:
                    st.rerun()
        if compare_page is not None and len(get_compare_urns(st.session_state)) >= 2:
            if action_columns[1].button("Compare selected", key="detail-open-compare"):
                st.switch_page(compare_page)
    else:
        st.caption(
            "This school was reloaded from the current dataset. Run a search containing it "
            "to calculate distance/match and add it to a comparison."
        )

    st.title(school.identity.name)
    details = [
        school.identity.sector,
        school.identity.age_range,
        school.identity.gender,
        school.identity.faith_status,
        school.location.local_authority_name,
    ]
    st.caption(" • ".join(value for value in details if value))

    _render_personal_disposition(
        school.identity.urn,
        key_prefix="detail",
    )

    metrics = st.columns(3)
    metrics[0].metric("Distance", format_distance(school.travel.distance_miles), help=MEASURE_HELP["Distance"])
    match_value = school.preference_score.overall if school.preference_score else None
    metrics[1].metric("Match", format_match_score(match_value), help=MEASURE_HELP["Match"])
    metrics[2].metric("Ofsted", ofsted_display(school), help=MEASURE_HELP["Ofsted"])

    if school.preference_score and school.preference_score.coverage_pct < 100:
        st.caption(
            f"Match score uses {school.preference_score.coverage_pct:.0f}% of the requested preference data."
        )

    available_benchmarks = result.benchmarks if result is not None else ()
    benchmarks = relevant_benchmarks(school, available_benchmarks)
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
            "Admissions",
            "Academics",
            "Subjects",
            "Ofsted",
            "Pastoral & behaviour",
            "Staffing",
            "Destinations",
            "Why it matches",
            "My view",
        ]
    )
    with tabs[0]:
        _render_overview(school)
    with tabs[1]:
        _render_admissions(school, history, history_error)
    with tabs[2]:
        _render_academics(school, benchmarks, history, history_error)
    with tabs[3]:
        _render_subjects(school)
    with tabs[4]:
        _render_ofsted(school)
    with tabs[5]:
        _render_pastoral_behaviour(school, benchmarks, history, history_error)
    with tabs[6]:
        _render_staffing(school, benchmarks, history, history_error)
    with tabs[7]:
        _render_destinations(school, benchmarks, history, history_error)
    with tabs[8]:
        _render_match_explanation(school, result)
    with tabs[9]:
        _render_personal_view(school.identity.urn)

def _render_my_school_card(school: SchoolResult, *, detail_page=None) -> None:
    """Render one school saved in the personal shortlist/disposition state."""
    with st.container(border=True):
        st.markdown(f"### {school.identity.name}")
        details = [
            school.identity.sector,
            school.identity.age_range,
            school.identity.gender,
            school.location.local_authority_name,
        ]
        st.caption(" • ".join(value for value in details if value))

        metrics = st.columns(3)
        metrics[0].metric("Ofsted", ofsted_display(school), help=MEASURE_HELP["Ofsted"])
        metrics[1].metric(
            "Attainment 8",
            format_number(school.academics.attainment8),
            help=MEASURE_HELP["Attainment 8"],
        )
        match_value = school.preference_score.overall if school.preference_score else None
        metrics[2].metric("Match", format_match_score(match_value), help=MEASURE_HELP["Match"])

        _render_personal_summary(school.identity.urn)
        _render_personal_disposition(school.identity.urn, key_prefix="my-schools")
        if detail_page is not None and st.button(
            "View details",
            key=f"my-schools-details-{school.identity.urn}",
        ):
            select_school(st.session_state, school.identity.urn)
            st.switch_page(detail_page)


def _my_schools_page(search_page=None, detail_page=None) -> None:
    """Render saved schools using current details reloaded from the canonical dataset."""
    st.title("My schools")
    _render_personalisation_storage_controls()
    personalised = get_personalised_urns(st.session_state)
    shortlisted = get_shortlisted_urns(st.session_state)
    rejected = get_rejected_urns(st.session_state)
    disposition_urns = set((*shortlisted, *rejected))
    other = tuple(urn for urn in personalised if urn not in disposition_urns)

    if not personalised:
        st.info(
            "You haven't saved any schools yet. Search for schools and use Shortlist / "
            "Not for us, or add a rating or note from School detail."
        )
        if search_page is not None and st.button("← Find schools"):
            st.switch_page(search_page)
        return

    saved_urns = personalised
    result = get_latest_search(st.session_state)
    search_by_urn = (
        {school.identity.urn: school for school in result.schools}
        if result is not None
        else {}
    )

    # The latest search is the richest context for schools it already contains
    # (distance, match score, candidate-relative scoring). Only fall back to the
    # canonical dataset for saved schools that are outside that search.
    missing_urns = tuple(urn for urn in saved_urns if urn not in search_by_urn)
    loaded: tuple[SchoolResult, ...] = ()
    if missing_urns:
        data_dir = os.environ.get("SCHOOL_FINDER_DATA_DIR", str(DEFAULT_DATA_DIR))
        try:
            loaded = _cached_schools_by_urn(data_dir, missing_urns)
        except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
            st.warning(f"Could not reload current school details: {exc}")

    current_by_urn = {school.identity.urn: school for school in loaded}
    schools_by_urn: dict[str, SchoolResult] = {}
    for urn in saved_urns:
        search_school = search_by_urn.get(urn)
        if search_school is not None:
            schools_by_urn[urn] = search_school
            continue
        current = current_by_urn.get(urn)
        if current is not None:
            schools_by_urn[urn] = current

    def render_section(title: str, urns: tuple[str, ...], empty_message: str) -> None:
        st.subheader(f"{title} ({len(urns)})")
        if not urns:
            st.caption(empty_message)
            return
        for urn in urns:
            school = schools_by_urn.get(urn)
            if school is not None:
                _render_my_school_card(school, detail_page=detail_page)
                continue
            with st.container(border=True):
                st.markdown(f"### URN {urn}")
                st.caption(
                    "This school could not be found in the current School Finder dataset. "
                    "It may have closed or changed URN."
                )
                _render_personal_summary(urn)
                _render_personal_disposition(urn, key_prefix="my-schools-missing")

    render_section("Shortlisted", shortlisted, "No schools are currently shortlisted.")
    render_section("Not for us", rejected, 'No schools are currently marked "Not for us".')
    render_section(
        "Other saved schools",
        other,
        "No other schools currently have saved ratings or notes.",
    )

    if search_page is not None and st.button("← Back to find schools", key="my-schools-back"):
        st.switch_page(search_page)



def _compare_page(search_page=None, detail_page=None) -> None:
    """Render up to four schools side-by-side from the latest search."""
    result = get_latest_search(st.session_state)
    urns = get_compare_urns(st.session_state)
    schools = selected_schools(result.schools, urns) if result is not None else ()

    st.title("Compare schools")
    if result is None:
        st.info("Run a school search first, then add schools to compare.")
        if search_page is not None and st.button("← Find schools"):
            st.switch_page(search_page)
        return

    if len(schools) < 2:
        st.info("Choose at least two schools from your search results to compare.")
        if search_page is not None and st.button("← Back to results"):
            st.switch_page(search_page)
        return

    st.caption(
        f"Comparing {len(schools)} of a maximum of {MAX_COMPARE_SCHOOLS} schools. "
        "★ marks the strongest available value where higher/lower performance has a clear "
        "direction. Match scores reflect your selected priorities."
    )

    columns = st.columns(len(schools))
    for column, school in zip(columns, schools, strict=True):
        column.markdown(f"### {school.identity.name}")
        if detail_page is not None and column.button(
            "View details",
            key=f"compare-details-{school.identity.urn}",
        ):
            select_school(st.session_state, school.identity.urn)
            st.switch_page(detail_page)
        if column.button("Remove", key=f"compare-remove-{school.identity.urn}"):
            remove_compare_school(st.session_state, school.identity.urn)
            st.rerun()

    st.subheader("My view")
    st.dataframe(
        pd.DataFrame(_comparison_personal_rows(schools)),
        hide_index=True,
        width="stretch",
    )

    for section in COMPARISON_SECTIONS:
        st.subheader(section.title)
        st.dataframe(
            pd.DataFrame(comparison_rows(schools, section)),
            hide_index=True,
            width="stretch",
        )

    match_rows = comparison_match_rows(schools)
    if match_rows:
        st.subheader("Why they match your priorities")
        preferences = result.request.preferences
        if preferences is not None:
            st.caption(f"Your priorities: {preference_profile(preferences)}")
            st.caption(priorities_summary(preferences))
        st.dataframe(pd.DataFrame(match_rows), hide_index=True, width="stretch")
        st.caption(
            "Component scores show how each school performs for the priorities used by your "
            "latest search. Most are relative to the current search candidate set; — means the "
            "measure was unavailable."
        )
        for school in schools:
            score = school.preference_score
            if score is not None and score.coverage_pct < 100:
                st.caption(
                    f"{school.identity.name}: {score.coverage_pct:.0f}% match coverage; "
                    "available priorities were reweighted."
                )

    actions = st.columns(2)
    if search_page is not None and actions[0].button("← Back to results", key="compare-back"):
        st.switch_page(search_page)
    if actions[1].button("Clear comparison", key="compare-clear"):
        clear_compare_schools(st.session_state)
        if search_page is not None:
            st.switch_page(search_page)
        else:
            st.rerun()

def main() -> None:
    if st is None:
        raise ImportError(
            "Streamlit is not installed. Install School Finder with the web extra: "
            "python -m pip install -e \".[web]\""
        )

    st.set_page_config(page_title="School Finder", page_icon="🏫", layout="wide")
    _sync_personalisation_storage()

    pages = {}
    search_page = st.Page(
        lambda: _search_page(pages["detail"], pages["compare"], pages["my_schools"]),
        title="Find schools",
        icon="🔎",
        url_path="find-schools",
        default=True,
    )
    my_schools_page = st.Page(
        lambda: _my_schools_page(pages["search"], pages["detail"]),
        title="My schools",
        icon="♥️",
        url_path="my-schools",
    )
    compare_page = st.Page(
        lambda: _compare_page(pages["search"], pages["detail"]),
        title="Compare schools",
        icon="⚖️",
        url_path="compare-schools",
    )
    detail_page = st.Page(
        lambda: _detail_page(pages["search"], pages["compare"]),
        title="School detail",
        icon="🏫",
        url_path="school-detail",
    )
    pages.update(
        search=search_page,
        my_schools=my_schools_page,
        compare=compare_page,
        detail=detail_page,
    )

    navigation = st.navigation([search_page, my_schools_page, compare_page, detail_page])
    navigation.run()

    st.markdown("---")
    st.caption("Built by Craig Wilkinson using public DfE, Ofsted and ONS data.")


if __name__ == "__main__":
    main()
