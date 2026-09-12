from datetime import date
import math

import pandas as pd

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
    available_trend_metrics,
    attendance_rows,
    behaviour_rows,
    destination_rows,
    find_school,
    format_date,
    format_integer,
    format_history_year,
    history_year_key,
    inspection_rows,
    overview_rows,
    pastoral_rows,
    relevant_benchmarks,
    school_address,
    subject_rows,
    trend_frame,
    trend_lineage_note,
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


def _history_rows():
    rows = []
    for year, school, hampshire, england in (
        ("202223", 48.0, 47.0, 46.0),
        ("202324", 50.0, 48.0, 47.0),
        ("202425", 52.0, 49.0, 48.0),
    ):
        rows.extend(
            [
                {"domain": "academics", "year": year, "metric": "attainment8", "series": "School", "value": school, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0},
                {"domain": "academics", "year": year, "metric": "attainment8", "series": "Hampshire", "value": hampshire, "source_urn": None, "source_school_name": None, "source_kind": None, "source_link_depth": None},
                {"domain": "academics", "year": year, "metric": "attainment8", "series": "England", "value": england, "source_urn": None, "source_school_name": None, "source_kind": None, "source_link_depth": None},
            ]
        )
    rows.extend(
        [
            {"domain": "academics", "year": "202324", "metric": "pupil_count", "series": "School", "value": 170, "source_urn": "999999", "source_school_name": "Old School", "source_kind": "predecessor", "source_link_depth": 1},
            {"domain": "academics", "year": "202425", "metric": "pupil_count", "series": "School", "value": 180, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0},
            {"domain": "academics", "year": "202425", "metric": "pupil_count", "series": "England", "value": 200, "source_urn": None, "source_school_name": None, "source_kind": None, "source_link_depth": None},
            {"domain": "attendance", "year": "202425", "metric": "overall_absence_pct", "series": "School", "value": 6.0, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0},
        ]
    )
    return pd.DataFrame(rows)


def test_history_year_helpers_support_dfe_formats():
    assert history_year_key("202425") == 202425
    assert history_year_key("2024/25") == 202425
    assert history_year_key("2024") == 2024
    assert history_year_key("bad") is None
    assert history_year_key(None) is None
    assert format_history_year("202425") == "2024/25"
    assert format_history_year("2024/25") == "2024/25"


def test_trend_metrics_require_two_school_years_and_frame_is_chronological():
    history = _history_rows()
    metrics = available_trend_metrics(history, "academics")
    assert "attainment8" in metrics
    assert "pupil_count" in metrics
    assert available_trend_metrics(history, "attendance") == ()
    assert available_trend_metrics(pd.DataFrame(), "academics") == ()
    assert available_trend_metrics(history, "unknown") == ()

    frame = trend_frame(history, "academics", "attainment8", years=2)
    assert frame["Year"].tolist() == ["2023/24", "2024/25"]
    assert list(frame.columns) == ["Year", "School", "England", "Hampshire"]
    assert frame["School"].tolist() == [50.0, 52.0]


def test_trend_frame_hides_invalid_benchmarks_for_school_only_metrics_and_handles_empty():
    history = _history_rows()
    frame = trend_frame(history, "academics", "pupil_count")
    assert list(frame.columns) == ["Year", "School"]
    assert frame["Year"].tolist() == ["2022/23", "2023/24", "2024/25"]
    assert pd.isna(frame.loc[0, "School"])

    assert trend_frame(pd.DataFrame(), "academics", "attainment8").empty
    assert trend_frame(history, "academics", "missing").empty

    bad = history.copy()
    bad.loc[bad["metric"].eq("attainment8"), "year"] = "unknown"
    assert trend_frame(bad, "academics", "attainment8").empty

    benchmarks_only = history[~history["series"].eq("School")]
    assert trend_frame(benchmarks_only, "academics", "attainment8").empty



def test_trend_frame_preserves_missing_metric_years_as_gaps():
    history = _history_rows()
    extra_domain_year = pd.DataFrame(
        [
            {"domain": "academics", "year": "202526", "metric": "pupil_count", "series": "School", "value": 190, "source_urn": "100001", "source_school_name": "Example School", "source_kind": "current", "source_link_depth": 0}
        ]
    )
    history = pd.concat([history, extra_domain_year], ignore_index=True)

    frame = trend_frame(history, "academics", "attainment8")

    assert frame["Year"].tolist() == ["2022/23", "2023/24", "2024/25", "2025/26"]
    assert pd.isna(frame.loc[3, "School"])

def test_trend_lineage_note_names_predecessor_schools():
    history = _history_rows()
    assert trend_lineage_note(history, "academics", "pupil_count") == (
        "Includes historical data from predecessor school: Old School."
    )
    assert trend_lineage_note(history, "academics", "attainment8") is None
    assert trend_lineage_note(pd.DataFrame(), "academics", "attainment8") is None

    extra = pd.concat(
        [
            history,
            pd.DataFrame(
                [
                    {"domain": "academics", "year": "202223", "metric": "pupil_count", "series": "School", "value": 160, "source_urn": "888888", "source_school_name": "Older School", "source_kind": "predecessor", "source_link_depth": 2}
                ]
            ),
        ],
        ignore_index=True,
    )
    assert trend_lineage_note(extra, "academics", "pupil_count") == (
        "Includes historical data from predecessor schools: Old School, Older School."
    )


def test_trend_frame_returns_empty_when_domain_has_no_valid_school_years():
    history = pd.DataFrame(
        [
            {
                "domain": "academics",
                "year": "unknown",
                "metric": "attainment8",
                "series": "School",
                "value": 50.0,
                "source_urn": "1",
                "source_school_name": "School",
                "source_kind": "current",
                "source_link_depth": 0,
            },
            {
                "domain": "academics",
                "year": "also-bad",
                "metric": "pupil_count",
                "series": "School",
                "value": 100,
                "source_urn": "1",
                "source_school_name": "School",
                "source_kind": "current",
                "source_link_depth": 0,
            },
        ]
    )

    assert trend_frame(history, "academics", "attainment8").empty
