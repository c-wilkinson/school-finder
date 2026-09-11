from datetime import date
import math

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
    WorkforceStatistics,
)
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult
from school_finder.ui.detail import (
    academic_rows,
    attendance_rows,
    behaviour_rows,
    destination_rows,
    find_school,
    format_date,
    format_integer,
    inspection_rows,
    overview_rows,
    pastoral_rows,
    relevant_benchmarks,
    school_address,
    subject_rows,
    workforce_ratio_rows,
    workforce_rows,
)
from school_finder.ui.formatting import MISSING


def _school() -> SchoolResult:
    return SchoolResult(
        identity=SchoolIdentity(
            "100001",
            "Example School",
            sector="State-funded",
            establishment_type="Academy converter",
            phase="Secondary",
            age_range="11–16",
            gender="Mixed",
            religious_character="None",
            religious_ethos="Does not apply",
            faith_status="Non-faith",
            telephone="01234 567890",
        ),
        location=SchoolLocation(
            address="1 School Lane",
            town="Basingstoke",
            postcode="RG00 1AA",
            local_authority_code="E10000014",
            local_authority_name="Hampshire",
        ),
        academics=AcademicPerformance(
            data_year="2024/25",
            pupil_count=180,
            attainment8=52,
            attainment8_english=10.5,
            attainment8_maths=10.1,
            attainment8_ebacc=16.2,
            attainment8_open=15.2,
            english_maths_grade5_pct=61,
            english_maths_grade4_pct=72,
            ebacc_entry_pct=38,
            ebacc_grade5_pct=25,
            ebacc_grade4_pct=31,
            ebacc_aps=4.7,
            triple_science_entry_pct=22,
            multiple_languages_entry_pct=8,
            gcse_entries_per_pupil=8.5,
            qualification_entries_per_pupil=9.1,
            progress8=0.2,
            progress8_english=0.1,
            progress8_maths=0.3,
            progress8_ebacc=0.25,
            progress8_open=0.15,
        ),
        inspection=InspectionSummary(
            rating="Good",
            equivalent_rating="Good",
            inspection_date=date(2025, 3, 4),
            publication_date=date(2025, 4, 5),
            safeguarding="Met",
            inclusion="Strong",
            curriculum_teaching="Good",
            achievement="Good",
            attendance_behaviour="Good",
            personal_development="Outstanding",
            leadership="Good",
        ),
        pastoral=PastoralCareStatistics(
            response_count=50,
            happy_pct=88,
            safe_pct=91,
            behaviour_positive_pct=79,
            bullying_dealt_with_pct=75,
            send_support_pct=72,
            communication_pct=81,
            concerns_dealt_with_pct=77,
            best_interests_pct=84,
            learning_support_pct=83,
            personal_development_pct=86,
            recommend_pct=89,
            score=84,
        ),
        attendance=AttendanceStatistics(
            overall_absence_pct=6,
            authorised_absence_pct=4,
            unauthorised_absence_pct=2,
            persistent_absence_pct=18,
            severe_absence_pct=2,
        ),
        behaviour=BehaviourStatistics(
            suspension_rate=4,
            pupils_with_one_or_more_suspension_rate=3,
            permanent_exclusion_rate=0.1,
        ),
        workforce=WorkforceStatistics(
            pupil_fte=1000,
            teacher_fte=60,
            qualified_teacher_fte=58,
            classroom_teacher_fte=55,
            teaching_assistant_fte=20,
            support_staff_fte=30,
            teachers_without_qts_fte=2,
            part_time_teacher_pct=18,
            pupil_qualified_teacher_ratio=17.2,
            pupil_teacher_ratio=16.7,
            pupil_adult_ratio=12.5,
        ),
        destinations=DestinationStatistics(
            sustained_destination_pct=94,
            education_pct=82,
            apprenticeship_pct=7,
            employment_pct=5,
            not_sustained_pct=4,
            unknown_pct=2,
        ),
    )


def _benchmark(label="Hampshire", level="Local authority", code="E10000014"):
    return SchoolBenchmarks(
        label=label,
        level=level,
        code=code,
        academics=AcademicPerformance(
            pupil_count=10000,
            attainment8=48,
            progress8=0,
            english_maths_grade5_pct=55,
        ),
        attendance=AttendanceStatistics(overall_absence_pct=7, persistent_absence_pct=20),
        behaviour=BehaviourStatistics(suspension_rate=5, permanent_exclusion_rate=0.2),
        workforce=WorkforceStatistics(pupil_teacher_ratio=17.5),
        destinations=DestinationStatistics(sustained_destination_pct=92),
    )


def _result(school=None):
    school = school or _school()
    return SchoolSearchResult(
        request=SchoolSearchRequest("RG00 1AA"),
        postcode=PostcodeLocation("RG00 1AA", 1, 2, True),
        schools=(school,),
    )


def test_find_school_and_relevant_benchmarks():
    school = _school()
    result = _result(school)
    assert find_school(result, school.identity.urn) is school
    assert find_school(result, "missing") is None
    assert find_school(None, school.identity.urn) is None
    assert find_school(result, None) is None

    england = _benchmark("England", "National", "E92000001")
    hampshire = _benchmark()
    other = _benchmark("Other", "Local authority", "E99999999")
    assert relevant_benchmarks(school, (england, other, hampshire)) == (hampshire, england)

    no_la = SchoolResult(identity=school.identity, location=SchoolLocation())
    assert relevant_benchmarks(no_la, (hampshire, england)) == (england,)
    assert relevant_benchmarks(no_la, ()) == ()


def test_scalar_detail_formatting_and_overview():
    school = _school()
    assert format_integer(1234) == "1,234"
    assert format_integer(None) == MISSING
    assert format_integer(math.nan) == MISSING
    assert format_integer("bad") == MISSING
    assert format_date(date(2025, 3, 4)) == "4 March 2025"
    assert format_date(None) == MISSING
    assert school_address(school) == "1 School Lane, Basingstoke, RG00 1AA"
    assert school_address(SchoolResult(identity=SchoolIdentity("1", "Empty"))) == MISSING

    rows = overview_rows(school)
    assert {"Field": "URN", "Value": "100001"} in rows
    assert {"Field": "School type", "Value": "Academy converter"} in rows
    assert {"Field": "Telephone", "Value": "01234 567890"} in rows


def test_comparison_row_builders_include_school_and_benchmarks_and_drop_empty_metrics():
    school = _school()
    benchmark = _benchmark()

    academics = academic_rows(school, (benchmark,))
    attainment = next(row for row in academics if row["Measure"] == "Attainment 8")
    assert attainment == {"Measure": "Attainment 8", "School": "52.0", "Hampshire": "48.0"}
    assert not any(row["Measure"] == "Progress 8 – Open" and row["School"] == MISSING for row in academics)

    attendance = attendance_rows(school, (benchmark,))
    assert next(row for row in attendance if row["Measure"] == "Overall absence")["School"] == "6.0%"

    behaviour = behaviour_rows(school, (benchmark,))
    assert next(row for row in behaviour if row["Measure"] == "Suspension rate")["Hampshire"] == "5.0"

    workforce_ratios = workforce_ratio_rows(school, (benchmark,))
    assert next(row for row in workforce_ratios if row["Measure"] == "Pupils per teacher")["School"] == "16.7:1"

    destinations = destination_rows(school, (benchmark,))
    assert next(row for row in destinations if row["Measure"] == "Sustained destination")["School"] == "94.0%"

    empty = SchoolResult(identity=SchoolIdentity("2", "Empty"))
    assert academic_rows(empty, ()) == []
    assert attendance_rows(empty, ()) == []
    assert behaviour_rows(empty, ()) == []
    assert workforce_ratio_rows(empty, ()) == []
    assert destination_rows(empty, ()) == []


def test_school_only_detail_rows():
    school = _school()
    workforce = workforce_rows(school)
    assert {"Measure": "Teachers (FTE)", "School": "60.0"} in workforce
    assert workforce_rows(SchoolResult(identity=SchoolIdentity("2", "Empty"))) == []

    pastoral = pastoral_rows(school)
    assert {"Measure": "Pastoral care score", "School": "84.0"} in pastoral
    assert {"Measure": "Would recommend", "School": "89.0%"} in pastoral
    assert pastoral_rows(SchoolResult(identity=SchoolIdentity("2", "Empty"))) == []

    inspection = inspection_rows(school)
    assert {"Judgement": "Official overall grade", "Outcome": "Good"} in inspection
    assert {"Judgement": "Inspection date", "Outcome": "4 March 2025"} in inspection
    assert inspection_rows(SchoolResult(identity=SchoolIdentity("2", "Empty"))) == []


def test_subject_rows_are_sorted_and_formatted():
    rows = subject_rows(
        (
            SubjectResult("1", data_year="2024/25", subject="Maths", qualification="GCSE", entries=100, grade5_plus_pct=70),
            SubjectResult("1", data_year="2024/25", subject="Art", qualification="GCSE", entries=20, grade4_plus_pct=80, grade7_plus_pct=15),
        )
    )
    assert [row["Subject"] for row in rows] == ["Art", "Maths"]
    assert rows[0]["Grade 4+"] == "80.0%"
    assert rows[0]["Grade 5+"] == MISSING
    assert rows[1]["Entries"] == "100"
    assert subject_rows(()) == []


def test_relevant_benchmarks_falls_back_to_national_when_local_code_has_no_match():
    school = _school()
    england = _benchmark("England", "National", "E92000001")
    other = _benchmark("Other", "Local authority", "E99999999")
    assert relevant_benchmarks(school, (other, england)) == (england,)
