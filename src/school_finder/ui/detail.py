"""Pure helpers for the Streamlit school detail view."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import re
from typing import Callable

import pandas as pd

from school_finder.models.school import SchoolBenchmarks, SchoolResult, SubjectResult
from school_finder.models.search import SchoolSearchResult
from school_finder.ui.formatting import (
    MISSING,
    format_number,
    format_percent,
    format_progress8,
    format_ratio,
)

Formatter = Callable[[float | int | None], str]
Accessor = Callable[[SchoolResult | SchoolBenchmarks], float | int | None]


def find_school(result: SchoolSearchResult | None, urn: str | None) -> SchoolResult | None:
    """Find one school from the latest search without introducing another data lookup."""
    if result is None or not urn:
        return None
    return next((school for school in result.schools if school.identity.urn == urn), None)


def relevant_benchmarks(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> tuple[SchoolBenchmarks, ...]:
    """Return the matching local-authority benchmark followed by England, when available."""
    benchmark_list = tuple(benchmarks)
    selected: list[SchoolBenchmarks] = []
    local_code = school.location.local_authority_code
    if local_code:
        local = next(
            (
                benchmark
                for benchmark in benchmark_list
                if (benchmark.level or "").casefold() == "local authority"
                and benchmark.code == local_code
            ),
            None,
        )
        if local is not None:
            selected.append(local)

    national = next(
        (
            benchmark
            for benchmark in benchmark_list
            if (benchmark.level or "").casefold() == "national"
        ),
        None,
    )
    if national is not None:
        selected.append(national)
    return tuple(selected)


def format_integer(value: int | float | None) -> str:
    if value is None:
        return MISSING
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MISSING
    if number != number or number in (float("inf"), float("-inf")):
        return MISSING
    return f"{number:,.0f}"


def format_date(value: date | None) -> str:
    if value is None:
        return MISSING
    return f"{value.day} {value.strftime('%B %Y')}"


def school_address(school: SchoolResult) -> str:
    parts = [school.location.address, school.location.town, school.location.postcode]
    return ", ".join(part.strip() for part in parts if part and part.strip()) or MISSING


def overview_rows(school: SchoolResult) -> list[dict[str, str]]:
    """Return stable school identity/contact rows for display."""
    identity = school.identity
    location = school.location
    values = (
        ("URN", identity.urn or MISSING),
        ("Address", school_address(school)),
        ("Local authority", location.local_authority_name or MISSING),
        ("School type", identity.establishment_type or identity.sector or MISSING),
        ("Sector", identity.sector or MISSING),
        ("Phase", identity.phase or MISSING),
        ("Age range", identity.age_range or MISSING),
        ("Gender", identity.gender or MISSING),
        ("Faith", identity.faith_status or MISSING),
        ("Religious character", identity.religious_character or MISSING),
        ("Religious ethos", identity.religious_ethos or MISSING),
        ("Telephone", identity.telephone or MISSING),
    )
    return [{"Field": label, "Value": value} for label, value in values]


def _comparison_rows(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
    measures: Iterable[tuple[str, Accessor, Formatter]],
) -> list[dict[str, str]]:
    benchmark_list = tuple(benchmarks)
    rows: list[dict[str, str]] = []
    for label, accessor, formatter in measures:
        row = {"Measure": label, "School": formatter(accessor(school))}
        for benchmark in benchmark_list:
            row[benchmark.label] = formatter(accessor(benchmark))
        if any(value != MISSING for key, value in row.items() if key != "Measure"):
            rows.append(row)
    return rows


def academic_rows(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> list[dict[str, str]]:
    return _comparison_rows(
        school,
        benchmarks,
        (
            ("Pupil count", lambda item: item.academics.pupil_count, format_integer),
            ("Attainment 8", lambda item: item.academics.attainment8, format_number),
            ("Attainment 8 – English", lambda item: item.academics.attainment8_english, format_number),
            ("Attainment 8 – Maths", lambda item: item.academics.attainment8_maths, format_number),
            ("Attainment 8 – EBacc", lambda item: item.academics.attainment8_ebacc, format_number),
            ("Attainment 8 – Open", lambda item: item.academics.attainment8_open, format_number),
            ("Progress 8", lambda item: item.academics.progress8, format_progress8),
            ("Progress 8 – English", lambda item: item.academics.progress8_english, format_progress8),
            ("Progress 8 – Maths", lambda item: item.academics.progress8_maths, format_progress8),
            ("Progress 8 – EBacc", lambda item: item.academics.progress8_ebacc, format_progress8),
            ("Progress 8 – Open", lambda item: item.academics.progress8_open, format_progress8),
            (
                "English & Maths Grade 5+",
                lambda item: item.academics.english_maths_grade5_pct,
                format_percent,
            ),
            (
                "English & Maths Grade 4+",
                lambda item: item.academics.english_maths_grade4_pct,
                format_percent,
            ),
            ("EBacc APS", lambda item: item.academics.ebacc_aps, format_number),
            ("EBacc entry", lambda item: item.academics.ebacc_entry_pct, format_percent),
            ("EBacc Grade 5+", lambda item: item.academics.ebacc_grade5_pct, format_percent),
            ("EBacc Grade 4+", lambda item: item.academics.ebacc_grade4_pct, format_percent),
            (
                "Triple science entry",
                lambda item: item.academics.triple_science_entry_pct,
                format_percent,
            ),
            (
                "Multiple languages entry",
                lambda item: item.academics.multiple_languages_entry_pct,
                format_percent,
            ),
            (
                "GCSE entries per pupil",
                lambda item: item.academics.gcse_entries_per_pupil,
                format_number,
            ),
            (
                "Qualification entries per pupil",
                lambda item: item.academics.qualification_entries_per_pupil,
                format_number,
            ),
        ),
    )


def attendance_rows(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> list[dict[str, str]]:
    return _comparison_rows(
        school,
        benchmarks,
        (
            ("Overall absence", lambda item: item.attendance.overall_absence_pct, format_percent),
            ("Authorised absence", lambda item: item.attendance.authorised_absence_pct, format_percent),
            ("Unauthorised absence", lambda item: item.attendance.unauthorised_absence_pct, format_percent),
            ("Persistent absence", lambda item: item.attendance.persistent_absence_pct, format_percent),
            ("Severe absence", lambda item: item.attendance.severe_absence_pct, format_percent),
        ),
    )


def behaviour_rows(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> list[dict[str, str]]:
    return _comparison_rows(
        school,
        benchmarks,
        (
            ("Suspension rate", lambda item: item.behaviour.suspension_rate, format_number),
            (
                "Pupils with 1+ suspension",
                lambda item: item.behaviour.pupils_with_one_or_more_suspension_rate,
                format_percent,
            ),
            (
                "Permanent exclusion rate",
                lambda item: item.behaviour.permanent_exclusion_rate,
                format_number,
            ),
        ),
    )


def workforce_ratio_rows(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> list[dict[str, str]]:
    return _comparison_rows(
        school,
        benchmarks,
        (
            (
                "Pupils per qualified teacher",
                lambda item: item.workforce.pupil_qualified_teacher_ratio,
                format_ratio,
            ),
            ("Pupils per teacher", lambda item: item.workforce.pupil_teacher_ratio, format_ratio),
            ("Pupils per adult", lambda item: item.workforce.pupil_adult_ratio, format_ratio),
            (
                "Part-time teachers",
                lambda item: item.workforce.part_time_teacher_pct,
                format_percent,
            ),
        ),
    )


def workforce_rows(school: SchoolResult) -> list[dict[str, str]]:
    workforce = school.workforce
    values = (
        ("Pupils (FTE)", workforce.pupil_fte),
        ("Teachers (FTE)", workforce.teacher_fte),
        ("Qualified teachers (FTE)", workforce.qualified_teacher_fte),
        ("Classroom teachers (FTE)", workforce.classroom_teacher_fte),
        ("Teaching assistants (FTE)", workforce.teaching_assistant_fte),
        ("Support staff (FTE)", workforce.support_staff_fte),
        ("Teachers without QTS (FTE)", workforce.teachers_without_qts_fte),
    )
    return [
        {"Measure": label, "School": format_number(value, decimals=1)}
        for label, value in values
        if value is not None
    ]


def destination_rows(
    school: SchoolResult,
    benchmarks: Iterable[SchoolBenchmarks],
) -> list[dict[str, str]]:
    return _comparison_rows(
        school,
        benchmarks,
        (
            (
                "Sustained destination",
                lambda item: item.destinations.sustained_destination_pct,
                format_percent,
            ),
            ("Education", lambda item: item.destinations.education_pct, format_percent),
            ("Apprenticeship", lambda item: item.destinations.apprenticeship_pct, format_percent),
            ("Employment", lambda item: item.destinations.employment_pct, format_percent),
            ("Not sustained", lambda item: item.destinations.not_sustained_pct, format_percent),
            ("Unknown", lambda item: item.destinations.unknown_pct, format_percent),
        ),
    )


def pastoral_rows(school: SchoolResult) -> list[dict[str, str]]:
    pastoral = school.pastoral
    values: tuple[tuple[str, str], ...] = (
        ("Pastoral care score", format_number(pastoral.score)),
        ("Parent View responses", format_integer(pastoral.response_count)),
        ("Happy", format_percent(pastoral.happy_pct)),
        ("Feels safe", format_percent(pastoral.safe_pct)),
        ("Behaviour is positive", format_percent(pastoral.behaviour_positive_pct)),
        ("Bullying dealt with", format_percent(pastoral.bullying_dealt_with_pct)),
        ("SEND support", format_percent(pastoral.send_support_pct)),
        ("Communication", format_percent(pastoral.communication_pct)),
        ("Concerns dealt with", format_percent(pastoral.concerns_dealt_with_pct)),
        ("Best interests", format_percent(pastoral.best_interests_pct)),
        ("Learning support", format_percent(pastoral.learning_support_pct)),
        ("Personal development", format_percent(pastoral.personal_development_pct)),
        ("Would recommend", format_percent(pastoral.recommend_pct)),
    )
    return [
        {"Measure": label, "School": value}
        for label, value in values
        if value != MISSING
    ]


def inspection_rows(school: SchoolResult) -> list[dict[str, str]]:
    inspection = school.inspection
    values = (
        ("Official overall grade", inspection.rating or MISSING),
        ("School Finder equivalent", inspection.equivalent_rating or MISSING),
        ("Inspection date", format_date(inspection.inspection_date)),
        ("Publication date", format_date(inspection.publication_date)),
        ("Safeguarding", inspection.safeguarding or MISSING),
        ("Inclusion", inspection.inclusion or MISSING),
        ("Curriculum & teaching", inspection.curriculum_teaching or MISSING),
        ("Achievement", inspection.achievement or MISSING),
        ("Attendance & behaviour", inspection.attendance_behaviour or MISSING),
        ("Personal development", inspection.personal_development or MISSING),
        ("Leadership", inspection.leadership or MISSING),
    )
    return [
        {"Judgement": label, "Outcome": value}
        for label, value in values
        if value != MISSING
    ]


def subject_rows(subjects: Iterable[SubjectResult]) -> list[dict[str, str]]:
    """Format subject-level KS4 results for a compact detail table."""
    rows: list[dict[str, str]] = []
    for subject in sorted(
        subjects,
        key=lambda item: ((item.subject or "").casefold(), (item.qualification or "").casefold()),
    ):
        rows.append(
            {
                "Subject": subject.subject or MISSING,
                "Qualification": subject.qualification or MISSING,
                "Entries": format_integer(subject.entries),
                "Grade 4+": format_percent(subject.grade4_plus_pct),
                "Grade 5+": format_percent(subject.grade5_plus_pct),
                "Grade 7+": format_percent(subject.grade7_plus_pct),
                "Year": subject.data_year or MISSING,
            }
        )
    return rows


TREND_METRIC_LABELS: dict[str, dict[str, str]] = {
    "academics": {
        "pupil_count": "Pupil count",
        "attainment8": "Attainment 8",
        "attainment8_english": "Attainment 8 – English",
        "attainment8_maths": "Attainment 8 – Maths",
        "attainment8_ebacc": "Attainment 8 – EBacc",
        "attainment8_open": "Attainment 8 – Open",
        "progress8_pupil_count": "Progress 8 pupil count",
        "progress8": "Progress 8",
        "progress8_english": "Progress 8 – English",
        "progress8_maths": "Progress 8 – Maths",
        "progress8_ebacc": "Progress 8 – EBacc",
        "progress8_open": "Progress 8 – Open",
        "english_maths_grade5_pct": "English & Maths Grade 5+",
        "english_maths_grade4_pct": "English & Maths Grade 4+",
        "ebacc_entry_pct": "EBacc entry",
        "ebacc_grade5_pct": "EBacc Grade 5+",
        "ebacc_grade4_pct": "EBacc Grade 4+",
        "ebacc_aps": "EBacc APS",
        "triple_science_entry_pct": "Triple science entry",
        "multiple_languages_entry_pct": "Multiple languages entry",
        "gcse_entries_per_pupil": "GCSE entries per pupil",
        "qualification_entries_per_pupil": "Qualification entries per pupil",
    },
    "attendance": {
        "attendance_enrolments": "Enrolments",
        "overall_absence_pct": "Overall absence",
        "authorised_absence_pct": "Authorised absence",
        "unauthorised_absence_pct": "Unauthorised absence",
        "persistent_absence_pct": "Persistent absence",
        "severe_absence_pct": "Severe absence",
    },
    "behaviour": {
        "behaviour_pupil_headcount": "Pupil headcount",
        "suspension_count": "Suspensions",
        "suspension_rate": "Suspension rate",
        "pupils_with_one_or_more_suspension": "Pupils with one or more suspensions",
        "pupils_with_one_or_more_suspension_rate": "Pupils with one or more suspensions rate",
        "permanent_exclusion_count": "Permanent exclusions",
        "permanent_exclusion_rate": "Permanent exclusion rate",
    },
    "workforce": {
        "pupil_fte": "Pupils (FTE)",
        "teacher_fte": "Teachers (FTE)",
        "qualified_teacher_fte": "Qualified teachers (FTE)",
        "classroom_teacher_fte": "Classroom teachers (FTE)",
        "teaching_assistant_fte": "Teaching assistants (FTE)",
        "support_staff_fte": "Support staff (FTE)",
        "teachers_without_qts_fte": "Teachers without QTS (FTE)",
        "part_time_teacher_pct": "Part-time teachers",
        "pupil_qualified_teacher_ratio": "Pupils per qualified teacher",
        "pupil_teacher_ratio": "Pupils per teacher",
        "pupil_adult_ratio": "Pupils per adult",
    },
    "destinations": {
        "destination_pupil_count": "Destination cohort",
        "sustained_destination_pct": "Sustained destination",
        "education_destination_pct": "Education destination",
        "apprenticeship_destination_pct": "Apprenticeship destination",
        "employment_destination_pct": "Employment destination",
        "not_sustained_destination_pct": "Not sustained",
        "unknown_destination_pct": "Unknown destination",
    },
}

DEFAULT_TREND_METRIC = {
    "academics": "attainment8",
    "attendance": "overall_absence_pct",
    "behaviour": "suspension_rate",
    "workforce": "pupil_teacher_ratio",
    "destinations": "sustained_destination_pct",
}

# Aggregate counts/FTE totals are not comparable with a single school. Rates,
# ratios and attainment measures are suitable for LA/England overlays.
BENCHMARK_TREND_METRICS = {
    "attainment8",
    "attainment8_english",
    "attainment8_maths",
    "attainment8_ebacc",
    "attainment8_open",
    "progress8",
    "progress8_english",
    "progress8_maths",
    "progress8_ebacc",
    "progress8_open",
    "english_maths_grade5_pct",
    "english_maths_grade4_pct",
    "ebacc_entry_pct",
    "ebacc_grade5_pct",
    "ebacc_grade4_pct",
    "ebacc_aps",
    "triple_science_entry_pct",
    "multiple_languages_entry_pct",
    "gcse_entries_per_pupil",
    "qualification_entries_per_pupil",
    "overall_absence_pct",
    "authorised_absence_pct",
    "unauthorised_absence_pct",
    "persistent_absence_pct",
    "severe_absence_pct",
    "suspension_rate",
    "pupils_with_one_or_more_suspension_rate",
    "permanent_exclusion_rate",
    "part_time_teacher_pct",
    "pupil_qualified_teacher_ratio",
    "pupil_teacher_ratio",
    "pupil_adult_ratio",
    "sustained_destination_pct",
    "education_destination_pct",
    "apprenticeship_destination_pct",
    "employment_destination_pct",
    "not_sustained_destination_pct",
    "unknown_destination_pct",
}


def history_year_key(value: object) -> int | None:
    """Return a sortable key for compact/slash academic years or calendar years."""
    text = str(value or "").strip()
    compact = re.fullmatch(r"(\d{4})(\d{2})", text)
    if compact:
        return int(f"{compact.group(1)}{compact.group(2)}")
    slash = re.fullmatch(r"(\d{4})/(\d{2})", text)
    if slash:
        return int(f"{slash.group(1)}{slash.group(2)}")
    calendar = re.fullmatch(r"\d{4}", text)
    if calendar:
        return int(text)
    return None


def format_history_year(value: object) -> str:
    """Render DfE compact academic years as 2024/25 while preserving other labels."""
    text = str(value or "").strip()
    compact = re.fullmatch(r"(\d{4})(\d{2})", text)
    if compact:
        return f"{compact.group(1)}/{compact.group(2)}"
    return text


def available_trend_metrics(history: pd.DataFrame, domain: str) -> tuple[str, ...]:
    """Return known metrics with at least two school observations in the domain."""
    labels = TREND_METRIC_LABELS.get(domain, {})
    if history.empty or not labels:
        return ()
    school = history[
        history["domain"].eq(domain) & history["series"].eq("School")
    ].copy()
    if school.empty:
        return ()
    available: list[str] = []
    for metric in labels:
        rows = school[school["metric"].eq(metric)]
        keys = {history_year_key(value) for value in rows["year"]}
        keys.discard(None)
        if len(keys) >= 2:
            available.append(metric)
    return tuple(available)


def trend_frame(
    history: pd.DataFrame,
    domain: str,
    metric: str,
    *,
    years: int | None = None,
) -> pd.DataFrame:
    """Return a chronological wide frame suitable for Streamlit line charts.

    The x-axis is based on every published school year in the domain rather than
    only years where the selected metric has a value. This preserves genuine
    publication gaps (for example Progress 8) instead of visually joining two
    non-adjacent observations as though the missing year had data.
    """
    if history.empty:
        return pd.DataFrame()

    domain_school = history[
        history["domain"].eq(domain) & history["series"].eq("School")
    ].copy()
    if domain_school.empty:
        return pd.DataFrame()
    domain_school["_year_key"] = domain_school["year"].map(history_year_key)
    domain_school = domain_school[domain_school["_year_key"].notna()].copy()
    if domain_school.empty:
        return pd.DataFrame()

    school_keys = sorted(domain_school["_year_key"].astype(int).unique())
    if years is not None and years > 0:
        school_keys = school_keys[-years:]

    work = history[
        history["domain"].eq(domain) & history["metric"].eq(metric)
    ].copy()
    if work.empty:
        return pd.DataFrame()
    if metric not in BENCHMARK_TREND_METRICS:
        work = work[work["series"].eq("School")].copy()

    work["_year_key"] = work["year"].map(history_year_key)
    work = work[work["_year_key"].notna() & work["_year_key"].isin(school_keys)].copy()
    if work.empty:
        return pd.DataFrame()

    labels_by_key: dict[int, str] = {}
    for key in school_keys:
        school_year = domain_school.loc[
            domain_school["_year_key"].eq(key), "year"
        ]
        value = school_year.iloc[-1] if not school_year.empty else str(key)
        labels_by_key[int(key)] = format_history_year(value)

    pivot = work.pivot_table(
        index="_year_key",
        columns="series",
        values="value",
        aggfunc="last",
    ).reindex(school_keys)
    series_order = [name for name in ("School",) if name in pivot.columns]
    series_order.extend(sorted(name for name in pivot.columns if name != "School"))
    pivot = pivot[series_order].reset_index()
    pivot.insert(0, "Year", pivot["_year_key"].map(labels_by_key))
    return pivot.drop(columns="_year_key")


def trend_lineage_note(history: pd.DataFrame, domain: str, metric: str) -> str | None:
    """Explain when a trend includes values inherited from predecessor schools."""
    if history.empty:
        return None
    rows = history[
        history["domain"].eq(domain)
        & history["metric"].eq(metric)
        & history["series"].eq("School")
        & history["source_kind"].eq("predecessor")
    ]
    names = sorted(
        {
            str(value).strip()
            for value in rows["source_school_name"].dropna()
            if str(value).strip()
        }
    )
    if not names:
        return None
    if len(names) == 1:
        return f"Includes historical data from predecessor school: {names[0]}."
    return "Includes historical data from predecessor schools: " + ", ".join(names) + "."
