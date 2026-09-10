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


def test_discover_latest_gias_links_source_uses_links_extract():
    session = Session([404, 200])
    source = gias.discover_latest_gias_links_source(session, today=date(2026, 9, 7))
    assert source.source_date == date(2026, 9, 6)
    assert source.url.endswith("links_edubasealldata20260906.csv")


def test_download_gias_links_csv_uses_expected_minimum_size(tmp_path, monkeypatch):
    source = gias.GiasLinksSource(date(2026, 9, 7), "https://example.test/links.csv")
    called = {}
    monkeypatch.setattr(
        gias,
        "stream_download",
        lambda s, u, d, minimum_size: called.update(url=u, dest=d, size=minimum_size),
    )
    dest = tmp_path / "links.csv"
    gias.download_gias_links_csv(object(), source, dest)
    assert called == {"url": source.url, "dest": dest, "size": 10_000}


def test_read_gias_csv_preserves_literal_none_for_religious_character(tmp_path):
    path = tmp_path / "gias.csv"
    pd.DataFrame([_raw_row(**{"ReligiousCharacter (name)": "None"})]).to_csv(
        path, index=False
    )
    frame = gias.read_gias_csv(path)
    assert frame.iloc[0]["ReligiousCharacter (name)"] == "None"


def test_clean_gias_data_classifies_faith_status():
    rows = [
        _raw_row(URN="1", **{"ReligiousCharacter (name)": "None"}),
        _raw_row(URN="2", **{"ReligiousCharacter (name)": "Does not apply"}),
        _raw_row(URN="3", **{"ReligiousCharacter (name)": "Church of England"}),
        _raw_row(URN="4", **{"ReligiousCharacter (name)": ""}),
    ]
    result = gias.clean_gias_data(
        pd.DataFrame(rows), gias.GiasSource(date(2026, 9, 7), "url")
    ).set_index("urn")
    assert result.loc["1", "faith_status"] == "Non-faith"
    assert result.loc["2", "faith_status"] == "Non-faith"
    assert result.loc["3", "faith_status"] == "Faith"
    assert result.loc["4", "faith_status"] == "Unknown"


def test_read_gias_links_csv_accepts_expected_schema(tmp_path):
    path = tmp_path / "links.csv"
    pd.DataFrame(
        [{"URN": "150839", "LinkURN": "116427", "LinkName": "Aldworth School", "LinkType": "Predecessor", "LinkEstablishmentDate": "31/05/2024"}]
    ).to_csv(path, index=False)
    frame = gias.read_gias_links_csv(path)
    assert frame.iloc[0]["LinkURN"] == "116427"


def test_read_gias_links_csv_rejects_missing_relationship_columns(tmp_path):
    path = tmp_path / "links.csv"
    pd.DataFrame([{"URN": "1"}]).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="links schema has changed"):
        gias.read_gias_links_csv(path)


def test_clean_gias_links_data_normalises_both_link_directions():
    raw_establishments = pd.DataFrame(
        [
            {"URN": "150839", "EstablishmentName": "The Blue Coat School Basingstoke"},
            {"URN": "116427", "EstablishmentName": "Aldworth School"},
        ]
    )
    raw_links = pd.DataFrame(
        [
            {
                "URN": "150839",
                "LinkURN": "116427",
                "LinkName": "Aldworth School",
                "LinkType": "Predecessor",
                "LinkEstablishmentDate": "31/05/2024",
            },
            {
                "URN": "116427",
                "LinkURN": "150839",
                "LinkName": "The Blue Coat School Basingstoke",
                "LinkType": "Successor",
                "LinkEstablishmentDate": "01/05/2024",
            },
        ]
    )
    result = gias.clean_gias_links_data(
        raw_links,
        raw_establishments,
        gias.GiasLinksSource(date(2026, 9, 7), "url"),
    )
    assert len(result) == 1
    assert result.iloc[0]["successor_urn"] == "150839"
    assert result.iloc[0]["predecessor_urn"] == "116427"
    assert result.iloc[0]["predecessor_name"] == "Aldworth School"


def test_read_gias_links_csv_reports_when_all_decoders_fail(monkeypatch, tmp_path):
    error = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: (_ for _ in ()).throw(error))
    with pytest.raises(SchoolFinderError, match="Could not decode the GIAS links CSV"):
        gias.read_gias_links_csv(tmp_path / "x.csv")


def test_clean_gias_links_data_rejects_missing_required_fields():
    with pytest.raises(SchoolFinderError, match="missing URN/link relationship fields"):
        gias.clean_gias_links_data(
            pd.DataFrame([{"URN": "1"}]),
            pd.DataFrame(),
            gias.GiasLinksSource(date(2026, 9, 7), "url"),
        )


def test_clean_gias_links_data_ignores_invalid_unknown_and_self_links():
    raw_links = pd.DataFrame([
        {"URN": "", "LinkURN": "2", "LinkType": "Predecessor"},
        {"URN": "1", "LinkURN": "1", "LinkType": "Predecessor"},
        {"URN": "1", "LinkURN": "2", "LinkType": "Unrelated"},
    ])
    result = gias.clean_gias_links_data(
        raw_links,
        pd.DataFrame(),
        gias.GiasLinksSource(date(2026, 9, 7), "url"),
    )
    assert result.empty
    assert result.columns.tolist() == [
        "successor_urn", "predecessor_urn", "predecessor_name", "link_date", "source_date"
    ]


def test_clean_gias_data_handles_extract_without_optional_religious_ethos():
    raw = pd.DataFrame([_raw_row()]).drop(columns=["ReligiousEthos (name)"])
    result = gias.clean_gias_data(raw, gias.GiasSource(date(2026, 9, 7), "url"))
    assert result.iloc[0]["religious_ethos"] == ""


def test_clean_text_handles_none():
    assert gias._clean_text(None) == ""
