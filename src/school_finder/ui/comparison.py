"""Pure helpers for side-by-side school comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from school_finder.models.school import SchoolResult
from school_finder.ui.formatting import (
    format_distance,
    format_match_score,
    format_number,
    format_percent,
    format_progress8,
    format_ratio,
    ofsted_display,
)

MISSING = "—"


@dataclass(frozen=True, slots=True)
class ComparisonMetric:
    """Definition of one comparable school measure."""

    label: str
    value: Callable[[SchoolResult], object]
    formatter: Callable[[object], str]
    higher_is_better: bool | None = None


@dataclass(frozen=True, slots=True)
class ComparisonSection:
    """A named group of comparison metrics."""

    title: str
    metrics: tuple[ComparisonMetric, ...]


def _identity_value(attribute: str) -> Callable[[SchoolResult], object]:
    return lambda school: getattr(school.identity, attribute)


def _format_text(value: object) -> str:
    text = str(value).strip() if value is not None else ""
    return text or MISSING


def _format_ofsted(value: object) -> str:
    return ofsted_display(value)  # type: ignore[arg-type]


def _match_value(school: SchoolResult) -> float | None:
    return school.preference_score.overall if school.preference_score else None


COMPARISON_SECTIONS: tuple[ComparisonSection, ...] = (
    ComparisonSection(
        "Overview",
        (
            ComparisonMetric("Distance", lambda s: s.travel.distance_miles, format_distance, False),
            ComparisonMetric("Match", _match_value, format_match_score, True),
            ComparisonMetric("Ofsted", lambda s: s, _format_ofsted),
            ComparisonMetric("Sector", _identity_value("sector"), _format_text),
            ComparisonMetric("Age range", _identity_value("age_range"), _format_text),
            ComparisonMetric("Gender", _identity_value("gender"), _format_text),
            ComparisonMetric("Faith", _identity_value("faith_status"), _format_text),
        ),
    ),
    ComparisonSection(
        "Academics",
        (
            ComparisonMetric("Attainment 8", lambda s: s.academics.attainment8, format_number, True),
            ComparisonMetric("Progress 8", lambda s: s.academics.progress8, format_progress8, True),
            ComparisonMetric("English & Maths Grade 5+", lambda s: s.academics.english_maths_grade5_pct, format_percent, True),
            ComparisonMetric("English & Maths Grade 4+", lambda s: s.academics.english_maths_grade4_pct, format_percent, True),
            ComparisonMetric("EBacc APS", lambda s: s.academics.ebacc_aps, format_number, True),
            ComparisonMetric("EBacc entry", lambda s: s.academics.ebacc_entry_pct, format_percent, True),
            ComparisonMetric("Triple science entry", lambda s: s.academics.triple_science_entry_pct, format_percent, True),
        ),
    ),
    ComparisonSection(
        "Pastoral & behaviour",
        (
            ComparisonMetric("Pastoral care", lambda s: s.pastoral.score, format_number, True),
            ComparisonMetric("Parent View responses", lambda s: s.pastoral.response_count, lambda value: format_number(value, decimals=0)),
            ComparisonMetric("Happy", lambda s: s.pastoral.happy_pct, format_percent, True),
            ComparisonMetric("Safe", lambda s: s.pastoral.safe_pct, format_percent, True),
            ComparisonMetric("Recommend", lambda s: s.pastoral.recommend_pct, format_percent, True),
            ComparisonMetric("Overall absence", lambda s: s.attendance.overall_absence_pct, format_percent, False),
            ComparisonMetric("Persistent absence", lambda s: s.attendance.persistent_absence_pct, format_percent, False),
            ComparisonMetric("Suspension rate", lambda s: s.behaviour.suspension_rate, format_number, False),
            ComparisonMetric("Permanent exclusion rate", lambda s: s.behaviour.permanent_exclusion_rate, format_number, False),
        ),
    ),
    ComparisonSection(
        "Staffing",
        (
            ComparisonMetric("Pupils per teacher", lambda s: s.workforce.pupil_teacher_ratio, format_ratio, False),
            ComparisonMetric("Pupils per qualified teacher", lambda s: s.workforce.pupil_qualified_teacher_ratio, format_ratio, False),
            ComparisonMetric("Part-time teachers", lambda s: s.workforce.part_time_teacher_pct, format_percent),
        ),
    ),
    ComparisonSection(
        "Destinations",
        (
            ComparisonMetric("Sustained destination", lambda s: s.destinations.sustained_destination_pct, format_percent, True),
            ComparisonMetric("Education destination", lambda s: s.destinations.education_pct, format_percent, True),
            ComparisonMetric("Apprenticeship destination", lambda s: s.destinations.apprenticeship_pct, format_percent, True),
            ComparisonMetric("Employment destination", lambda s: s.destinations.employment_pct, format_percent, True),
        ),
    ),
)


def selected_schools(schools: tuple[SchoolResult, ...], urns: tuple[str, ...]) -> tuple[SchoolResult, ...]:
    """Return selected schools in the user's comparison order."""
    by_urn = {school.identity.urn: school for school in schools}
    return tuple(by_urn[urn] for urn in urns if urn in by_urn)


def comparison_rows(
    schools: tuple[SchoolResult, ...],
    section: ComparisonSection,
) -> list[dict[str, str]]:
    """Build display-ready rows, marking the unique/joint best numeric values."""
    rows: list[dict[str, str]] = []
    for metric in section.metrics:
        raw = [metric.value(school) for school in schools]
        best: float | None = None
        if metric.higher_is_better is not None:
            numeric = [float(value) for value in raw if isinstance(value, (int, float))]
            if numeric:
                best = max(numeric) if metric.higher_is_better else min(numeric)

        row = {"Measure": metric.label}
        for school, value in zip(schools, raw, strict=True):
            rendered = metric.formatter(value)
            if best is not None and isinstance(value, (int, float)) and float(value) == best:
                rendered = f"★ {rendered}"
            row[school.identity.name] = rendered
        rows.append(row)
    return rows
