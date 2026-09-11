from datetime import date
import math

from school_finder.models.school import (
    AcademicPerformance,
    AttendanceStatistics,
    BehaviourStatistics,
    PastoralCareStatistics,
    SchoolBenchmarks,
    SchoolIdentity,
    SchoolLocation,
    SchoolResult,
    TravelInformation,
    WorkforceStatistics,
)
from school_finder.ui.formatting import (
    MISSING,
    benchmark_comparisons,
    benchmark_for_school,
    benchmark_rows,
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


def _school(**kwargs):
    return SchoolResult(
        identity=SchoolIdentity("1", "Example", website=kwargs.get("website")),
        location=SchoolLocation(local_authority_code=kwargs.get("la_code", "E10000014")),
        academics=AcademicPerformance(
            attainment8=kwargs.get("attainment8", 52.0),
            english_maths_grade5_pct=kwargs.get("grade5", 60.0),
            progress8=kwargs.get("progress8", 0.21),
        ),
        pastoral=kwargs.get("pastoral", PastoralCareStatistics(score=72.0, response_count=50)),
        attendance=AttendanceStatistics(overall_absence_pct=kwargs.get("absence", 6.0)),
        behaviour=BehaviourStatistics(suspension_rate=kwargs.get("suspensions", 4.0)),
        workforce=WorkforceStatistics(pupil_teacher_ratio=kwargs.get("ratio", 16.2)),
        travel=TravelInformation(distance_miles=kwargs.get("distance", 1.24)),
    )


def _benchmark(level="Local authority", code="E10000014", label="Hampshire"):
    return SchoolBenchmarks(
        label=label,
        level=level,
        code=code,
        academics=AcademicPerformance(attainment8=48.0, progress8=0.0, english_maths_grade5_pct=50.0),
        attendance=AttendanceStatistics(overall_absence_pct=7.0, persistent_absence_pct=20.0),
        behaviour=BehaviourStatistics(suspension_rate=5.0),
        workforce=WorkforceStatistics(pupil_teacher_ratio=17.0),
    )


def test_number_formatters_hide_missing_values():
    assert format_number(None) == MISSING
    assert format_number(math.nan) == MISSING
    assert format_number(12.345, decimals=2) == "12.35"
    assert format_percent(51.2) == "51.2%"
    assert format_percent(None) == MISSING
    assert format_progress8(0.125) == "+0.12"
    assert format_progress8(-0.2) == "-0.20"
    assert format_progress8(None) == MISSING
    assert format_distance(1.24) == "1.2 mi"
    assert format_distance(None) == MISSING
    assert format_match_score(82.36) == "82.4"
    assert format_match_score(None) == MISSING
    assert format_ratio(16.25) == "16.2:1"
    assert format_ratio(None) == MISSING


def test_website_normalisation():
    assert normalise_website(None) is None
    assert normalise_website("   ") is None
    assert normalise_website("school.example") == "https://school.example"
    assert normalise_website("https://school.example") == "https://school.example"
    assert normalise_website("http://school.example") == "http://school.example"


def test_ofsted_display_prefers_equivalent_then_official(monkeypatch):
    school = _school()
    object.__setattr__(school.inspection, "rating", "Good")
    assert ofsted_display(school) == "Good"
    object.__setattr__(school.inspection, "equivalent_rating", "Outstanding")
    assert ofsted_display(school) == "Outstanding"
    object.__setattr__(school.inspection, "equivalent_rating", None)
    object.__setattr__(school.inspection, "rating", None)
    assert ofsted_display(school) == MISSING


def test_pastoral_note_explains_score_and_missing_data():
    assert pastoral_note(_school()) == "Based on 50 Parent View responses."
    assert pastoral_note(_school(pastoral=PastoralCareStatistics(score=70))) is None
    assert pastoral_note(_school(pastoral=PastoralCareStatistics(response_count=5))) == (
        "Insufficient Parent View responses (5) for a score."
    )
    assert pastoral_note(_school(pastoral=PastoralCareStatistics())) == (
        "No usable Parent View score is currently available."
    )


def test_benchmark_selection_prefers_matching_local_authority_then_national():
    school = _school()
    england = _benchmark(level="National", code="E92000001", label="England")
    hampshire = _benchmark()
    assert benchmark_for_school(school, (england, hampshire)) is hampshire
    no_local = _school(la_code="E99999999")
    assert benchmark_for_school(no_local, (england, hampshire)) is england
    no_local_code = _school(la_code=None)
    assert benchmark_for_school(no_local_code, (england, hampshire)) is england
    assert benchmark_for_school(no_local, ()) is None


def test_benchmark_comparisons_describe_better_worse_and_equal():
    school = _school(attainment8=52, absence=6, suspensions=6)
    benchmark = _benchmark()
    comparisons = benchmark_comparisons(school, benchmark)
    assert comparisons == (
        "Attainment 8 4.0 better",
        "Absence 1.0pp better",
        "Suspensions 1.0 worse",
    )

    equal = _school(attainment8=48.02, absence=7.01, suspensions=5.0)
    assert benchmark_comparisons(equal, benchmark) == (
        "Attainment 8 about the same",
        "Absence about the same",
        "Suspensions about the same",
    )
    missing = _school(attainment8=None)
    assert benchmark_comparisons(missing, benchmark) == (
        "Absence 1.0pp better",
        "Suspensions 1.0 better",
    )
    assert benchmark_comparisons(school, None) == ()


def test_benchmark_rows_formats_table_values():
    rows = benchmark_rows((_benchmark(),))
    assert rows == [
        {
            "Area": "Hampshire",
            "Attainment 8": "48.0",
            "Progress 8": "+0.00",
            "Grade 5+ E&M": "50.0%",
            "Absence": "7.0%",
            "Persistent absence": "20.0%",
            "Suspension rate": "5.0",
            "Pupil/teacher": "17.0:1",
        }
    ]
