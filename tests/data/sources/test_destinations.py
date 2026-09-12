from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import destinations
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


def _row(**overrides):
    row = {
        "time_period": "202223",
        "geographic_level": "School",
        "country_code": "E92000001",
        "country_name": "England",
        "new_la_code": "E10000014",
        "la_name": "Hampshire",
        "school_urn": "100001",
        "institution_group": "State-funded mainstream schools",
        "institution_type": "Total",
        "breakdown_topic": "Total",
        "breakdown": "Total",
        "data_type": "Percentage",
        "cohort": "200",
        "overall": "91.2",
        "education": "72.0",
        "appren": "8.0",
        "all_work": "11.2",
        "all_notsust": "5.0",
        "all_unknown": "3.8",
    }
    row.update(overrides)
    return row


def test_discover_destination_sources_and_errors():
    for function, dataset_id in (
        (destinations.discover_destination_school_source, destinations.DESTINATION_SCHOOL_DATASET_ID),
        (destinations.discover_destination_national_source, destinations.DESTINATION_NATIONAL_DATASET_ID),
        (destinations.discover_destination_la_source, destinations.DESTINATION_LA_DATASET_ID),
    ):
        response = Response()
        source = function(Session(response))
        assert dataset_id in source.url
        assert response.closed

    with pytest.raises(SchoolFinderError, match="Could not retrieve DfE destination school-level"):
        destinations.discover_destination_school_source(
            Session(error=requests.ConnectionError("offline"))
        )


def test_next_academic_year_handles_compact_slash_and_invalid():
    assert destinations.next_academic_year("202223") == "202324"
    assert destinations.next_academic_year("2022/23") == "2023/24"
    assert destinations.next_academic_year("bad") is None


def test_read_destination_school_uses_latest_percentage_total(tmp_path: Path):
    path = tmp_path / "destinations.csv"
    pd.DataFrame([
        _row(time_period="202122", overall="80"),
        _row(),
        _row(data_type="Number", overall="999"),
        _row(breakdown="Disadvantaged", overall="50"),
        _row(geographic_level="Local authority", overall="40"),
    ]).to_csv(path, index=False)
    row = destinations.read_destination_school(path).iloc[0]
    assert row["urn"] == "100001"
    assert row["destination_leaver_year"] == "202223"
    assert row["destination_year"] == "202324"
    assert row["destination_pupil_count"] == 200
    assert row["sustained_destination_pct"] == 91.2
    assert row["education_destination_pct"] == 72.0
    assert row["apprenticeship_destination_pct"] == 8.0
    assert row["employment_destination_pct"] == 11.2
    assert row["not_sustained_destination_pct"] == 5.0
    assert row["unknown_destination_pct"] == 3.8
    assert row["destination_source_dataset_id"] == destinations.DESTINATION_SCHOOL_DATASET_ID


def test_destination_school_validates_urn_and_usable_rows(tmp_path: Path):
    path = tmp_path / "missing.csv"
    pd.DataFrame({"time_period": ["202223"]}).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="missing school_urn"):
        destinations.read_destination_school(path)

    path2 = tmp_path / "invalid.csv"
    pd.DataFrame([_row(time_period="bad")]).to_csv(path2, index=False)
    with pytest.raises(SchoolFinderError, match="no usable headline rows"):
        destinations.read_destination_school(path2)


def test_read_destination_benchmarks_returns_england_and_local_authority(tmp_path: Path):
    national = tmp_path / "national.csv"
    local = tmp_path / "local.csv"
    pd.DataFrame([
        _row(geographic_level="National", school_urn="", new_la_code="", la_name="", overall="92.0"),
        _row(geographic_level="National", school_urn="", institution_group="Other", overall="1.0"),
    ]).to_csv(national, index=False)
    pd.DataFrame([
        _row(geographic_level="Local authority", school_urn="", overall="93.0"),
        _row(geographic_level="Local authority", school_urn="", institution_type="Other", overall="2.0"),
    ]).to_csv(local, index=False)
    result = destinations.read_destination_benchmarks(national, local)
    assert result["benchmark_level"].tolist() == ["National", "Local authority"]
    assert result.iloc[0]["benchmark_name"] == "England"
    assert result.iloc[0]["sustained_destination_pct"] == 92.0
    assert result.iloc[1]["benchmark_code"] == "E10000014"
    assert result.iloc[1]["sustained_destination_pct"] == 93.0


def test_destination_benchmark_requires_geography_identity(tmp_path: Path):
    national = tmp_path / "national.csv"
    local = tmp_path / "local.csv"
    row = _row(geographic_level="National", school_urn="")
    row.pop("country_code")
    pd.DataFrame([row]).to_csv(national, index=False)
    pd.DataFrame([_row(geographic_level="Local authority", school_urn="")]).to_csv(local, index=False)
    with pytest.raises(SchoolFinderError, match="geography identity"):
        destinations.read_destination_benchmarks(national, local)


def test_destination_helpers_handle_optional_columns_and_missing_metrics(tmp_path: Path):
    school = tmp_path / "school-minimal.csv"
    pd.DataFrame([{
        "time_period": "202223",
        "school_urn": "1",
        "cohort": "10",
        "overall": "90",
    }]).to_csv(school, index=False)
    row = destinations.read_destination_school(school).iloc[0]
    assert row["sustained_destination_pct"] == 90
    assert pd.isna(row["education_destination_pct"])

    national = tmp_path / "national-minimal.csv"
    local = tmp_path / "local-minimal.csv"
    pd.DataFrame([{
        "time_period": "202223",
        "country_code": "E92000001",
        "country_name": "England",
        "cohort": "100",
        "overall": "91",
    }]).to_csv(national, index=False)
    pd.DataFrame([{
        "time_period": "202223",
        "new_la_code": "E10000014",
        "la_name": "Hampshire",
        "cohort": "20",
        "overall": "92",
    }]).to_csv(local, index=False)
    result = destinations.read_destination_benchmarks(national, local)
    assert len(result) == 2


def test_destination_benchmark_keeps_rows_when_preferred_group_or_total_type_absent(tmp_path: Path):
    national = tmp_path / "national.csv"
    local = tmp_path / "local.csv"
    pd.DataFrame([_row(
        geographic_level="National", school_urn="", new_la_code="", la_name="",
        institution_group="Other", institution_type="Other",
    )]).to_csv(national, index=False)
    pd.DataFrame([_row(
        geographic_level="Local authority", school_urn="",
        institution_group="Other", institution_type="Other",
    )]).to_csv(local, index=False)
    result = destinations.read_destination_benchmarks(national, local)
    assert len(result) == 2


def test_destination_headline_requires_time_period(tmp_path: Path):
    path = tmp_path / "missing-time.csv"
    pd.DataFrame([{"school_urn": "1", "overall": "90"}]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="missing time_period"):
        destinations.read_destination_school(path)


def test_destination_history_keeps_multiple_school_and_benchmark_cohorts(tmp_path: Path):
    school_path = tmp_path / "destination-history.csv"
    pd.DataFrame([
        _row(time_period="202122", overall="89.0"),
        _row(time_period="202223", overall="91.2"),
    ]).to_csv(school_path, index=False)

    school = destinations.read_destination_school_history(school_path)
    assert school["destination_leaver_year"].tolist() == ["202122", "202223"]
    assert school["sustained_destination_pct"].tolist() == [89.0, 91.2]

    national = tmp_path / "destination-national-history.csv"
    local = tmp_path / "destination-local-history.csv"
    pd.DataFrame([
        _row(
            time_period="202122",
            geographic_level="National",
            school_urn="",
            new_la_code="",
            la_name="",
            overall="90.0",
        ),
        _row(
            time_period="202223",
            geographic_level="National",
            school_urn="",
            new_la_code="",
            la_name="",
            overall="92.0",
        ),
    ]).to_csv(national, index=False)
    pd.DataFrame([
        _row(
            time_period="202122",
            geographic_level="Local authority",
            school_urn="",
            overall="91.0",
        ),
        _row(
            time_period="202223",
            geographic_level="Local authority",
            school_urn="",
            overall="93.0",
        ),
    ]).to_csv(local, index=False)

    benchmarks = destinations.read_destination_benchmark_history(national, local)
    england = benchmarks[benchmarks["benchmark_level"].eq("National")]
    hampshire = benchmarks[benchmarks["benchmark_level"].eq("Local authority")]
    assert england["destination_leaver_year"].tolist() == ["202122", "202223"]
    assert hampshire["destination_leaver_year"].tolist() == ["202122", "202223"]
