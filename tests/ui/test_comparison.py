from dataclasses import replace

from school_finder.models.school import (
    AcademicPerformance,
    AttendanceStatistics,
    BehaviourStatistics,
    DestinationStatistics,
    PastoralCareStatistics,
    SchoolIdentity,
    SchoolResult,
    TravelInformation,
    WorkforceStatistics,
)
from school_finder.models.scoring import SchoolScore
from school_finder.ui.comparison import COMPARISON_SECTIONS, comparison_rows, selected_schools


def _school(urn: str, name: str, *, attainment: float | None, distance: float | None, match: float | None):
    return SchoolResult(
        identity=SchoolIdentity(urn, name, sector="State-funded", age_range="11–16", gender="Mixed", faith_status="Non-faith"),
        academics=AcademicPerformance(attainment8=attainment, progress8=0.2, english_maths_grade5_pct=60),
        pastoral=PastoralCareStatistics(score=75, response_count=50, happy_pct=80, safe_pct=90, recommend_pct=85),
        attendance=AttendanceStatistics(overall_absence_pct=6, persistent_absence_pct=12),
        behaviour=BehaviourStatistics(suspension_rate=4, permanent_exclusion_rate=0.1),
        workforce=WorkforceStatistics(pupil_teacher_ratio=16, pupil_qualified_teacher_ratio=17, part_time_teacher_pct=20),
        destinations=DestinationStatistics(sustained_destination_pct=94, education_pct=80, apprenticeship_pct=8, employment_pct=6),
        travel=TravelInformation(distance_miles=distance),
        preference_score=SchoolScore(match, 100, ()) if match is not None else None,
    )


def test_selected_schools_preserves_requested_order_and_ignores_missing():
    a = _school("1", "A", attainment=50, distance=2, match=80)
    b = _school("2", "B", attainment=55, distance=1, match=90)
    assert selected_schools((a, b), ("2", "missing", "1")) == (b, a)


def test_comparison_rows_format_and_mark_best_values():
    a = _school("1", "A", attainment=50, distance=2, match=80)
    b = _school("2", "B", attainment=55, distance=1, match=90)

    overview = comparison_rows((a, b), COMPARISON_SECTIONS[0])
    assert overview[0] == {"Measure": "Distance", "A": "2.0 mi", "B": "★ 1.0 mi"}
    assert overview[1]["B"].startswith("★ ")
    assert overview[2]["A"] == "—"

    academics = comparison_rows((a, b), COMPARISON_SECTIONS[1])
    assert academics[0]["B"].startswith("★ 55")


def test_comparison_rows_handles_missing_and_joint_best():
    a = _school("1", "A", attainment=None, distance=None, match=None)
    b = _school("2", "B", attainment=None, distance=None, match=None)
    staffing = comparison_rows((a, b), COMPARISON_SECTIONS[3])
    assert staffing[0]["A"].startswith("★ ")

    academics = comparison_rows((a, b), COMPARISON_SECTIONS[1])
    assert academics[0]["A"] == "—"
    assert academics[0]["B"] == "—"


def test_comparison_text_formatter_handles_blank_values():
    school = _school("1", "A", attainment=50, distance=1, match=80)
    school = replace(school, identity=replace(school.identity, sector="  "))
    overview = comparison_rows((school,), COMPARISON_SECTIONS[0])
    assert overview[3]["A"] == "—"
