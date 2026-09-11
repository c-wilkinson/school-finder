"""Formatting and benchmark helpers shared by Streamlit views."""

from __future__ import annotations

import math
from typing import Iterable

from school_finder.models.school import SchoolBenchmarks, SchoolResult

MISSING = "—"

MEASURE_HELP: dict[str, str] = {
    "Distance": (
        "Straight-line distance from the supplied postcode using ONS postcode coordinates. "
        "It is not road distance or journey time."
    ),
    "Match": (
        "School Finder's preference score based on the weights you selected. It is not an "
        "official school rating. Missing metrics are reweighted across the data that is available."
    ),
    "Ofsted": (
        "The latest official overall Ofsted grade where available. If an overall grade is not "
        "published, School Finder may show a clearly identified equivalent derived from Ofsted's "
        "published inspection judgements."
    ),
    "Attainment 8": (
        "Average pupil achievement across eight GCSE-level qualification slots. English and maths "
        "are weighted more heavily. Higher scores mean stronger overall attainment."
    ),
    "Progress 8": (
        "How much progress pupils made from the end of primary school to GCSEs compared with pupils "
        "nationally who had similar prior attainment. 0 is broadly average; +0.5 is roughly half a "
        "grade better per subject and -0.5 roughly half a grade lower. The latest published historic "
        "year is used when recent cohorts do not have a valid KS2 baseline."
    ),
    "Grade 5+ E&M": (
        "Percentage of pupils achieving grade 5 or above in both English and maths GCSEs."
    ),
    "English & Maths Grade 5+": (
        "Percentage of pupils achieving grade 5 or above in both English and maths GCSEs."
    ),
    "EBacc APS": (
        "English Baccalaureate average point score across the EBacc subject areas: English, maths, "
        "sciences, a language, and history or geography. Higher is better."
    ),
    "EBacc entry": (
        "Percentage of pupils entered for the English Baccalaureate combination of English, maths, "
        "sciences, a language, and history or geography."
    ),
    "EBacc Grade 5+": (
        "Percentage of pupils achieving the English Baccalaureate at grade 5 or above."
    ),
    "Triple science entry": (
        "Percentage of pupils entered for biology, chemistry and physics as separate sciences."
    ),
    "Pastoral care": (
        "School Finder's 0-100 pastoral score derived from Ofsted Parent View responses. It is not an "
        "Ofsted rating. A score is not shown when there are too few usable responses."
    ),
    "Parent View responses": (
        "Number of Ofsted Parent View responses behind the pastoral data shown for the school."
    ),
    "Absence": (
        "Percentage of possible school sessions missed by pupils. Lower is generally better."
    ),
    "Persistent absence": (
        "Percentage of enrolments where the pupil missed 10% or more of their possible school "
        "sessions. Lower is generally better."
    ),
    "Suspension rate": (
        "Number of suspensions per 100 pupils. A pupil can be suspended more than once, so this is "
        "not the percentage of pupils who were suspended. Lower is generally better."
    ),
    "Permanent exclusion rate": (
        "Number of permanent exclusions per 100 pupils. Lower is generally better."
    ),
    "Pupil/teacher": (
        "Number of pupils per full-time-equivalent teacher. A lower ratio means fewer pupils per "
        "teacher on average, but it is not the same as average class size."
    ),
    "Sustained destination": (
        "Percentage of KS4 leavers recorded in sustained education, an apprenticeship or employment "
        "in the year after leaving school."
    ),
    "Pupil count": (
        "Number of pupils included in the school's Key Stage 4 performance cohort."
    ),
}



def _number(value: float | int | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def format_number(value: float | int | None, *, decimals: int = 1) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    return f"{number:.{decimals}f}"


def format_percent(value: float | int | None, *, decimals: int = 1) -> str:
    formatted = format_number(value, decimals=decimals)
    return MISSING if formatted == MISSING else f"{formatted}%"


def format_progress8(value: float | None) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    return f"{number:+.2f}"


def format_distance(value: float | None) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    return f"{number:.1f} mi"


def format_match_score(value: float | None) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    return f"{number:.1f}"


def format_ratio(value: float | None) -> str:
    number = _number(value)
    if number is None:
        return MISSING
    return f"{number:.1f}:1"


def normalise_website(value: str | None) -> str | None:
    if value is None:
        return None
    website = value.strip()
    if not website:
        return None
    if website.startswith(("http://", "https://")):
        return website
    return f"https://{website}"


def ofsted_display(school: SchoolResult) -> str:
    return school.inspection.equivalent_rating or school.inspection.rating or MISSING


def pastoral_note(school: SchoolResult) -> str | None:
    pastoral = school.pastoral
    if pastoral.score is not None:
        if pastoral.response_count is None:
            return None
        return f"Based on {pastoral.response_count} Parent View responses."
    if pastoral.response_count is not None and pastoral.response_count > 0:
        return f"Insufficient Parent View responses ({pastoral.response_count}) for a score."
    return "No usable Parent View score is currently available."


def benchmark_for_school(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> SchoolBenchmarks | None:
    benchmark_list = tuple(benchmarks)
    local_code = school.location.local_authority_code
    if local_code:
        for benchmark in benchmark_list:
            if (
                (benchmark.level or "").casefold() == "local authority"
                and benchmark.code == local_code
            ):
                return benchmark
    return next(
        (
            benchmark
            for benchmark in benchmark_list
            if (benchmark.level or "").casefold() == "national"
        ),
        None,
    )


def _difference_text(
    value: float | None,
    benchmark: float | None,
    *,
    label: str,
    unit: str = "",
    lower_is_better: bool = False,
) -> str | None:
    actual = _number(value)
    reference = _number(benchmark)
    if actual is None or reference is None:
        return None
    delta = actual - reference
    if abs(delta) < 0.05:
        return f"{label} about the same"
    better = delta < 0 if lower_is_better else delta > 0
    direction = "better" if better else "worse"
    magnitude = abs(delta)
    return f"{label} {magnitude:.1f}{unit} {direction}"


def benchmark_comparisons(
    school: SchoolResult,
    benchmark: SchoolBenchmarks | None,
) -> tuple[str, ...]:
    if benchmark is None:
        return ()
    comparisons = (
        _difference_text(
            school.academics.attainment8,
            benchmark.academics.attainment8,
            label="Attainment 8",
        ),
        _difference_text(
            school.attendance.overall_absence_pct,
            benchmark.attendance.overall_absence_pct,
            label="Absence",
            unit="pp",
            lower_is_better=True,
        ),
        _difference_text(
            school.behaviour.suspension_rate,
            benchmark.behaviour.suspension_rate,
            label="Suspensions",
            lower_is_better=True,
        ),
    )
    return tuple(value for value in comparisons if value is not None)


def benchmark_rows(benchmarks: Iterable[SchoolBenchmarks]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for benchmark in benchmarks:
        rows.append(
            {
                "Area": benchmark.label,
                "Attainment 8": format_number(benchmark.academics.attainment8),
                "Progress 8": format_progress8(benchmark.academics.progress8),
                "Grade 5+ E&M": format_percent(
                    benchmark.academics.english_maths_grade5_pct
                ),
                "Absence": format_percent(benchmark.attendance.overall_absence_pct),
                "Persistent absence": format_percent(
                    benchmark.attendance.persistent_absence_pct
                ),
                "Suspension rate": format_number(benchmark.behaviour.suspension_rate),
                "Pupil/teacher": format_ratio(benchmark.workforce.pupil_teacher_ratio),
            }
        )
    return rows
