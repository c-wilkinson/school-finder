"""Streamlit MVP for School Finder."""

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
from school_finder.services.search import search_schools
from school_finder.ui.controls import (
    CUSTOM_DEFAULT_WEIGHTS,
    PRESET_LABELS,
    SORT_LABELS,
    build_search_request,
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


if st is not None:
    _cached_search = st.cache_data(ttl=900, show_spinner=False)(_cached_search_impl)
else:
    _cached_search = _cached_search_impl


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

            submitted = st.form_submit_button("Find schools", type="primary", use_container_width=True)

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


def _render_school_card(index: int, school: SchoolResult, result: SchoolSearchResult) -> None:
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


def _render_results(result: SchoolSearchResult) -> None:
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
        _render_school_card(index, school, result)

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
            st.dataframe(pd.DataFrame(benchmark_rows(result.benchmarks)), hide_index=True, use_container_width=True)

    st.caption("Ofsted values may be School Finder equivalents where no official overall grade is available.")


def main() -> None:
    if st is None:
        raise ImportError(
            "Streamlit is not installed. Install School Finder with the web extra: "
            "python -m pip install -e \".[web]\""
        )

    st.set_page_config(page_title="School Finder", page_icon="🏫", layout="wide")
    st.title("School Finder")
    st.markdown(
        "Find, compare and rank secondary schools in England using public DfE, Ofsted and ONS data."
    )
    st.caption("Choose what matters to you, then School Finder ranks the schools that match your filters.")

    submitted, request = _sidebar_form()
    if not submitted:
        st.info("Enter a postcode in the sidebar to get started.")
    elif request is not None:
        data_dir = os.environ.get("SCHOOL_FINDER_DATA_DIR", str(DEFAULT_DATA_DIR))
        try:
            with st.spinner("Finding schools..."):
                result = _cached_search(data_dir, request)
            _render_results(result)
        except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
            st.error(str(exc))

    st.markdown("---")
    st.caption("Built by Craig Wilkinson using public DfE, Ofsted and ONS data.")


if __name__ == "__main__":
    main()
