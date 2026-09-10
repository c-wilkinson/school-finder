from datetime import date, datetime, time, timezone

import pandas as pd
import pytest

from school_finder.models import school as model
from school_finder.models.school import (
    AcademicPerformance, AttendanceStatistics, InspectionSummary, SchoolBenchmarks,
    SchoolResultSet, TravelInformation, WorkforceStatistics,
    school_benchmark_from_flat_record, school_result_from_flat_record,
)


def test_maps_all_current_and_future_canonical_fields_into_nested_contract():
    result = school_result_from_flat_record({
        "urn":"123456", "school_name":"Example School", "sector":"State-funded",
        "establishment_type":"Academy", "phase":"Secondary", "age_range":"11–16",
        "gender":"Mixed", "religious_character":"None", "website":"https://example.test",
        "telephone":"0123", "address":"1 Road", "town":"Town", "postcode":"RG1 1AA",
        "local_authority_code":"E10000014", "local_authority_name":"Hampshire",
        "easting":"1", "northing":2.4, "latitude":"51.2", "longitude":"-1.2",
        "performance_year":"202425", "progress8":"0.17", "progress8_year":"202324",
        "english_maths_grade5_pct":"55", "english_maths_grade4_pct":75,
        "pupil_count":"180", "attainment8":"50.2", "attainment8_english":"11",
        "attainment8_maths":"10", "attainment8_ebacc":"14.2", "attainment8_open":"15",
        "ebacc_entry_pct":"40", "ebacc_grade5_pct":"28", "ebacc_grade4_pct":"42",
        "ebacc_aps":"4.5", "triple_science_entry_pct":"31",
        "multiple_languages_entry_pct":"8", "gcse_entries_per_pupil":"8.2",
        "qualification_entries_per_pupil":"9.1", "progress8_pupil_count":"170",
        "progress8_english":"0.10", "progress8_maths":"0.21", "progress8_ebacc":"0.14",
        "progress8_open":"0.23",
        "ofsted_rating":"Good", "ofsted_equivalent_rating":"Good",
        "ofsted_equivalent_basis":"official",
        "ofsted_equivalent_explanation":"Official Ofsted overall effectiveness grade.",
        "ofsted_inspection_date":"2025-06-11",
        "ofsted_publication_date":"2025-07-01", "ofsted_safeguarding":"Met",
        "ofsted_inclusion":"Strong", "ofsted_curriculum_teaching":"Good",
        "ofsted_achievement":"Good", "ofsted_attendance_behaviour":"Good",
        "ofsted_personal_development":"Good", "ofsted_leadership":"Good",
        "ofsted_adjusted_score":"3.5",
        "pastoral_response_count":"84", "happy_pct":"82", "safe_pct":"90",
        "behaviour_positive_pct":"75", "bullying_dealt_with_pct":"68",
        "send_support_pct":"71", "communication_pct":"76",
        "concerns_dealt_with_pct":"69", "best_interests_pct":"80",
        "learning_support_pct":"79", "recommend_pct":"88",
        "pastoral_score":"79.35", "pastoral_score_coverage_pct":"100",
        "parent_view_as_at_date":"2026-04-06",
        "pastoral_source":"Ofsted Parent View management information",
        "pastoral_source_url":"https://example.test/parent-view.ods",
        "attendance_enrolments":"960",
        "overall_absence_pct":"7.4", "authorised_absence_pct":"5.1",
        "unauthorised_absence_pct":"2.3", "persistent_absence_pct":"12",
        "severe_absence_pct":"1.2", "attendance_year":"202425",
        "attendance_source":"DfE absence", "attendance_source_dataset_id":"att-id",
        "attendance_source_urn":"111", "attendance_source_school_name":"Old school",
        "attendance_source_kind":"predecessor", "attendance_source_link_depth":"1",
        "behaviour_pupil_headcount":"960", "suspension_count":"18",
        "suspension_rate":"2.3", "pupils_with_one_or_more_suspension":"14",
        "pupils_with_one_or_more_suspension_rate":"1.5",
        "permanent_exclusion_count":"1", "permanent_exclusion_rate":"0.1",
        "behaviour_year":"202425", "behaviour_source":"DfE behaviour",
        "behaviour_source_dataset_id":"beh-id", "behaviour_source_urn":"123456",
        "behaviour_source_school_name":"Example School", "behaviour_source_kind":"current",
        "behaviour_source_link_depth":"0",
        "pupil_fte":"960", "teacher_fte":"60", "qualified_teacher_fte":"58",
        "classroom_teacher_fte":"48", "teaching_assistant_fte":"12",
        "support_staff_fte":"25", "teachers_without_qts_fte":"2",
        "part_time_teacher_pct":"20", "pupil_qualified_teacher_ratio":"16.55",
        "pupil_teacher_ratio":"16", "pupil_adult_ratio":"11.3",
        "workforce_year":"202526", "workforce_ratio_year":"202526",
        "workforce_source":"DfE workforce", "workforce_source_dataset_id":"wf-id",
        "workforce_ratio_source":"DfE ratios", "workforce_ratio_source_dataset_id":"ratio-id",
        "workforce_source_urn":"123456", "workforce_source_school_name":"Example School",
        "workforce_source_kind":"current", "workforce_source_link_depth":"0",
        "destination_pupil_count":"175", "sustained_destination_pct":"94.2",
        "education_destination_pct":"83.1", "apprenticeship_destination_pct":"4.5",
        "employment_destination_pct":"6.6", "not_sustained_destination_pct":"3.1",
        "unknown_destination_pct":"2.7", "destination_leaver_year":"202223",
        "destination_year":"202324", "destination_source":"DfE destinations",
        "destination_source_dataset_id":"dest-id", "destination_source_urn":"111",
        "destination_source_school_name":"Old school", "destination_source_kind":"predecessor",
        "destination_source_link_depth":"1",
        "admissions_policy":"Non-selective",
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
    assert result.location.local_authority_code == "E10000014"
    assert result.location.local_authority_name == "Hampshire"
    assert result.academics.attainment8 == 50.2
    assert result.academics.pupil_count == 180
    assert result.academics.attainment8_ebacc == 14.2
    assert result.academics.attainment8_open == 15.0
    assert result.academics.ebacc_grade5_pct == 28.0
    assert result.academics.triple_science_entry_pct == 31.0
    assert result.academics.gcse_entries_per_pupil == 8.2
    assert result.academics.progress8_pupil_count == 170
    assert result.academics.progress8_open == 0.23
    assert result.inspection.inspection_year == 2025
    assert result.inspection.equivalent_rating == "Good"
    assert result.inspection.equivalent_basis == "official"
    assert result.pastoral.response_count == 84
    assert result.pastoral.safe_pct == 90.0
    assert result.pastoral.score == 79.35
    assert result.pastoral.as_at_date == date(2026, 4, 6)
    assert result.attendance.overall_absence_pct == 7.4
    assert result.attendance.authorised_absence_pct == 5.1
    assert result.attendance.source_kind == "predecessor"
    assert result.behaviour.permanent_exclusion_count == 1
    assert result.behaviour.suspension_rate == 2.3
    assert result.workforce.pupil_teacher_ratio == 16.0
    assert result.workforce.pupils_per_classroom_teacher == 20.0
    assert result.workforce.pupils_per_classroom_and_support_staff == 16.0
    assert result.destinations.sustained_destination_pct == 94.2
    assert result.destinations.destination_year == "202324"
    assert result.destinations.source_kind == "predecessor"
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
    assert WorkforceStatistics(pupil_fte=100, classroom_teacher_fte=0).pupils_per_classroom_teacher is None
    assert WorkforceStatistics(pupil_fte=100).pupils_per_classroom_and_support_staff is None
    assert WorkforceStatistics(pupil_fte=100, classroom_teacher_fte=0, teaching_assistant_fte=0).pupils_per_classroom_and_support_staff is None
    assert WorkforceStatistics(pupil_fte=100, classroom_teacher_fte=4, teaching_assistant_fte=1).pupils_per_classroom_and_support_staff == 20.0


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


def test_benchmark_from_flat_record_maps_metadata_and_academics():
    benchmark = school_benchmark_from_flat_record({
        "benchmark_level": "Local authority",
        "benchmark_code": "E10000014",
        "benchmark_name": "Hampshire",
        "source": "DfE benchmark source",
        "source_dataset_id": "dataset-id",
        "performance_year": "202425",
        "pupil_count": "12000",
        "attainment8_english": "10.8",
        "attainment8_maths": "9.4",
        "attainment8_ebacc": "13.2",
        "attainment8_open": "13.4",
        "ebacc_grade5_pct": "25.0",
        "ebacc_grade4_pct": "38.0",
        "triple_science_entry_pct": "28.0",
        "multiple_languages_entry_pct": "6.0",
        "gcse_entries_per_pupil": "8.1",
        "qualification_entries_per_pupil": "9.0",
        "progress8_pupil_count": "11000",
        "progress8": "-0.01",
        "progress8_english": "0.02",
        "progress8_maths": "-0.03",
        "progress8_ebacc": "-0.04",
        "progress8_open": "0.01",
        "progress8_year": "202324",
        "english_maths_grade5_pct": "47.1",
        "english_maths_grade4_pct": "66.2",
        "attainment8": "46.8",
        "ebacc_entry_pct": "39.2",
        "ebacc_aps": "4.15",
        "attendance_year": "202425",
        "attendance_enrolments": "1000",
        "overall_absence_pct": "7.0",
        "authorised_absence_pct": "5.0",
        "unauthorised_absence_pct": "2.0",
        "persistent_absence_pct": "18.0",
        "severe_absence_pct": "2.0",
        "attendance_source": "absence",
        "attendance_source_dataset_id": "absence-id",
        "behaviour_year": "202425",
        "behaviour_pupil_headcount": "1000",
        "suspension_count": "120",
        "suspension_rate": "12.0",
        "pupils_with_one_or_more_suspension": "80",
        "pupils_with_one_or_more_suspension_rate": "8.0",
        "permanent_exclusion_count": "1",
        "permanent_exclusion_rate": "0.1",
        "behaviour_source": "behaviour",
        "behaviour_source_dataset_id": "beh-id",
        "workforce_year": "202526",
        "workforce_ratio_year": "202526",
        "pupil_fte": "1000",
        "teacher_fte": "60",
        "qualified_teacher_fte": "58",
        "classroom_teacher_fte": "50",
        "teaching_assistant_fte": "12",
        "support_staff_fte": "30",
        "teachers_without_qts_fte": "2",
        "part_time_teacher_pct": "19",
        "pupil_qualified_teacher_ratio": "17.2",
        "pupil_teacher_ratio": "16.7",
        "pupil_adult_ratio": "11.1",
        "workforce_source": "workforce",
        "workforce_source_dataset_id": "wf-id",
        "workforce_ratio_source": "ratios",
        "workforce_ratio_source_dataset_id": "ratio-id",
        "destination_pupil_count": "11000",
        "sustained_destination_pct": "92.0",
        "education_destination_pct": "80.0",
        "apprenticeship_destination_pct": "5.0",
        "employment_destination_pct": "7.0",
        "not_sustained_destination_pct": "4.0",
        "unknown_destination_pct": "4.0",
        "destination_leaver_year": "202223",
        "destination_year": "202324",
        "destination_source": "destinations",
        "destination_source_dataset_id": "dest-id",
    })
    assert benchmark.label == "Hampshire"
    assert benchmark.level == "Local authority"
    assert benchmark.code == "E10000014"
    assert benchmark.source == "DfE benchmark source"
    assert benchmark.source_dataset_id == "dataset-id"
    assert benchmark.academics.data_year == "202425"
    assert benchmark.academics.pupil_count == 12000
    assert benchmark.academics.attainment8_ebacc == 13.2
    assert benchmark.academics.ebacc_grade5_pct == 25.0
    assert benchmark.academics.progress8_pupil_count == 11000
    assert benchmark.academics.progress8_english == 0.02
    assert benchmark.academics.progress8 == -0.01
    assert benchmark.academics.progress8_year == "202324"
    assert benchmark.academics.english_maths_grade5_pct == 47.1
    assert benchmark.academics.english_maths_grade4_pct == 66.2
    assert benchmark.academics.attainment8 == 46.8
    assert benchmark.academics.ebacc_entry_pct == 39.2
    assert benchmark.academics.ebacc_aps == 4.15
    assert benchmark.attendance.overall_absence_pct == 7.0
    assert benchmark.attendance.enrolments == 1000
    assert benchmark.behaviour.suspension_rate == 12.0
    assert benchmark.behaviour.permanent_exclusion_rate == 0.1
    assert benchmark.workforce.teacher_fte == 60.0
    assert benchmark.workforce.pupil_teacher_ratio == 16.7
    assert benchmark.workforce.ratio_year == "202526"
    assert benchmark.destinations.sustained_destination_pct == 92.0
    assert benchmark.destinations.destination_year == "202324"


def test_benchmark_from_flat_record_handles_missing_identity_and_metrics():
    benchmark = school_benchmark_from_flat_record({})
    assert benchmark.label == ""
    assert benchmark.level is None
    assert benchmark.code is None
    assert benchmark.academics.attainment8 is None


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
    assert WorkforceStatistics(classroom_teacher_fte=4, teaching_assistant_fte=1).pupils_per_classroom_and_support_staff is None


def test_missing_detection_tolerates_objects_with_broken_inequality():
    class Broken:
        def __str__(self): return "value"
        def __ne__(self, other): raise TypeError("no comparison")
    assert model._is_missing(Broken()) is False


def test_maps_preference_scoring_into_explainable_school_score():
    record = {
        "urn": "1",
        "school_name": "Scored School",
        "distance_miles": 1.5,
        "ofsted_equivalent_rating": "Good",
        "attainment8": 52.0,
        "progress8": 0.2,
        "english_maths_grade5_pct": 61.0,
        "ebacc_aps": 4.4,
        "preference_score": 81.25,
        "preference_score_coverage_pct": 80.0,
    }
    for metric in model.PreferenceMetric:
        key = metric.value.replace("-", "_")
        record[f"preference_{key}_score"] = 75.0
        record[f"preference_{key}_requested_weight_pct"] = 20.0
        record[f"preference_{key}_effective_weight_pct"] = 25.0

    result = school_result_from_flat_record(record)
    score = result.preference_score
    assert score.overall == 81.25
    assert score.coverage_pct == 80.0
    assert len(score.components) == 7
    assert score.component(model.PreferenceMetric.DISTANCE).raw_value == 1.5
    assert score.component(model.PreferenceMetric.OFSTED).raw_value == "Good"
    assert score.component(model.PreferenceMetric.ATTAINMENT8).raw_value == 52.0
    assert score.component(model.PreferenceMetric.PROGRESS8).raw_value == 0.2
    assert score.component(model.PreferenceMetric.GRADE5_ENGLISH_MATHS).raw_value == 61.0
    assert score.component(model.PreferenceMetric.EBACC_APS).raw_value == 4.4
    assert result.to_dict()["preference_score"]["overall"] == 81.25


def test_scoring_record_with_zero_coverage_is_preserved_as_applied_but_unscored():
    result = school_result_from_flat_record({
        "urn": "1",
        "school_name": "No data",
        "preference_score": None,
        "preference_score_coverage_pct": 0.0,
    })
    assert result.preference_score is not None
    assert result.preference_score.overall is None
    assert result.preference_score.coverage_pct == 0.0
    assert all(component.requested_weight_pct == 0.0 for component in result.preference_score.components)
    assert all(component.effective_weight_pct == 0.0 for component in result.preference_score.components)
