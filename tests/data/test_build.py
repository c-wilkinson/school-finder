from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from school_finder.config import MANIFEST_SCHEMA_VERSION
from school_finder.data import build
from school_finder.data.sources.common import CsvSource
from school_finder.data.sources.gias import GiasSource
from school_finder.data.sources.onspd import OnspdSource
from school_finder.errors import SchoolFinderError


def _sources(monkeypatch):
    gias = GiasSource(date(2026, 9, 7), "gias-url")
    onspd = OnspdSource("onspd-id", "ONS Postcode Directory (August 2026)", date(2026,8,1), datetime(2026,8,2,tzinfo=timezone.utc), "item-url", "onspd-url")
    ofsted = CsvSource("Ofsted", "ofsted-url", "ofsted-release")
    independent = CsvSource("Independent Ofsted", "ind-url", "ind-release")
    ks4 = CsvSource("KS4", "ks4-url", "ks4-release")
    monkeypatch.setattr(build, "create_session", lambda: object())
    monkeypatch.setattr(build, "discover_latest_gias_source", lambda session: gias)
    monkeypatch.setattr(build, "discover_latest_onspd_source", lambda session, item_id_override=None: onspd)
    monkeypatch.setattr(build, "discover_latest_ofsted_source", lambda session: ofsted)
    monkeypatch.setattr(build, "discover_latest_independent_ofsted_source", lambda session: independent)
    monkeypatch.setattr(build, "discover_ks4_source", lambda session: ks4)
    return gias, onspd, ofsted, independent, ks4


def _disable_pyarrow_guard(monkeypatch):
    monkeypatch.setattr(build, "require_pyarrow", lambda: None)


def _fake_parquet_writes(monkeypatch):
    monkeypatch.setattr(build, "write_parquet_file", lambda frame, path: path.write_bytes(b"parquet"))
    monkeypatch.setattr(build, "parquet_metadata", lambda path: {"rows":1, "bytes":path.stat().st_size, "sha256":"hash", "columns":["x"]})


def test_enrich_school_quality_joins_by_urn_without_dropping_schools():
    schools = pd.DataFrame([{"urn":"1","name":"A"},{"urn":"2","name":"B"}])
    ofsted = pd.DataFrame([{"urn":"1","ofsted_rating":"Good"}])
    performance = pd.DataFrame([{"urn":"2","attainment8":50.0}])
    result = build.enrich_school_quality(schools, ofsted, performance).set_index("urn")
    assert result.loc["1", "ofsted_rating"] == "Good"
    assert result.loc["2", "attainment8"] == 50.0
    assert len(result) == 2


def test_enrich_school_quality_rejects_duplicate_quality_rows():
    schools = pd.DataFrame([{"urn":"1"}])
    duplicate = pd.DataFrame([{"urn":"1"},{"urn":"1"}])
    with pytest.raises(pd.errors.MergeError):
        build.enrich_school_quality(schools, duplicate, pd.DataFrame({"urn":[]}))


def test_build_returns_unchanged_when_every_source_is_current(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    (tmp_path / "schools.parquet").touch()
    (tmp_path / "postcodes.parquet").touch()
    existing = {"schema_version": MANIFEST_SCHEMA_VERSION, "sources":{}, "sentinel":True}
    monkeypatch.setattr(build, "read_manifest", lambda path: existing)
    monkeypatch.setattr(build, "source_matches", lambda *args, **kwargs: True)
    result = build.build_datasets(tmp_path)
    assert result == build.BuildResult(False, False, False, existing)


def test_build_force_rebuilds_and_publishes_both_datasets(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    _fake_parquet_writes(monkeypatch)
    monkeypatch.setattr(build, "read_manifest", lambda path: None)
    monkeypatch.setattr(build, "download_gias_csv", lambda *a, **k: None)
    schools = pd.DataFrame({"urn":[str(i) for i in range(10_000)], "school_name":["S"]*10_000})
    monkeypatch.setattr(build, "read_gias_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_data", lambda raw, source: schools)
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    quality = pd.DataFrame(columns=["urn","ofsted_publication_date","ofsted_inspection_date"])
    monkeypatch.setattr(build, "read_ofsted_quality", lambda path: quality.copy())
    monkeypatch.setattr(build, "read_ks4_quality", lambda path: pd.DataFrame(columns=["urn"]))
    monkeypatch.setattr(build, "download_onspd_zip", lambda *a, **k: None)
    monkeypatch.setattr(build, "clean_onspd_data", lambda path, source: pd.DataFrame({"postcode_key":["RG226SX"]}))
    fixed_now = datetime(2026,9,7,12,0,tzinfo=timezone.utc)
    monkeypatch.setattr(build, "utc_now", lambda: fixed_now)

    result = build.build_datasets(tmp_path, force=True, onspd_item_id="override")

    assert result.schools_updated is True
    assert result.postcodes_updated is True
    assert result.manifest_updated is True
    assert (tmp_path / "schools.parquet").exists()
    assert (tmp_path / "postcodes.parquet").exists()
    assert (tmp_path / "manifest.json").exists()
    assert result.manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert result.manifest["dataset_version"] == "gias-2026-09-07__onspd-2026-08"
    assert result.manifest["generated_at"] == "2026-09-07T12:00:00Z"


def test_build_only_refreshes_postcodes_when_school_sources_are_current(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    _fake_parquet_writes(monkeypatch)
    (tmp_path / "schools.parquet").write_bytes(b"existing")
    (tmp_path / "postcodes.parquet").write_bytes(b"old")
    existing = {"schema_version": MANIFEST_SCHEMA_VERSION, "sources":{}}
    monkeypatch.setattr(build, "read_manifest", lambda path: existing)
    monkeypatch.setattr(build, "source_matches", lambda manifest, name, expected, keys: name != "onspd")
    monkeypatch.setattr(build, "download_onspd_zip", lambda *a, **k: None)
    monkeypatch.setattr(build, "clean_onspd_data", lambda path, source: pd.DataFrame({"postcode_key":["X"]}))
    monkeypatch.setattr(build, "parquet_metadata", lambda path: {"rows":1,"bytes":path.stat().st_size,"sha256":"h","columns":[]})
    result = build.build_datasets(tmp_path)
    assert result.schools_updated is False
    assert result.postcodes_updated is True
    assert (tmp_path / "schools.parquet").read_bytes() == b"existing"


def test_build_only_refreshes_schools_when_postcodes_are_current(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    _fake_parquet_writes(monkeypatch)
    (tmp_path / "schools.parquet").write_bytes(b"old")
    (tmp_path / "postcodes.parquet").write_bytes(b"existing")
    existing = {"schema_version": MANIFEST_SCHEMA_VERSION, "sources":{}}
    monkeypatch.setattr(build, "read_manifest", lambda path: existing)
    monkeypatch.setattr(build, "source_matches", lambda manifest, name, expected, keys: name == "onspd")
    monkeypatch.setattr(build, "download_gias_csv", lambda *a, **k: None)
    schools = pd.DataFrame({"urn":[str(i) for i in range(10_000)]})
    monkeypatch.setattr(build, "read_gias_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_data", lambda raw, source: schools)
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_ofsted_quality", lambda path: pd.DataFrame(columns=["urn","ofsted_publication_date","ofsted_inspection_date"]))
    monkeypatch.setattr(build, "read_ks4_quality", lambda path: pd.DataFrame(columns=["urn"]))
    result = build.build_datasets(tmp_path)
    assert result.schools_updated is True
    assert result.postcodes_updated is False
    assert (tmp_path / "postcodes.parquet").read_bytes() == b"existing"


def test_build_rejects_implausibly_small_gias_result(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    monkeypatch.setattr(build, "read_manifest", lambda path: None)
    monkeypatch.setattr(build, "download_gias_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_gias_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_data", lambda raw, source: pd.DataFrame({"urn":["1"]}))
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_ofsted_quality", lambda path: pd.DataFrame(columns=["urn","ofsted_publication_date","ofsted_inspection_date"]))
    monkeypatch.setattr(build, "read_ks4_quality", lambda path: pd.DataFrame(columns=["urn"]))
    with pytest.raises(SchoolFinderError, match="probably incomplete"):
        build.build_datasets(tmp_path, force=True)
