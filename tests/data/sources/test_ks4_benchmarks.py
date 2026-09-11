from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import ks4_benchmarks
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
        "time_period": "202425",
        "geographic_level": "National",
        "country_code": "E92000001",
        "country_name": "England",
        "new_la_code": "",
        "la_name": "",
        "establishment_type_group": "All state-funded",
        "breakdown_topic": "Total",
        "breakdown": "Total",
        "pupil_count": "200",
        "attainment8_average": "46.1",
        "attainment8eng_average": "10.0",
        "attainment8mat_average": "9.5",
        "attainment8ebacc_average": "12.5",
        "attainment8open_average": "14.1",
        "engmath_95_percent": "45.4",
        "engmath_94_percent": "64.8",
        "ebacc_entering_percent": "40.5",
        "ebacc_95_percent": "20.0",
        "ebacc_94_percent": "30.0",
        "ebacc_aps_average": "4.09",
        "sci_triple_entering_percent": "25",
        "lan_multiple_entering_percent": "10",
        "gcse_entries_average": "7.1",
        "qual_entries_average": "7.8",
        "progress8_pupil_count": "180",
        "progress8_average": "z",
        "progress8eng_average": "z",
        "progress8mat_average": "z",
        "progress8ebacc_average": "z",
        "progress8open_average": "z",
    }
    row.update(overrides)
    return row


def test_discover_source_checks_endpoint_and_returns_stable_source():
    response = Response()
    source = ks4_benchmarks.discover_ks4_benchmark_source(Session(response))
    assert source.url == ks4_benchmarks.EES_KS4_BENCHMARK_CSV_URL
    assert ks4_benchmarks.EES_KS4_BENCHMARK_DATASET_ID in source.release_label
    assert response.closed is True


def test_discover_source_wraps_request_errors():
    with pytest.raises(SchoolFinderError, match="Could not retrieve DfE KS4 benchmark"):
        ks4_benchmarks.discover_ks4_benchmark_source(
            Session(error=requests.ConnectionError("offline"))
        )


def test_read_benchmarks_returns_current_england_and_la_with_latest_published_progress8(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([
        _row(time_period="202324", progress8_pupil_count="190", progress8_average="0.02", progress8eng_average="0.03", progress8mat_average="0.01", progress8ebacc_average="0.04", progress8open_average="0.00", attainment8_average="45.0"),
        _row(),
        _row(
            time_period="202324",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            country_code="E92000001",
            country_name="England",
            progress8_pupil_count="195",
            progress8_average="-0.01",
            progress8eng_average="0.01",
            progress8mat_average="-0.02",
            progress8ebacc_average="-0.03",
            progress8open_average="0.00",
            attainment8_average="45.5",
        ),
        _row(
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            attainment8_average="46.8",
            engmath_95_percent="47.1",
            engmath_94_percent="66.2",
            ebacc_entering_percent="39.2",
            ebacc_aps_average="4.15",
        ),
        _row(breakdown="Girls", attainment8_average="99"),
        _row(establishment_type_group="Independent schools", attainment8_average="1"),
        _row(geographic_level="Regional", attainment8_average="88"),
    ]).to_csv(path, index=False)

    result = ks4_benchmarks.read_ks4_benchmarks(path).set_index("benchmark_code")

    england = result.loc["E92000001"]
    assert england["benchmark_level"] == "National"
    assert england["benchmark_name"] == "England"
    assert england["performance_year"] == "202425"
    assert england["pupil_count"] == 200
    assert england["attainment8"] == 46.1
    assert england["attainment8_english"] == 10.0
    assert england["attainment8_open"] == 14.1
    assert england["ebacc_grade5_pct"] == 20.0
    assert england["triple_science_entry_pct"] == 25
    assert england["gcse_entries_per_pupil"] == 7.1
    assert england["progress8_pupil_count"] == 190
    assert england["progress8"] == 0.02
    assert england["progress8_english"] == 0.03
    assert england["progress8_maths"] == 0.01
    assert england["progress8_ebacc"] == 0.04
    assert england["progress8_open"] == 0.0
    assert england["progress8_year"] == "202324"
    assert england["source_dataset_id"] == ks4_benchmarks.EES_KS4_BENCHMARK_DATASET_ID

    hampshire = result.loc["E10000014"]
    assert hampshire["benchmark_level"] == "Local authority"
    assert hampshire["benchmark_name"] == "Hampshire"
    assert hampshire["attainment8"] == 46.8
    assert hampshire["english_maths_grade5_pct"] == 47.1
    assert hampshire["progress8"] == -0.01
    assert hampshire["progress8_year"] == "202324"


def test_read_benchmarks_handles_no_progress_column_and_missing_optional_metrics(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([
        {
            "time_period": "202425",
            "geographic_level": "National",
            "country_code": "E92000001",
            "country_name": "England",
            "new_la_code": "",
            "la_name": "",
            "breakdown": "Total",
        }
    ]).to_csv(path, index=False)

    result = ks4_benchmarks.read_ks4_benchmarks(path).iloc[0]
    assert pd.isna(result["attainment8"])
    assert pd.isna(result["progress8"])
    assert pd.isna(result["progress8_year"])


def test_read_benchmarks_handles_progress_column_with_no_numeric_values(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([_row(progress8_average="z")]).to_csv(path, index=False)
    result = ks4_benchmarks.read_ks4_benchmarks(path).iloc[0]
    assert pd.isna(result["progress8"])
    assert pd.isna(result["progress8_year"])


def test_read_benchmarks_requires_time_and_geographic_level(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame({"time_period": ["202425"]}).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="missing time_period or geographic_level"):
        ks4_benchmarks.read_ks4_benchmarks(path)


def test_read_benchmarks_requires_headline_rows(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([_row(breakdown="Girls")]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="no all-pupils national or local-authority rows"):
        ks4_benchmarks.read_ks4_benchmarks(path)


def test_read_benchmarks_requires_a_valid_time_period(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([_row(time_period="not-a-year")]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        ks4_benchmarks.read_ks4_benchmarks(path)


def test_read_benchmarks_requires_identity_columns(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    row = _row()
    row.pop("la_name")
    pd.DataFrame([row]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="identity columns"):
        ks4_benchmarks.read_ks4_benchmarks(path)


def test_read_benchmarks_discards_blank_codes_and_orders_national_first(tmp_path: Path):
    path = tmp_path / "benchmarks.csv"
    pd.DataFrame([
        _row(
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
        ),
        _row(),
        _row(
            geographic_level="Local authority",
            new_la_code="",
            la_name="No code",
        ),
    ]).to_csv(path, index=False)
    result = ks4_benchmarks.read_ks4_benchmarks(path)
    assert result["benchmark_name"].tolist() == ["England", "Hampshire"]


def test_read_ks4_benchmark_history_returns_all_geography_years(tmp_path: Path):
    path = tmp_path / "ks4-benchmark-history.csv"
    pd.DataFrame([
        _row(time_period="202324", attainment8_average="45.0"),
        _row(time_period="202425", attainment8_average="46.1"),
        _row(
            time_period="202324",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            attainment8_average="45.5",
        ),
        _row(
            time_period="202425",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            attainment8_average="46.8",
        ),
    ]).to_csv(path, index=False)

    result = ks4_benchmarks.read_ks4_benchmark_history(path)

    england = result[result["benchmark_code"].eq("E92000001")]
    hampshire = result[result["benchmark_code"].eq("E10000014")]
    assert england["performance_year"].tolist() == ["202324", "202425"]
    assert hampshire["performance_year"].tolist() == ["202324", "202425"]
