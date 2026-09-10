from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import ks4
from school_finder.errors import SchoolFinderError


class Response:
    def __init__(self, error=None): self.error, self.closed = error, False
    def raise_for_status(self):
        if self.error: raise self.error
    def close(self): self.closed = True


class Session:
    def __init__(self, response=None, error=None): self.response, self.error = response, error
    def get(self, *args, **kwargs):
        if self.error: raise self.error
        return self.response


def test_discover_ks4_source_checks_endpoint_and_returns_stable_source():
    response = Response()
    source = ks4.discover_ks4_source(Session(response))
    assert source.url == ks4.EES_KS4_CSV_URL
    assert ks4.EES_KS4_DATASET_ID in source.release_label
    assert response.closed


def test_discover_ks4_source_wraps_request_errors():
    with pytest.raises(SchoolFinderError, match="Could not retrieve DfE"):
        ks4.discover_ks4_source(Session(error=requests.ConnectionError()))


def test_read_ks4_quality_uses_latest_headline_and_latest_numeric_progress8(tmp_path: Path):
    path = tmp_path / "ks4.csv"
    pd.DataFrame([
        {"school_urn":"100001", "time_period":"202324", "breakdown":"Total", "attainment8_average":"48", "engmath_95_percent":"50", "engmath_94_percent":"70", "ebacc_entering_percent":"30", "ebacc_aps_average":"4.1", "progress8_average":"0.21"},
        {"school_urn":"100001", "time_period":"202425", "breakdown":"Total", "attainment8_average":"52.1", "engmath_95_percent":"55", "engmath_94_percent":"75", "ebacc_entering_percent":"35", "ebacc_aps_average":"4.4", "progress8_average":"z"},
        {"school_urn":"100001", "time_period":"202425", "breakdown":"Girls", "attainment8_average":"99", "progress8_average":"1.5"},
        {"school_urn":"100002", "time_period":"202425", "breakdown":"Total", "attainment8_average":"45", "progress8_average":""},
    ]).to_csv(path, index=False)
    result = ks4.read_ks4_quality(path).set_index("urn")
    assert result.loc["100001", "performance_year"] == "202425"
    assert result.loc["100001", "attainment8"] == 52.1
    assert result.loc["100001", "progress8"] == 0.21
    assert result.loc["100001", "progress8_year"] == "202324"
    assert pd.isna(result.loc["100002", "progress8"])


def test_read_ks4_quality_requires_urn_and_time_period(tmp_path):
    path = tmp_path / "ks4.csv"
    pd.DataFrame({"URN": ["1"]}).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="missing school_urn or time_period"):
        ks4.read_ks4_quality(path)


def test_read_ks4_quality_requires_headline_total_rows(tmp_path):
    path = tmp_path / "ks4.csv"
    pd.DataFrame([{"school_urn":"1", "time_period":"202425", "breakdown":"Girls"}]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="no all-pupils headline rows"):
        ks4.read_ks4_quality(path)


def test_read_ks4_quality_handles_missing_optional_metric_and_progress_columns(tmp_path):
    path = tmp_path / "ks4.csv"
    pd.DataFrame([{"school_urn":"1", "time_period":"202425", "breakdown":"Total"}]).to_csv(path, index=False)
    result = ks4.read_ks4_quality(path)
    assert result.iloc[0]["urn"] == "1"
    assert pd.isna(result.iloc[0]["attainment8"])
    assert pd.isna(result.iloc[0]["progress8"])


def test_read_ks4_quality_keeps_historic_progress_only_urns(tmp_path: Path):
    path = tmp_path / "ks4.csv"
    pd.DataFrame([
        {
            "school_urn": "OLD",
            "time_period": "202324",
            "breakdown": "Total",
            "attainment8_average": "35.6",
            "progress8_average": "-0.76",
        },
        {
            "school_urn": "CURRENT",
            "time_period": "202425",
            "breakdown": "Total",
            "attainment8_average": "33.1",
            "progress8_average": "z",
        },
    ]).to_csv(path, index=False)

    result = ks4.read_ks4_quality(path).set_index("urn")

    assert result.loc["CURRENT", "attainment8"] == 33.1
    assert pd.isna(result.loc["CURRENT", "progress8"])
    assert result.loc["OLD", "progress8"] == -0.76
    assert result.loc["OLD", "progress8_year"] == "202324"
    assert pd.isna(result.loc["OLD", "performance_year"])
