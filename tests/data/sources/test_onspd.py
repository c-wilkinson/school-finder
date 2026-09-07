import builtins
import io
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from school_finder.data.sources import onspd
from school_finder.errors import SchoolFinderError


def _source():
    return onspd.OnspdSource(
        item_id="abc",
        title="ONS Postcode Directory (August 2026)",
        release_date=date(2026, 8, 1),
        modified_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
        item_url="https://example.test/item",
        download_url="https://example.test/data",
    )


@pytest.mark.parametrize(
    "title,expected",
    [
        ("ONS Postcode Directory (August 2026)", date(2026, 8, 1)),
        ("ONS Postcode Directory (November 2025) for the UK", date(2025, 11, 1)),
        ("ONS Postcode Directory (May 2024) (V2)", date(2024, 5, 1)),
        ("not a release", None),
    ],
)
def test_parse_onspd_release_date(title, expected):
    assert onspd.parse_onspd_release_date(title) == expected


def test_discover_latest_onspd_source_from_override(monkeypatch):
    def fake_fetch(session, url, params=None):
        return {
            "title": "ONS Postcode Directory (August 2026)",
            "type": "CSV Collection",
            "modified": 1786752000000,
        }
    monkeypatch.setattr(onspd, "fetch_json", fake_fetch)
    source = onspd.discover_latest_onspd_source(object(), item_id_override="abc")
    assert source.item_id == "abc"
    assert source.release_date == date(2026, 8, 1)


def test_discover_latest_onspd_source_rejects_bad_override(monkeypatch):
    monkeypatch.setattr(onspd, "fetch_json", lambda *a, **k: {"title":"Wrong", "type":"CSV Collection", "modified":1})
    with pytest.raises(SchoolFinderError, match="not a recognised ONSPD"):
        onspd.discover_latest_onspd_source(object(), item_id_override="bad")


def test_discover_latest_onspd_source_searches_and_selects_latest(monkeypatch):
    def fake_fetch(session, url, params=None):
        if url == onspd.ARCGIS_SEARCH_URL:
            return {"results":[{"id":"old"},{"id":"new"},{"id":"new"}]}
        item = url.rsplit("/", 1)[-1]
        if item == "old":
            return {"title":"ONS Postcode Directory (May 2026)", "type":"CSV Collection", "modified":1000}
        return {"title":"ONS Postcode Directory (August 2026)", "type":"CSV Collection", "modified":900}
    monkeypatch.setattr(onspd, "fetch_json", fake_fetch)
    source = onspd.discover_latest_onspd_source(object())
    assert source.item_id == "new"


def test_discover_latest_onspd_source_errors_without_candidates(monkeypatch):
    monkeypatch.setattr(onspd, "fetch_json", lambda *a, **k: {"results":[]} if a[1] == onspd.ARCGIS_SEARCH_URL else {})
    with pytest.raises(SchoolFinderError, match="Could not discover"):
        onspd.discover_latest_onspd_source(object())


def test_download_onspd_zip_accepts_zip(tmp_path, monkeypatch):
    destination = tmp_path / "onspd.zip"
    def fake_download(session, url, dest, minimum_size):
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("x.csv", "a,b\n1,2\n")
    monkeypatch.setattr(onspd, "stream_download", fake_download)
    onspd.download_onspd_zip(object(), _source(), destination)
    assert destination.exists()


def test_download_onspd_zip_rejects_non_zip(tmp_path, monkeypatch):
    destination = tmp_path / "onspd.zip"
    monkeypatch.setattr(onspd, "stream_download", lambda s,u,d,minimum_size: d.write_text("not zip"))
    with pytest.raises(SchoolFinderError, match="did not return a ZIP"):
        onspd.download_onspd_zip(object(), _source(), destination)
    assert not destination.exists()


def test_match_onspd_fields_recognises_aliases():
    fields = onspd.match_onspd_fields(["PCDS", "DOTERM", "OSEAST1M", "OSNRTH1M", "CTRY", "LAT", "LONG"])
    assert fields["postcode"] == "PCDS"
    assert fields["country_code"] == "CTRY"
    assert fields["latitude"] == "LAT"


def test_detect_onspd_header_finds_header_after_preamble(tmp_path):
    archive_path = tmp_path / "x.zip"
    content = "metadata\nmore metadata\nPCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY\nRG22 6SX,,462000,149000,E92000001\n"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("data.csv", content)
    with zipfile.ZipFile(archive_path) as zf:
        fields, row = onspd.detect_onspd_header(zf, "data.csv")
    assert row == 2
    assert set(onspd.ONSPD_REQUIRED_FIELDS).issubset(fields)


def test_detect_onspd_header_returns_empty_when_unrecognised(tmp_path):
    archive_path = tmp_path / "x.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("data.csv", "a,b\n1,2\n")
    with zipfile.ZipFile(archive_path) as zf:
        assert onspd.detect_onspd_header(zf, "data.csv") == ({}, 0)


def test_select_onspd_members_prefers_multi_csv(tmp_path):
    archive_path = tmp_path / "x.zip"
    header = "PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY\nRG22 6SX,,1,1,E92000001\n"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("single.csv", header)
        zf.writestr("multi_csv/a.csv", header)
        zf.writestr("multi_csv/b.csv", header)
    with zipfile.ZipFile(archive_path) as zf:
        members = onspd.select_onspd_members(zf)
    assert [m[0] for m in members] == ["multi_csv/a.csv", "multi_csv/b.csv"]


def test_select_onspd_members_prefers_largest_full_uk(tmp_path):
    archive_path = tmp_path / "x.zip"
    header = "PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY\nRG22 6SX,,1,1,E92000001\n"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("ONSPD_UK_small.csv", header)
        zf.writestr("ONSPD_UK_large.csv", header + ("X" * 1000))
    with zipfile.ZipFile(archive_path) as zf:
        members = onspd.select_onspd_members(zf)
    assert members[0][0] == "ONSPD_UK_large.csv"


def test_select_onspd_members_errors_with_preview(tmp_path):
    archive_path = tmp_path / "x.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("readme.csv", "bad,header\n1,2\n")
    with zipfile.ZipFile(archive_path) as zf:
        with pytest.raises(SchoolFinderError, match="First CSV samples"):
            onspd.select_onspd_members(zf)


def test_read_onspd_member_filters_to_valid_english_rows(tmp_path):
    archive_path = tmp_path / "x.zip"
    content = (
        "PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY,DOINTR,LAT,LONG\n"
        "RG22 6SX,,462000,149000,E92000001,202001,51.2,-1.1\n"
        "RG22 6SY,202401,462100,149100,England,202001,51.3,-1.2\n"
        "CF10 1AA,,318000,176000,W92000004,202001,51.4,-3.2\n"
        "RG22 6SZ,,0,149200,E92000001,202001,51.5,-1.3\n"
    )
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("data.csv", content)
    fields = onspd.match_onspd_fields(content.splitlines()[0].split(","))
    with zipfile.ZipFile(archive_path) as zf:
        chunks = list(onspd.read_onspd_member(zf, "data.csv", fields, 0, _source()))
    result = pd.concat(chunks, ignore_index=True)
    assert result["postcode_key"].tolist() == ["RG226SX", "RG226SY"]
    assert result["is_current"].tolist() == [True, False]
    assert set(result["country_code"]) == {onspd.ENGLAND_COUNTRY_CODE}


def test_clean_onspd_data_errors_when_no_english_frames(tmp_path, monkeypatch):
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as zf: zf.writestr("x.csv", "x")
    monkeypatch.setattr(onspd, "select_onspd_members", lambda archive: [("x.csv", {}, 0)])
    monkeypatch.setattr(onspd, "read_onspd_member", lambda *a, **k: iter(()))
    with pytest.raises(SchoolFinderError, match="No English postcodes"):
        onspd.clean_onspd_data(path, _source())


def test_clean_onspd_data_rejects_implausibly_small_dataset(tmp_path, monkeypatch):
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as zf: zf.writestr("x.csv", "x")
    frame = pd.DataFrame({"postcode_key":["A"], "postcode":["A"]})
    monkeypatch.setattr(onspd, "select_onspd_members", lambda archive: [("x.csv", {}, 0)])
    monkeypatch.setattr(onspd, "read_onspd_member", lambda *a, **k: iter([frame]))
    with pytest.raises(SchoolFinderError, match="probably incomplete"):
        onspd.clean_onspd_data(path, _source())


def test_clean_onspd_data_deduplicates_and_sorts_when_size_gate_passes(tmp_path, monkeypatch):
    path = tmp_path / "x.zip"
    with zipfile.ZipFile(path, "w") as zf: zf.writestr("x.csv", "x")
    frame = pd.DataFrame({"postcode_key":["B", "A", "A"], "postcode":["B", "A1", "A2"]})
    monkeypatch.setattr(onspd, "select_onspd_members", lambda archive: [("x.csv", {}, 0)])
    monkeypatch.setattr(onspd, "read_onspd_member", lambda *a, **k: iter([frame]))
    real_len = builtins.len
    monkeypatch.setattr(onspd, "len", lambda obj: 1_000_000 if isinstance(obj, pd.DataFrame) else real_len(obj), raising=False)
    result = onspd.clean_onspd_data(path, _source())
    assert result["postcode_key"].tolist() == ["A", "B"]
    assert result.iloc[0]["postcode"] == "A2"


def test_discover_latest_onspd_source_skips_invalid_search_candidate(monkeypatch):
    def fake_fetch(session, url, params=None):
        if url == onspd.ARCGIS_SEARCH_URL:
            return {"results":[{"id":"bad"},{"id":"good"}]}
        item = url.rsplit("/", 1)[-1]
        if item == "bad":
            return {"title":"Wrong", "type":"CSV Collection", "modified":1}
        return {"title":"ONS Postcode Directory (August 2026)", "type":"CSV Collection", "modified":2}
    monkeypatch.setattr(onspd, "fetch_json", fake_fetch)
    assert onspd.discover_latest_onspd_source(object()).item_id == "good"


def test_detect_onspd_header_stops_after_ten_rows(tmp_path):
    archive_path = tmp_path / "x.zip"
    content = "\n".join(["a,b"] * 11 + ["PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY"]) + "\n"
    with zipfile.ZipFile(archive_path, "w") as zf: zf.writestr("data.csv", content)
    with zipfile.ZipFile(archive_path) as zf:
        assert onspd.detect_onspd_header(zf, "data.csv") == ({}, 0)


def test_select_onspd_members_skips_directories_and_non_csv_and_uses_sorted_fallback(tmp_path):
    archive_path = tmp_path / "x.zip"
    header = "PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY\nRG22 6SX,,1,1,E92000001\n"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("folder/", "")
        zf.writestr("notes.txt", "ignore")
        zf.writestr("z_data.csv", header)
        zf.writestr("a_data.csv", header)
    with zipfile.ZipFile(archive_path) as zf:
        members = onspd.select_onspd_members(zf)
    assert [m[0] for m in members] == ["a_data.csv", "z_data.csv"]


def test_select_onspd_members_handles_preview_read_oserror(monkeypatch):
    class FakeRaw:
        def __enter__(self): raise OSError("cannot read")
        def __exit__(self, *args): return False
    class FakeArchive:
        def namelist(self): return ["bad.csv"]
        def open(self, member): return FakeRaw()
    monkeypatch.setattr(onspd, "detect_onspd_header", lambda archive, member: ({}, 0))
    with pytest.raises(SchoolFinderError, match="could not read"):
        onspd.select_onspd_members(FakeArchive())


def test_read_onspd_member_yields_nothing_for_non_english_chunk(tmp_path):
    archive_path = tmp_path / "x.zip"
    content = "PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY\nCF10 1AA,,318000,176000,W92000004\n"
    with zipfile.ZipFile(archive_path, "w") as zf: zf.writestr("data.csv", content)
    fields = onspd.match_onspd_fields(content.splitlines()[0].split(","))
    with zipfile.ZipFile(archive_path) as zf:
        assert list(onspd.read_onspd_member(zf, "data.csv", fields, 0, _source())) == []


def test_read_onspd_member_yields_nothing_when_english_coordinates_invalid(tmp_path):
    archive_path = tmp_path / "x.zip"
    content = "PCDS,DOTERM,OSEAST1M,OSNRTH1M,CTRY\nRG22 6SX,,0,0,E92000001\n"
    with zipfile.ZipFile(archive_path, "w") as zf: zf.writestr("data.csv", content)
    fields = onspd.match_onspd_fields(content.splitlines()[0].split(","))
    with zipfile.ZipFile(archive_path) as zf:
        assert list(onspd.read_onspd_member(zf, "data.csv", fields, 0, _source())) == []


def test_discover_latest_onspd_source_ignores_search_results_without_ids(monkeypatch):
    def fake_fetch(session, url, params=None):
        if url == onspd.ARCGIS_SEARCH_URL:
            return {"results": [None, {}, {"id": "good"}]}
        return {"title":"ONS Postcode Directory (August 2026)", "type":"CSV Collection", "modified":2}
    monkeypatch.setattr(onspd, "fetch_json", fake_fetch)
    assert onspd.discover_latest_onspd_source(object()).item_id == "good"


def test_select_onspd_members_caps_preview_collection_at_twelve(tmp_path):
    archive_path = tmp_path / "x.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        for index in range(13):
            zf.writestr(f"bad_{index:02}.csv", "bad,header\n1,2\n")
    with zipfile.ZipFile(archive_path) as zf:
        with pytest.raises(SchoolFinderError) as exc:
            onspd.select_onspd_members(zf)
    assert str(exc.value).count("bad_") == 12
