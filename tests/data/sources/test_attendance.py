from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import attendance
from school_finder.errors import SchoolFinderError


class Response:
    def __init__(self, error=None):
        self.error = error
        self.closed = False

    def raise_for_status(self):
        if self.error:
            raise self.error

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


def _school_row(**overrides):
    row = {
        "time_period": "202425",
        "geographic_level": "School",
        "school_urn": "100001",
        "enrolments": "1000",
        "sess_overall_percent": "7.1",
        "sess_authorised_percent": "5.0",
        "sess_unauthorised_percent": "2.1",
        "enrolments_pa_10_exact_percent": "18.2",
        "enrolments_pa_50_exact_percent": "2.3",
    }
    row.update(overrides)
    return row


def _benchmark_row(**overrides):
    row = {
        "time_period": "202425",
        "geographic_level": "National",
        "country_code": "E92000001",
        "country_name": "England",
        "new_la_code": "",
        "la_name": "",
        "education_phase": "State-funded secondary",
        "enrolments": "3000000",
        "sess_overall_percent": "7.2",
        "sess_authorised_percent": "5.1",
        "sess_unauthorised_percent": "2.1",
        "enrolments_pa_10_exact_percent": "19.0",
        "enrolments_pa_50_exact_percent": "2.5",
    }
    row.update(overrides)
    return row


def test_discover_sources_check_endpoints_and_return_metadata():
    response = Response()
    school = attendance.discover_attendance_school_source(Session(response))
    assert school.name == attendance.ATTENDANCE_SOURCE_NAME
    assert attendance.ATTENDANCE_SCHOOL_DATASET_ID in school.url
    assert "2024/25" in school.release_label
    assert response.closed is True

    response = Response()
    benchmark = attendance.discover_attendance_benchmark_source(Session(response))
    assert benchmark.name == attendance.ATTENDANCE_BENCHMARK_SOURCE_NAME
    assert attendance.ATTENDANCE_BENCHMARK_DATASET_ID in benchmark.url
    assert response.closed is True


def test_discover_wraps_request_errors():
    with pytest.raises(SchoolFinderError, match="attendance school-level"):
        attendance.discover_attendance_school_source(
            Session(error=requests.ConnectionError("offline"))
        )
    with pytest.raises(SchoolFinderError, match="attendance benchmark"):
        attendance.discover_attendance_benchmark_source(
            Session(response=Response(requests.HTTPError("bad")))
        )


def test_read_attendance_school_uses_latest_school_rows_and_maps_metrics(tmp_path: Path):
    path = tmp_path / "attendance.csv"
    pd.DataFrame([
        _school_row(time_period="202324", sess_overall_percent="9.9"),
        _school_row(),
        _school_row(school_urn="100002", sess_overall_percent="z", sess_authorised_percent=""),
        _school_row(geographic_level="Local authority", school_urn="999999", sess_overall_percent="1"),
        _school_row(school_urn="", sess_overall_percent="2"),
    ]).to_csv(path, index=False)

    result = attendance.read_attendance_school(path).set_index("urn")
    assert list(result.index) == ["100001", "100002"]
    assert result.loc["100001", "attendance_year"] == "202425"
    assert result.loc["100001", "attendance_enrolments"] == 1000
    assert result.loc["100001", "overall_absence_pct"] == 7.1
    assert result.loc["100001", "authorised_absence_pct"] == 5.0
    assert result.loc["100001", "unauthorised_absence_pct"] == 2.1
    assert result.loc["100001", "persistent_absence_pct"] == 18.2
    assert result.loc["100001", "severe_absence_pct"] == 2.3
    assert pd.isna(result.loc["100002", "overall_absence_pct"])
    assert result.loc["100001", "attendance_source_dataset_id"] == attendance.ATTENDANCE_SCHOOL_DATASET_ID


def test_read_attendance_school_allows_missing_level_and_optional_metric_columns(tmp_path: Path):
    path = tmp_path / "attendance.csv"
    pd.DataFrame([
        {"time_period": "202425", "school_urn": "1", "sess_overall_percent": "8.0"}
    ]).to_csv(path, index=False)
    result = attendance.read_attendance_school(path).iloc[0]
    assert result["urn"] == "1"
    assert result["overall_absence_pct"] == 8.0
    assert pd.isna(result["severe_absence_pct"])


def test_attendance_school_requires_urn_and_valid_time(tmp_path: Path):
    missing_urn = tmp_path / "missing-urn.csv"
    pd.DataFrame([{"time_period": "202425"}]).to_csv(missing_urn, index=False)
    with pytest.raises(SchoolFinderError, match="missing school_urn"):
        attendance.read_attendance_school(missing_urn)

    missing_time = tmp_path / "missing-time.csv"
    pd.DataFrame([{"school_urn": "1"}]).to_csv(missing_time, index=False)
    with pytest.raises(SchoolFinderError, match="missing time_period"):
        attendance.read_attendance_school(missing_time)

    bad_time = tmp_path / "bad-time.csv"
    pd.DataFrame([{"time_period": "bad", "school_urn": "1"}]).to_csv(bad_time, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        attendance.read_attendance_school(bad_time)


def test_read_attendance_benchmarks_returns_latest_england_and_local_authority(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([
        _benchmark_row(time_period="202324", sess_overall_percent="8.0"),
        _benchmark_row(),
        _benchmark_row(
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            sess_overall_percent="6.8",
            enrolments_pa_10_exact_percent="17.5",
        ),
        _benchmark_row(education_phase="State-funded primary", sess_overall_percent="99"),
        _benchmark_row(geographic_level="Regional", sess_overall_percent="99"),
    ]).to_csv(path, index=False)

    result = attendance.read_attendance_benchmarks(path).set_index("benchmark_code")
    england = result.loc["E92000001"]
    assert england["benchmark_name"] == "England"
    assert england["attendance_year"] == "202425"
    assert england["overall_absence_pct"] == 7.2
    hampshire = result.loc["E10000014"]
    assert hampshire["benchmark_level"] == "Local authority"
    assert hampshire["benchmark_name"] == "Hampshire"
    assert hampshire["overall_absence_pct"] == 6.8
    assert hampshire["persistent_absence_pct"] == 17.5
    assert hampshire["attendance_source_dataset_id"] == attendance.ATTENDANCE_BENCHMARK_DATASET_ID


def test_attendance_benchmark_validation_and_missing_optional_metrics(tmp_path: Path):
    path = tmp_path / "missing-columns.csv"
    pd.DataFrame([{"time_period": "202425", "geographic_level": "National"}]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="geographic_level or education_phase"):
        attendance.read_attendance_benchmarks(path)

    no_secondary = tmp_path / "no-secondary.csv"
    pd.DataFrame([_benchmark_row(education_phase="State-funded primary")]).to_csv(no_secondary, index=False)
    with pytest.raises(SchoolFinderError, match="no secondary benchmark rows"):
        attendance.read_attendance_benchmarks(no_secondary)

    invalid_time = tmp_path / "invalid-time.csv"
    pd.DataFrame([_benchmark_row(time_period="bad")]).to_csv(invalid_time, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        attendance.read_attendance_benchmarks(invalid_time)

    bad_identity = tmp_path / "bad-identity.csv"
    row = _benchmark_row()
    row.pop("la_name")
    pd.DataFrame([row]).to_csv(bad_identity, index=False)
    with pytest.raises(SchoolFinderError, match="geography identity columns"):
        attendance.read_attendance_benchmarks(bad_identity)

    optional = tmp_path / "optional.csv"
    minimal = {
        "time_period": "202425", "geographic_level": "National",
        "country_code": "E92000001", "country_name": "England",
        "new_la_code": "", "la_name": "", "education_phase": "State-funded secondary",
    }
    pd.DataFrame([minimal]).to_csv(optional, index=False)
    result = attendance.read_attendance_benchmarks(optional).iloc[0]
    assert pd.isna(result["overall_absence_pct"])
