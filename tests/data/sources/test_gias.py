from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import gias
from school_finder.errors import SchoolFinderError


class Response:
    def __init__(self, status):
        self.status_code = status
        self.closed = False
    def close(self): self.closed = True


class Session:
    def __init__(self, statuses=None, error=None):
        self.statuses = iter(statuses or [])
        self.error = error
        self.urls = []
    def get(self, url, **kwargs):
        self.urls.append(url)
        if self.error:
            raise self.error
        return Response(next(self.statuses))


def _raw_row(**overrides):
    row = {column: "" for column in gias.GIAS_COLUMNS}
    row.update({
        "URN": "100001",
        "EstablishmentName": " Example School ",
        "TypeOfEstablishment (name)": "Academy converter",
        "EstablishmentTypeGroup (name)": "Academies",
        "EstablishmentStatus (name)": "Open",
        "PhaseOfEducation (name)": "Secondary",
        "StatutoryLowAge": "11",
        "StatutoryHighAge": "16",
        "Gender (name)": "Mixed",
        "ReligiousCharacter (name)": "None",
        "AdmissionsPolicy (name)": "Non-selective",
        "Street": "Road",
        "Town": "Town",
        "County (name)": "County",
        "Postcode": "rg226aa",
        "SchoolWebsite": "https://example.test",
        "TelephoneNum": "0123",
        "Easting": "463000.2",
        "Northing": "150000.4",
    })
    row.update(overrides)
    return row


def test_discover_latest_gias_source_skips_404_and_returns_first_available():
    session = Session([404, 200])
    source = gias.discover_latest_gias_source(session, today=date(2026, 9, 7))
    assert source.source_date == date(2026, 9, 6)
    assert source.url.endswith("edubasealldata20260906.csv")


def test_discover_latest_gias_source_rejects_non_404_http_status():
    with pytest.raises(SchoolFinderError, match="HTTP 500"):
        gias.discover_latest_gias_source(Session([500]), today=date(2026, 9, 7))


def test_discover_latest_gias_source_wraps_connection_error():
    with pytest.raises(SchoolFinderError, match="Could not contact"):
        gias.discover_latest_gias_source(
            Session(error=requests.ConnectionError("offline")), today=date(2026, 9, 7)
        )


def test_discover_latest_gias_source_errors_when_lookback_exhausted(monkeypatch):
    monkeypatch.setattr(gias, "GIAS_LOOKBACK_DAYS", 2)
    with pytest.raises(SchoolFinderError, match="No GIAS extract"):
        gias.discover_latest_gias_source(Session([404, 404]), today=date(2026, 9, 7))


def test_download_gias_csv_uses_expected_minimum_size(tmp_path, monkeypatch):
    source = gias.GiasSource(date(2026, 9, 7), "https://example.test/gias.csv")
    called = {}
    monkeypatch.setattr(gias, "stream_download", lambda s, u, d, minimum_size: called.update(url=u, dest=d, size=minimum_size))
    dest = tmp_path / "gias.csv"
    gias.download_gias_csv(object(), source, dest)
    assert called == {"url": source.url, "dest": dest, "size": 100_000}


def test_read_gias_csv_accepts_expected_schema(tmp_path):
    path = tmp_path / "gias.csv"
    pd.DataFrame([_raw_row()]).to_csv(path, index=False)
    frame = gias.read_gias_csv(path)
    assert set(frame.columns) == set(gias.GIAS_COLUMNS)


def test_read_gias_csv_rejects_changed_schema(tmp_path):
    path = tmp_path / "gias.csv"
    row = _raw_row()
    row.pop("URN")
    pd.DataFrame([row]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="schema has changed"):
        gias.read_gias_csv(path)


def test_read_gias_csv_falls_back_to_latin1(tmp_path):
    path = tmp_path / "gias.csv"
    pd.DataFrame([_raw_row(EstablishmentName="École")]).to_csv(path, index=False, encoding="latin-1")
    assert gias.read_gias_csv(path).iloc[0]["EstablishmentName"] == "École"


def test_clean_gias_data_filters_invalid_rows_classifies_sector_and_deduplicates():
    rows = [
        _raw_row(),
        _raw_row(URN="100002", **{"EstablishmentName": "Private", "EstablishmentTypeGroup (name)": "Independent schools"}),
        _raw_row(URN="100003", **{"EstablishmentStatus (name)": "Closed"}),
        _raw_row(URN="100004", Easting="0"),
        _raw_row(URN="100001", **{"EstablishmentName": "Latest duplicate"}),
    ]
    result = gias.clean_gias_data(pd.DataFrame(rows), gias.GiasSource(date(2026, 9, 7), "url"))
    assert result["urn"].tolist() == ["100001", "100002"]
    assert result.iloc[0]["school_name"] == "Latest duplicate"
    assert result.iloc[0]["sector"] == "State-funded"
    assert result.iloc[1]["sector"] == "Independent"
    assert result.iloc[0]["postcode"] == "RG22 6AA"
    assert result.iloc[0]["postcode_key"] == "RG226AA"
    assert str(result["easting"].dtype) == "int32"


def test_read_gias_csv_reports_when_all_decoders_fail(monkeypatch, tmp_path):
    error = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(error))
    with pytest.raises(SchoolFinderError, match="Could not decode the GIAS CSV"):
        gias.read_gias_csv(tmp_path / "x.csv")
