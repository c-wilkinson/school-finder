from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from school_finder.config import MANIFEST_SCHEMA_VERSION
from school_finder.data import build
from school_finder.data.sources.common import CsvSource
from school_finder.data.sources.gias import GiasLinksSource, GiasSource
from school_finder.data.sources.onspd import OnspdSource
from school_finder.errors import SchoolFinderError


def _sources(monkeypatch):
    gias = GiasSource(date(2026, 9, 7), "gias-url")
    gias_links = GiasLinksSource(date(2026, 9, 7), "gias-links-url")
    onspd = OnspdSource("onspd-id", "ONS Postcode Directory (August 2026)", date(2026,8,1), datetime(2026,8,2,tzinfo=timezone.utc), "item-url", "onspd-url")
    ofsted = CsvSource("Ofsted", "ofsted-url", "ofsted-release")
    legacy_ofsted = CsvSource("Legacy Ofsted", "legacy-url", "legacy-release")
    independent = CsvSource("Independent Ofsted", "ind-url", "ind-release")
    ks4 = CsvSource("KS4", "ks4-url", "ks4-release")
    ks4_benchmarks = CsvSource("KS4 benchmarks", "bench-url", "bench-release")
    monkeypatch.setattr(build, "create_session", lambda: object())
    monkeypatch.setattr(build, "discover_latest_gias_source", lambda session: gias)
    monkeypatch.setattr(build, "discover_latest_gias_links_source", lambda session, today=None: gias_links)
    monkeypatch.setattr(build, "discover_latest_onspd_source", lambda session, item_id_override=None: onspd)
    monkeypatch.setattr(build, "discover_latest_ofsted_source", lambda session: ofsted)
    monkeypatch.setattr(build, "discover_latest_legacy_ofsted_source", lambda session: legacy_ofsted)
    monkeypatch.setattr(build, "discover_latest_independent_ofsted_source", lambda session: independent)
    monkeypatch.setattr(build, "discover_ks4_source", lambda session: ks4)
    monkeypatch.setattr(build, "discover_ks4_benchmark_source", lambda session: ks4_benchmarks)
    return gias, gias_links, onspd, ofsted, legacy_ofsted, independent, ks4, ks4_benchmarks


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


def test_combine_ofsted_quality_preserves_legacy_when_current_row_has_no_inspection():
    legacy = pd.DataFrame([
        {
            "urn": "116478",
            "ofsted_rating": "Good",
            "ofsted_inspection_date": pd.Timestamp("2023-09-13"),
            "ofsted_publication_date": pd.Timestamp("2023-11-09"),
        },
        {
            "urn": "145125",
            "ofsted_rating": None,
            "ofsted_inspection_date": pd.Timestamp("2025-04-01"),
            "ofsted_publication_date": pd.Timestamp("2025-05-08"),
        },
    ])
    current = pd.DataFrame([
        {
            "urn": "116478",
            "ofsted_rating": None,
            "ofsted_inspection_date": pd.NaT,
            "ofsted_publication_date": pd.NaT,
        },
        {
            "urn": "145125",
            "ofsted_rating": None,
            "ofsted_inspection_date": pd.NaT,
            "ofsted_publication_date": pd.NaT,
        },
    ])

    result = build.combine_ofsted_quality(legacy, current).set_index("urn")
    assert result.loc["116478", "ofsted_rating"] == "Good"
    assert result.loc["116478", "ofsted_inspection_date"] == pd.Timestamp("2023-09-13")
    assert result.loc["145125", "ofsted_inspection_date"] == pd.Timestamp("2025-04-01")


def test_combine_ofsted_quality_prefers_newer_current_inspection():
    legacy = pd.DataFrame([
        {
            "urn": "1",
            "ofsted_rating": "Good",
            "ofsted_inspection_date": pd.Timestamp("2025-01-01"),
            "ofsted_publication_date": pd.Timestamp("2025-02-01"),
        }
    ])
    current = pd.DataFrame([
        {
            "urn": "1",
            "ofsted_rating": None,
            "ofsted_inspection_date": pd.Timestamp("2026-01-01"),
            "ofsted_publication_date": pd.Timestamp("2026-02-01"),
        }
    ])

    result = build.combine_ofsted_quality(legacy, current).iloc[0]
    assert pd.isna(result["ofsted_rating"])
    assert result["ofsted_inspection_date"] == pd.Timestamp("2026-01-01")


def test_build_returns_unchanged_when_every_source_is_current(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    (tmp_path / "schools.parquet").touch()
    (tmp_path / "postcodes.parquet").touch()
    (tmp_path / "benchmarks.parquet").touch()
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
    monkeypatch.setattr(build, "download_gias_links_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_gias_links_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_links_data", lambda raw, establishments, source: pd.DataFrame(columns=["successor_urn", "predecessor_urn", "predecessor_name"]))
    schools = pd.DataFrame({"urn":[str(i) for i in range(10_000)], "school_name":["S"]*10_000})
    monkeypatch.setattr(build, "read_gias_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_data", lambda raw, source: schools)
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    quality = pd.DataFrame(columns=["urn","ofsted_publication_date","ofsted_inspection_date"])
    monkeypatch.setattr(build, "read_ofsted_quality", lambda path: quality.copy())
    monkeypatch.setattr(build, "read_ks4_quality", lambda path: pd.DataFrame(columns=["urn"]))
    monkeypatch.setattr(
        build,
        "read_ks4_benchmarks",
        lambda path: pd.DataFrame([{"benchmark_level": "National", "benchmark_code": "E92000001"}]),
    )
    monkeypatch.setattr(build, "download_onspd_zip", lambda *a, **k: None)
    monkeypatch.setattr(build, "clean_onspd_data", lambda path, source: pd.DataFrame({"postcode_key":["RG226SX"]}))
    fixed_now = datetime(2026,9,7,12,0,tzinfo=timezone.utc)
    monkeypatch.setattr(build, "utc_now", lambda: fixed_now)

    result = build.build_datasets(tmp_path, force=True, onspd_item_id="override")

    assert result.schools_updated is True
    assert result.postcodes_updated is True
    assert result.benchmarks_updated is True
    assert result.manifest_updated is True
    assert (tmp_path / "schools.parquet").exists()
    assert (tmp_path / "postcodes.parquet").exists()
    assert (tmp_path / "benchmarks.parquet").exists()
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
    (tmp_path / "benchmarks.parquet").write_bytes(b"benchmarks")
    existing = {"schema_version": MANIFEST_SCHEMA_VERSION, "sources":{}}
    monkeypatch.setattr(build, "read_manifest", lambda path: existing)
    monkeypatch.setattr(build, "source_matches", lambda manifest, name, expected, keys: name != "onspd")
    monkeypatch.setattr(build, "download_onspd_zip", lambda *a, **k: None)
    monkeypatch.setattr(build, "clean_onspd_data", lambda path, source: pd.DataFrame({"postcode_key":["X"]}))
    monkeypatch.setattr(build, "parquet_metadata", lambda path: {"rows":1,"bytes":path.stat().st_size,"sha256":"h","columns":[]})
    result = build.build_datasets(tmp_path)
    assert result.schools_updated is False
    assert result.postcodes_updated is True
    assert result.benchmarks_updated is False
    assert (tmp_path / "schools.parquet").read_bytes() == b"existing"
    assert (tmp_path / "benchmarks.parquet").read_bytes() == b"benchmarks"


def test_build_only_refreshes_schools_when_postcodes_are_current(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    _fake_parquet_writes(monkeypatch)
    (tmp_path / "schools.parquet").write_bytes(b"old")
    (tmp_path / "postcodes.parquet").write_bytes(b"existing")
    (tmp_path / "benchmarks.parquet").write_bytes(b"benchmarks")
    existing = {"schema_version": MANIFEST_SCHEMA_VERSION, "sources":{}}
    monkeypatch.setattr(build, "read_manifest", lambda path: existing)
    monkeypatch.setattr(
        build,
        "source_matches",
        lambda manifest, name, expected, keys: name in {"onspd", "ks4_benchmarks"},
    )
    monkeypatch.setattr(build, "download_gias_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "download_gias_links_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_gias_links_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_links_data", lambda raw, establishments, source: pd.DataFrame(columns=["successor_urn", "predecessor_urn", "predecessor_name"]))
    schools = pd.DataFrame({"urn":[str(i) for i in range(10_000)]})
    monkeypatch.setattr(build, "read_gias_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_data", lambda raw, source: schools)
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_ofsted_quality", lambda path: pd.DataFrame(columns=["urn","ofsted_publication_date","ofsted_inspection_date"]))
    monkeypatch.setattr(build, "read_ks4_quality", lambda path: pd.DataFrame(columns=["urn"]))
    result = build.build_datasets(tmp_path)
    assert result.schools_updated is True
    assert result.postcodes_updated is False
    assert result.benchmarks_updated is False
    assert (tmp_path / "postcodes.parquet").read_bytes() == b"existing"
    assert (tmp_path / "benchmarks.parquet").read_bytes() == b"benchmarks"


def test_build_rejects_implausibly_small_gias_result(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    monkeypatch.setattr(build, "read_manifest", lambda path: None)
    monkeypatch.setattr(build, "download_gias_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "download_gias_links_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_gias_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "read_gias_links_csv", lambda path: pd.DataFrame())
    monkeypatch.setattr(build, "clean_gias_links_data", lambda raw, establishments, source: pd.DataFrame(columns=["successor_urn", "predecessor_urn", "predecessor_name"]))
    monkeypatch.setattr(build, "clean_gias_data", lambda raw, source: pd.DataFrame({"urn":["1"], "school_name":["S"]}))
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_ofsted_quality", lambda path: pd.DataFrame(columns=["urn","ofsted_publication_date","ofsted_inspection_date"]))
    monkeypatch.setattr(build, "read_ks4_quality", lambda path: pd.DataFrame(columns=["urn"]))
    with pytest.raises(SchoolFinderError, match="probably incomplete"):
        build.build_datasets(tmp_path, force=True)


def test_build_only_refreshes_benchmarks_when_other_datasets_are_current(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    _fake_parquet_writes(monkeypatch)
    (tmp_path / "schools.parquet").write_bytes(b"schools")
    (tmp_path / "postcodes.parquet").write_bytes(b"postcodes")
    (tmp_path / "benchmarks.parquet").write_bytes(b"old")
    existing = {"schema_version": MANIFEST_SCHEMA_VERSION, "sources": {}}
    monkeypatch.setattr(build, "read_manifest", lambda path: existing)
    monkeypatch.setattr(
        build,
        "source_matches",
        lambda manifest, name, expected, keys: name != "ks4_benchmarks",
    )
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    monkeypatch.setattr(
        build,
        "read_ks4_benchmarks",
        lambda path: pd.DataFrame([{"benchmark_level": "National", "benchmark_code": "E92000001"}]),
    )

    result = build.build_datasets(tmp_path)

    assert result.schools_updated is False
    assert result.postcodes_updated is False
    assert result.benchmarks_updated is True
    assert (tmp_path / "schools.parquet").read_bytes() == b"schools"
    assert (tmp_path / "postcodes.parquet").read_bytes() == b"postcodes"
    assert (tmp_path / "benchmarks.parquet").read_bytes() == b"parquet"
    assert "benchmarks.parquet" in result.manifest["files"]
    assert "ks4_benchmarks" in result.manifest["sources"]


def test_build_rejects_empty_benchmark_result(tmp_path, monkeypatch):
    _disable_pyarrow_guard(monkeypatch)
    _sources(monkeypatch)
    (tmp_path / "schools.parquet").touch()
    (tmp_path / "postcodes.parquet").touch()
    monkeypatch.setattr(build, "read_manifest", lambda path: {"schema_version": MANIFEST_SCHEMA_VERSION, "sources": {}})
    monkeypatch.setattr(
        build,
        "source_matches",
        lambda manifest, name, expected, keys: name != "ks4_benchmarks",
    )
    monkeypatch.setattr(build, "download_csv", lambda *a, **k: None)
    monkeypatch.setattr(build, "read_ks4_benchmarks", lambda path: pd.DataFrame())

    with pytest.raises(SchoolFinderError, match="no usable benchmark rows"):
        build.build_datasets(tmp_path)


def _ofsted_row(urn, rating="Requires improvement", inspection="2023-02-07"):
    return {
        "urn": urn,
        "ofsted_rating": rating,
        "ofsted_inspection_date": pd.Timestamp(inspection),
        "ofsted_publication_date": pd.Timestamp(inspection) + pd.Timedelta(days=30),
        "ofsted_safeguarding": "Yes",
        "ofsted_inclusion": pd.NA,
        "ofsted_curriculum_teaching": rating,
        "ofsted_achievement": pd.NA,
        "ofsted_attendance_behaviour": rating,
        "ofsted_personal_development": "Good",
        "ofsted_leadership": rating,
    }


def test_resolve_ofsted_lineage_uses_current_school_inspection_first():
    schools = pd.DataFrame([{"urn": "2", "school_name": "Current"}])
    links = pd.DataFrame([{"successor_urn": "2", "predecessor_urn": "1", "predecessor_name": "Old"}])
    ofsted = pd.DataFrame([_ofsted_row("1"), _ofsted_row("2", "Good", "2026-01-01")])
    result = build.resolve_ofsted_lineage(schools, links, ofsted).iloc[0]
    assert result["ofsted_rating"] == "Good"
    assert result["ofsted_source_urn"] == "2"
    assert result["ofsted_source_kind"] == "current"
    assert result["ofsted_source_link_depth"] == 0


def test_resolve_ofsted_lineage_inherits_single_predecessor_inspection():
    schools = pd.DataFrame([{"urn": "150839", "school_name": "The Blue Coat School Basingstoke"}])
    links = pd.DataFrame([{"successor_urn": "150839", "predecessor_urn": "116427", "predecessor_name": "Aldworth School"}])
    ofsted = pd.DataFrame([_ofsted_row("116427")])
    result = build.resolve_ofsted_lineage(schools, links, ofsted).iloc[0]
    assert result["urn"] == "150839"
    assert result["ofsted_rating"] == "Requires improvement"
    assert result["ofsted_source_urn"] == "116427"
    assert result["ofsted_source_school_name"] == "Aldworth School"
    assert result["ofsted_source_kind"] == "predecessor"
    assert result["ofsted_source_link_depth"] == 1


def test_resolve_ofsted_lineage_can_walk_linear_predecessor_chain():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Current"}])
    links = pd.DataFrame([
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Middle"},
        {"successor_urn": "2", "predecessor_urn": "1", "predecessor_name": "Original"},
    ])
    result = build.resolve_ofsted_lineage(schools, links, pd.DataFrame([_ofsted_row("1")])).iloc[0]
    assert result["ofsted_source_urn"] == "1"
    assert result["ofsted_source_school_name"] == "Original"
    assert result["ofsted_source_link_depth"] == 2


def test_resolve_ofsted_lineage_does_not_guess_across_multiple_predecessors():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Merged"}])
    links = pd.DataFrame([
        {"successor_urn": "3", "predecessor_urn": "1", "predecessor_name": "One"},
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Two"},
    ])
    result = build.resolve_ofsted_lineage(
        schools, links, pd.DataFrame([_ofsted_row("1"), _ofsted_row("2", "Good")])
    )
    assert result.empty


def test_resolve_ofsted_lineage_stops_on_cycle():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Current"}])
    links = pd.DataFrame([
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Two"},
        {"successor_urn": "2", "predecessor_urn": "3", "predecessor_name": "Current"},
    ])
    result = build.resolve_ofsted_lineage(schools, links, pd.DataFrame([_ofsted_row("9")]))
    assert result.empty


def test_resolve_ofsted_lineage_handles_empty_links_and_duplicate_or_invalid_edges():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Current"}])
    own = build.resolve_ofsted_lineage(
        schools,
        pd.DataFrame(columns=["successor_urn", "predecessor_urn", "predecessor_name"]),
        pd.DataFrame([_ofsted_row("3", "Good")]),
    )
    assert own.iloc[0]["ofsted_source_kind"] == "current"

    links = pd.DataFrame([
        {"successor_urn": "", "predecessor_urn": "2", "predecessor_name": ""},
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": ""},
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": ""},
    ])
    inherited = build.resolve_ofsted_lineage(
        schools, links, pd.DataFrame([_ofsted_row("2")])
    )
    assert inherited.iloc[0]["ofsted_source_urn"] == "2"


def _performance_row(
    urn,
    *,
    attainment8=50.0,
    progress8=0.2,
    progress8_year="202324",
    performance_year="202425",
):
    return {
        "urn": urn,
        "performance_year": performance_year,
        "attainment8": attainment8,
        "english_maths_grade5_pct": 50.0,
        "english_maths_grade4_pct": 70.0,
        "ebacc_entry_pct": 30.0,
        "ebacc_aps": 4.0,
        "progress8": progress8,
        "progress8_year": progress8_year,
    }


def test_resolve_progress8_lineage_keeps_current_school_value():
    schools = pd.DataFrame([{"urn": "2", "school_name": "Current"}])
    links = pd.DataFrame([
        {"successor_urn": "2", "predecessor_urn": "1", "predecessor_name": "Old"}
    ])
    performance = pd.DataFrame([
        _performance_row("1", progress8=-0.5),
        _performance_row("2", progress8=0.3),
    ])

    result = build.resolve_progress8_lineage(schools, links, performance).iloc[0]

    assert result["progress8"] == 0.3
    assert result["progress8_source_urn"] == "2"
    assert result["progress8_source_school_name"] == "Current"
    assert result["progress8_source_kind"] == "current"
    assert result["progress8_source_link_depth"] == 0


def test_resolve_progress8_lineage_inherits_only_missing_progress8():
    schools = pd.DataFrame([
        {"urn": "150839", "school_name": "The Blue Coat School Basingstoke"}
    ])
    links = pd.DataFrame([
        {
            "successor_urn": "150839",
            "predecessor_urn": "116427",
            "predecessor_name": "Aldworth School",
        }
    ])
    performance = pd.DataFrame([
        _performance_row(
            "150839",
            attainment8=33.1,
            progress8=pd.NA,
            progress8_year=pd.NA,
        ),
        _performance_row(
            "116427",
            attainment8=35.6,
            progress8=-0.76,
            progress8_year="202324",
            performance_year=pd.NA,
        ),
    ])

    result = build.resolve_progress8_lineage(schools, links, performance).iloc[0]

    assert result["attainment8"] == 33.1
    assert result["progress8"] == -0.76
    assert result["progress8_year"] == "202324"
    assert result["progress8_source_urn"] == "116427"
    assert result["progress8_source_school_name"] == "Aldworth School"
    assert result["progress8_source_kind"] == "predecessor"
    assert result["progress8_source_link_depth"] == 1


def test_resolve_progress8_lineage_walks_linear_chain():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Current"}])
    links = pd.DataFrame([
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Middle"},
        {"successor_urn": "2", "predecessor_urn": "1", "predecessor_name": "Original"},
    ])
    performance = pd.DataFrame([_performance_row("1", progress8=-0.4)])

    result = build.resolve_progress8_lineage(schools, links, performance).iloc[0]

    assert result["progress8"] == -0.4
    assert result["progress8_source_urn"] == "1"
    assert result["progress8_source_school_name"] == "Original"
    assert result["progress8_source_link_depth"] == 2


def test_resolve_progress8_lineage_does_not_guess_across_multiple_predecessors():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Merged"}])
    links = pd.DataFrame([
        {"successor_urn": "3", "predecessor_urn": "1", "predecessor_name": "One"},
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Two"},
    ])
    performance = pd.DataFrame([
        _performance_row("1", progress8=-0.4),
        _performance_row("2", progress8=0.4),
    ])

    result = build.resolve_progress8_lineage(schools, links, performance).iloc[0]

    assert pd.isna(result["progress8"])
    assert result["progress8_source_urn"] is None
    assert result["progress8_source_kind"] is None


def test_resolve_progress8_lineage_stops_on_cycle_and_handles_bad_edges():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Current"}])
    links = pd.DataFrame([
        {"successor_urn": "", "predecessor_urn": "9", "predecessor_name": "Ignored"},
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": ""},
        {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": ""},
        {"successor_urn": "2", "predecessor_urn": "3", "predecessor_name": "Current"},
    ])

    result = build.resolve_progress8_lineage(
        schools, links, pd.DataFrame([_performance_row("9")])
    ).iloc[0]

    assert pd.isna(result["progress8"])
    assert result["progress8_source_school_name"] is None


def test_enrich_school_quality_resolves_progress8_lineage_without_overwriting_current_metrics():
    schools = pd.DataFrame([
        {"urn": "2", "school_name": "Current"},
    ])
    links = pd.DataFrame([
        {"successor_urn": "2", "predecessor_urn": "1", "predecessor_name": "Old"}
    ])
    performance = pd.DataFrame([
        _performance_row("2", attainment8=52.0, progress8=pd.NA),
        _performance_row("1", attainment8=40.0, progress8=-0.25),
    ])
    ofsted = pd.DataFrame(columns=["urn", *build.OFSTED_QUALITY_COLUMNS])

    result = build.enrich_school_quality(
        schools, ofsted, performance, links=links
    ).iloc[0]

    assert result["attainment8"] == 52.0
    assert result["progress8"] == -0.25
    assert result["progress8_source_kind"] == "predecessor"
