from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from school_finder.models import school as model
from school_finder.models.school import (
    AcademicPerformance, AttendanceStatistics, InspectionSummary, SchoolBenchmarks,
    SchoolResultSet, TravelInformation, WorkforceStatistics, school_result_from_flat_record,
)


def test_maps_all_current_and_future_canonical_fields_into_nested_contract():
    result = school_result_from_flat_record({
        "urn":"123456", "school_name":"Example School", "sector":"State-funded",
        "establishment_type":"Academy", "phase":"Secondary", "age_range":"11–16",
        "gender":"Mixed", "religious_character":"None", "website":"https://example.test",
        "telephone":"0123", "address":"1 Road", "town":"Town", "postcode":"RG1 1AA",
        "easting":"1", "northing":2.4, "latitude":"51.2", "longitude":"-1.2",
        "performance_year":"202425", "progress8":"0.17", "progress8_year":"202324",
        "english_maths_grade5_pct":"55", "english_maths_grade4_pct":75,
        "attainment8":"50.2", "attainment8_english":"11", "attainment8_maths":"10",
        "attainment8_other":"29.2", "ebacc_entry_pct":"40", "ebacc_aps":"4.5",
        "ofsted_rating":"Good", "ofsted_inspection_date":"2025-06-11",
        "ofsted_publication_date":"2025-07-01", "ofsted_safeguarding":"Met",
        "ofsted_inclusion":"Strong", "ofsted_curriculum_teaching":"Good",
        "ofsted_achievement":"Good", "ofsted_attendance_behaviour":"Good",
        "ofsted_personal_development":"Good", "ofsted_leadership":"Good",
        "ofsted_adjusted_score":"3.5", "overall_absence_pct":"7.4",
        "persistent_absence_pct":"12", "attendance_year":"202425", "suspension_count":"18",
        "suspension_pct":"2.3", "permanent_exclusion_count":"1",
        "permanent_exclusion_pct":"0.1", "behaviour_year":"202425", "pupil_headcount":"960",
        "teacher_headcount":"60", "classroom_teacher_headcount":"48",
        "teaching_assistant_headcount":"12", "workforce_year":"2025", "admissions_policy":"Non-selective",
        "selective":"no", "published_admission_number":"240", "catchment_description":"Area",
        "last_offer_distance_miles":"2.4", "last_offer_year":"2026", "admissions_likelihood":"Likely",
        "distance_miles":"1.25", "walking_minutes":"42", "public_transport_minutes":"27",
        "annual_transport_cost_gbp":"500", "school_day_summary":"08:30-15:30",
        "leave_home_time":"07:45", "home_arrival_time":"16:05", "total_day_minutes":"500",
        "user_notes":"Visit", "user_score":"4.0",
    })
    assert result.identity.urn == "123456"
    assert result.location.easting == 1
    assert result.location.northing == 2
    assert result.academics.attainment8 == 50.2
    assert result.inspection.inspection_year == 2025
    assert result.attendance.overall_absence_pct == 7.4
    assert result.behaviour.permanent_exclusion_count == 1
    assert result.workforce.pupils_per_classroom_teacher == 20.0
    assert result.workforce.pupils_per_classroom_and_support_staff == 16.0
    assert result.admissions.selective is False
    assert result.travel.public_transport_time_saved_minutes == 15
    assert result.travel.school_day.summary == "08:30-15:30"
    assert result.user_assessment.score == 4.0


def test_missing_identity_values_default_to_empty_strings_and_no_user_assessment():
    result = school_result_from_flat_record({})
    assert result.identity.urn == ""
    assert result.identity.name == ""
    assert result.user_assessment is None
    assert result.inspection.inspection_year is None


def test_workforce_derived_ratios_handle_missing_and_zero_values():
    assert WorkforceStatistics().pupils_per_classroom_teacher is None
    assert WorkforceStatistics(pupil_headcount=100, classroom_teacher_headcount=0).pupils_per_classroom_teacher is None
    assert WorkforceStatistics(pupil_headcount=100).pupils_per_classroom_and_support_staff is None
    assert WorkforceStatistics(pupil_headcount=100, classroom_teacher_headcount=0, teaching_assistant_headcount=0).pupils_per_classroom_and_support_staff is None
    assert WorkforceStatistics(pupil_headcount=100, classroom_teacher_headcount=4, teaching_assistant_headcount=1).pupils_per_classroom_and_support_staff == 20.0


def test_travel_saved_minutes_handles_missing_and_negative_savings():
    assert TravelInformation().public_transport_time_saved_minutes is None
    assert TravelInformation(walking_minutes=20).public_transport_time_saved_minutes is None
    assert TravelInformation(walking_minutes=20, public_transport_minutes=25).public_transport_time_saved_minutes == -5


@pytest.mark.parametrize("value", [None, "", "<NA>", "NaT", "nan", "None", "N/A", "?", float("nan"), pd.NA])
def test_missing_markers_are_treated_as_missing(value):
    assert model._is_missing(value)


def test_conversion_helpers_cover_valid_and_invalid_inputs():
    assert model._as_str(" x ") == "x"
    assert model._as_str(None) is None
    assert model._as_float("1.25") == 1.25
    assert model._as_float("bad") is None
    assert model._as_int("2.6") == 3
    assert model._as_bool(True) is True
    assert model._as_bool("YES") is True
    assert model._as_bool("0") is False
    assert model._as_bool("perhaps") is None
    d = date(2026, 9, 7)
    dt = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)
    assert model._as_date(d) == d
    assert model._as_date(dt) == d
    assert model._as_date("2026-09-07T12:30:00") == d
    assert model._as_date("bad") is None
    assert model._as_time(time(7,45,1,999)) == time(7,45,1)
    assert model._as_time(dt) == time(12,30)
    assert model._as_time("07:45") == time(7,45)
    assert model._as_time("7:45PM") == time(19,45)
    assert model._as_time("7:45 PM") == time(19,45)
    assert model._as_time("bad") is None


def test_benchmarks_are_separate_from_real_schools_and_serialise():
    school = school_result_from_flat_record({"urn":"123456", "school_name":"Example"})
    benchmark = SchoolBenchmarks(label="England", academics=AcademicPerformance(attainment8=45.9), attendance=AttendanceStatistics(overall_absence_pct=8.9))
    payload = SchoolResultSet(schools=(school,), benchmarks=(benchmark,)).to_dict()
    assert payload["schools"][0]["identity"]["urn"] == "123456"
    assert payload["benchmarks"][0]["academics"]["attainment8"] == 45.9
    assert "identity" not in payload["benchmarks"][0]


def test_serialise_dates_datetimes_times_and_tuples():
    value = (date(2026,9,7), datetime(2026,9,7,12,30), time(7,45))
    assert model._serialise(value) == ["2026-09-07", "2026-09-07T12:30:00", "07:45:00"]


def test_result_and_benchmark_to_dict_delegate_to_serialisation():
    result = school_result_from_flat_record({"urn":"1", "school_name":"X", "ofsted_inspection_date":"2025-01-02"})
    assert result.to_dict()["inspection"]["inspection_date"] == "2025-01-02"
    benchmark = SchoolBenchmarks(label="England")
    assert benchmark.to_dict()["label"] == "England"


def test_inspection_year_property():
    assert InspectionSummary(inspection_date=date(2024, 5, 6)).inspection_year == 2024


def test_workforce_support_ratio_is_none_without_pupil_count():
    assert WorkforceStatistics(classroom_teacher_headcount=4, teaching_assistant_headcount=1).pupils_per_classroom_and_support_staff is None


def test_missing_detection_tolerates_objects_with_broken_inequality():
    class Broken:
        def __str__(self): return "value"
        def __ne__(self, other): raise TypeError("no comparison")
    assert model._is_missing(Broken()) is False
