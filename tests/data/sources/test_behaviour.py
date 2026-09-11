from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import behaviour
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
        "time_period": "202425", "geographic_level": "School", "school_urn": "100001",
        "headcount": "1000", "suspension": "120", "susp_rate": "12.0",
        "one_plus_susp": "80", "one_plus_susp_rate": "8.0",
        "perm_excl": "1", "perm_excl_rate": "0.1",
    }
    row.update(overrides)
    return row


def _benchmark_row(**overrides):
    row = {
        "time_period": "202425", "geographic_level": "National",
        "country_code": "E92000001", "country_name": "England", "new_la_code": "", "la_name": "",
        "education_phase": "State-funded secondary", "headcount": "3000000",
        "suspension": "600000", "susp_rate": "20.0", "one_plus_susp": "210000",
        "one_plus_susp_rate": "7.0", "perm_excl": "6000", "perm_excl_rate": "0.2",
    }
    row.update(overrides)
    return row


def test_discover_behaviour_sources_and_errors():
    response = Response()
    source = behaviour.discover_behaviour_school_source(Session(response))
    assert behaviour.BEHAVIOUR_SCHOOL_DATASET_ID in source.url
    assert response.closed
    response = Response()
    source = behaviour.discover_behaviour_benchmark_source(Session(response))
    assert behaviour.BEHAVIOUR_BENCHMARK_DATASET_ID in source.url
    assert response.closed
    with pytest.raises(SchoolFinderError, match="behaviour school-level"):
        behaviour.discover_behaviour_school_source(Session(error=requests.ConnectionError("offline")))
    with pytest.raises(SchoolFinderError, match="behaviour benchmark"):
        behaviour.discover_behaviour_benchmark_source(Session(response=Response(requests.HTTPError("bad"))))


def test_read_behaviour_school_latest_and_metrics(tmp_path: Path):
    path = tmp_path / "behaviour.csv"
    pd.DataFrame([
        _school_row(time_period="202324", susp_rate="99"),
        _school_row(),
        _school_row(school_urn="100002", suspension="z", perm_excl="x"),
        _school_row(geographic_level="Local authority", school_urn="9"),
        _school_row(school_urn=""),
    ]).to_csv(path, index=False)
    result = behaviour.read_behaviour_school(path).set_index("urn")
    assert list(result.index) == ["100001", "100002"]
    assert result.loc["100001", "behaviour_year"] == "202425"
    assert result.loc["100001", "behaviour_pupil_headcount"] == 1000
    assert result.loc["100001", "suspension_count"] == 120
    assert result.loc["100001", "suspension_rate"] == 12.0
    assert result.loc["100001", "pupils_with_one_or_more_suspension"] == 80
    assert result.loc["100001", "pupils_with_one_or_more_suspension_rate"] == 8.0
    assert result.loc["100001", "permanent_exclusion_count"] == 1
    assert result.loc["100001", "permanent_exclusion_rate"] == 0.1
    assert pd.isna(result.loc["100002", "suspension_count"])
    assert result.loc["100001", "behaviour_source_dataset_id"] == behaviour.BEHAVIOUR_SCHOOL_DATASET_ID


def test_behaviour_school_without_level_optional_metrics_and_validation(tmp_path: Path):
    path = tmp_path / "minimal.csv"
    pd.DataFrame([{"time_period": "202425", "school_urn": "1", "susp_rate": "4.2"}]).to_csv(path, index=False)
    result = behaviour.read_behaviour_school(path).iloc[0]
    assert result["suspension_rate"] == 4.2
    assert pd.isna(result["permanent_exclusion_rate"])

    missing_urn = tmp_path / "missing-urn.csv"
    pd.DataFrame([{"time_period": "202425"}]).to_csv(missing_urn, index=False)
    with pytest.raises(SchoolFinderError, match="missing school_urn"):
        behaviour.read_behaviour_school(missing_urn)

    missing_time = tmp_path / "missing-time.csv"
    pd.DataFrame([{"school_urn": "1"}]).to_csv(missing_time, index=False)
    with pytest.raises(SchoolFinderError, match="missing time_period"):
        behaviour.read_behaviour_school(missing_time)

    bad_time = tmp_path / "bad-time.csv"
    pd.DataFrame([{"time_period": "bad", "school_urn": "1"}]).to_csv(bad_time, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        behaviour.read_behaviour_school(bad_time)


def test_read_behaviour_benchmarks_filters_and_maps(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([
        _benchmark_row(time_period="202324", susp_rate="99"),
        _benchmark_row(),
        _benchmark_row(geographic_level="Local authority", new_la_code="E10000014", la_name="Hampshire", susp_rate="18.2", perm_excl_rate="0.15"),
        _benchmark_row(education_phase="State-funded primary", susp_rate="99"),
        _benchmark_row(geographic_level="Regional", susp_rate="99"),
    ]).to_csv(path, index=False)
    result = behaviour.read_behaviour_benchmarks(path).set_index("benchmark_code")
    assert result.loc["E92000001", "benchmark_name"] == "England"
    assert result.loc["E92000001", "suspension_rate"] == 20.0
    assert result.loc["E10000014", "benchmark_name"] == "Hampshire"
    assert result.loc["E10000014", "suspension_rate"] == 18.2
    assert result.loc["E10000014", "permanent_exclusion_rate"] == 0.15
    assert result.loc["E92000001", "behaviour_source_dataset_id"] == behaviour.BEHAVIOUR_BENCHMARK_DATASET_ID


def test_behaviour_benchmark_validation(tmp_path: Path):
    missing = tmp_path / "missing.csv"
    pd.DataFrame([{"time_period": "202425", "geographic_level": "National"}]).to_csv(missing, index=False)
    with pytest.raises(SchoolFinderError, match="geographic_level or education_phase"):
        behaviour.read_behaviour_benchmarks(missing)

    no_secondary = tmp_path / "no-secondary.csv"
    pd.DataFrame([_benchmark_row(education_phase="State-funded primary")]).to_csv(no_secondary, index=False)
    with pytest.raises(SchoolFinderError, match="no secondary benchmark rows"):
        behaviour.read_behaviour_benchmarks(no_secondary)

    bad_time = tmp_path / "bad-time.csv"
    pd.DataFrame([_benchmark_row(time_period="bad")]).to_csv(bad_time, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        behaviour.read_behaviour_benchmarks(bad_time)

    bad_identity = tmp_path / "bad-identity.csv"
    row = _benchmark_row(); row.pop("country_name")
    pd.DataFrame([row]).to_csv(bad_identity, index=False)
    with pytest.raises(SchoolFinderError, match="geography identity columns"):
        behaviour.read_behaviour_benchmarks(bad_identity)


def test_behaviour_history_keeps_multiple_published_years(tmp_path: Path):
    school_path = tmp_path / "behaviour-history.csv"
    pd.DataFrame([
        _school_row(time_period="202324", susp_rate="14.0"),
        _school_row(time_period="202425", susp_rate="12.0"),
    ]).to_csv(school_path, index=False)

    school = behaviour.read_behaviour_school_history(school_path)
    assert school["behaviour_year"].tolist() == ["202324", "202425"]
    assert school["suspension_rate"].tolist() == [14.0, 12.0]

    benchmark_path = tmp_path / "behaviour-benchmark-history.csv"
    pd.DataFrame([
        _benchmark_row(time_period="202324", susp_rate="21.0"),
        _benchmark_row(time_period="202425", susp_rate="20.0"),
        _benchmark_row(
            time_period="202324",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            susp_rate="19.0",
        ),
        _benchmark_row(
            time_period="202425",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            susp_rate="18.0",
        ),
    ]).to_csv(benchmark_path, index=False)

    benchmarks = behaviour.read_behaviour_benchmark_history(benchmark_path)
    england = benchmarks[benchmarks["benchmark_code"].eq("E92000001")]
    hampshire = benchmarks[benchmarks["benchmark_code"].eq("E10000014")]
    assert england["behaviour_year"].tolist() == ["202324", "202425"]
    assert hampshire["behaviour_year"].tolist() == ["202324", "202425"]
