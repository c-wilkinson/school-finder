import json
from datetime import date, datetime, timezone

from school_finder.data.manifest import (
    csv_source_manifest, gias_manifest, onspd_manifest, read_manifest,
    source_matches, write_json_atomic,
)
from school_finder.data.sources.common import CsvSource
from school_finder.data.sources.gias import GiasSource
from school_finder.data.sources.onspd import OnspdSource


def test_read_manifest_missing_invalid_non_mapping_and_valid(tmp_path):
    path = tmp_path / "manifest.json"
    assert read_manifest(path) is None
    path.write_text("not json")
    assert read_manifest(path) is None
    path.write_text("[]")
    assert read_manifest(path) is None
    path.write_text('{"schema_version": 3}')
    assert read_manifest(path) == {"schema_version": 3}


def test_write_json_atomic_writes_sorted_pretty_json_and_removes_temp(tmp_path):
    path = tmp_path / "manifest.json"
    write_json_atomic({"b": 1, "a": "é"}, path)
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": "é", "b": 1}
    assert not (tmp_path / ".manifest.json.tmp").exists()


def test_source_manifest_helpers():
    g = gias_manifest(GiasSource(date(2026, 9, 7), "gias-url"))
    assert g["source_date"] == "2026-09-07"
    c = csv_source_manifest(CsvSource("KS4", "ks4-url", "latest"))
    assert c == {"name":"KS4", "release_label":"latest", "download_url":"ks4-url"}
    o = onspd_manifest(OnspdSource("id", "ONS Postcode Directory (August 2026)", date(2026,8,1), datetime(2026,8,2,tzinfo=timezone.utc), "item", "download"))
    assert o["arcgis_item_id"] == "id"
    assert o["modified_at"].endswith("Z")


def test_source_matches_handles_none_missing_and_matching_values():
    expected = {"release":"x", "url":"y"}
    assert not source_matches(None, "ks4", expected, ("release",))
    assert not source_matches({"sources":{}}, "ks4", expected, ("release",))
    manifest = {"sources":{"ks4":{"release":"x", "url":"y"}}}
    assert source_matches(manifest, "ks4", expected, ("release", "url"))
    assert not source_matches(manifest, "ks4", {"release":"z"}, ("release",))
