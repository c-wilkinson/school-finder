from pathlib import Path

import pandas as pd
import pytest

from school_finder.data.history import BENCHMARK_HISTORY_COLUMNS, SCHOOL_HISTORY_COLUMNS
from school_finder.errors import SchoolFinderError
from school_finder.services import history as history_service


def _school_history():
    return pd.DataFrame(
        [
            {
                "urn": "100001",
                "domain": "academics",
                "year": "202324",
                "metric": "attainment8",
                "value": 50.0,
                "source_urn": "100000",
                "source_school_name": "Old School",
                "source_kind": "predecessor",
                "source_link_depth": 1,
            },
            {
                "urn": "100001",
                "domain": "academics",
                "year": "202425",
                "metric": "attainment8",
                "value": 52.0,
                "source_urn": "100001",
                "source_school_name": "Current School",
                "source_kind": "current",
                "source_link_depth": 0,
            },
        ],
        columns=SCHOOL_HISTORY_COLUMNS,
    )


def _benchmark_history():
    rows = []
    for level, code, name, value in (
        ("National", "E92000001", "England", 47.0),
        ("Local authority", "E10000014", "Hampshire", 49.0),
        ("Local authority", "E99999999", "Elsewhere", 45.0),
    ):
        rows.append(
            {
                "benchmark_level": level,
                "benchmark_code": code,
                "benchmark_name": name,
                "domain": "academics",
                "year": "202425",
                "metric": "attainment8",
                "value": value,
            }
        )
    return pd.DataFrame(rows, columns=BENCHMARK_HISTORY_COLUMNS)


def _touch_files(tmp_path: Path):
    (tmp_path / "history.parquet").touch()
    (tmp_path / "benchmark_history.parquet").touch()


def _mock_reads(monkeypatch, school=None, benchmarks=None):
    school = _school_history() if school is None else school
    benchmarks = _benchmark_history() if benchmarks is None else benchmarks

    def fake_read(path, *, filters=None):
        if path.name == "history.parquet":
            if school.empty:
                return school.copy()
            urn = filters[0][2]
            return school[school["urn"].eq(urn)].copy()
        frame = benchmarks.copy()
        if not filters or frame.empty:
            return frame
        column, _, value = filters[0]
        return frame[frame[column].eq(value)].copy()

    monkeypatch.setattr(history_service, "_read_parquet", fake_read)


def test_get_school_history_returns_school_local_authority_and_england(tmp_path, monkeypatch):
    _touch_files(tmp_path)
    _mock_reads(monkeypatch)

    result = history_service.get_school_history(tmp_path, " 100001 ", "E10000014")

    assert set(result["series"]) == {"School", "Hampshire", "England"}
    school = result[result["series"].eq("School")]
    assert school["year"].tolist() == ["202324", "202425"]
    assert school.iloc[0]["source_kind"] == "predecessor"
    assert "Elsewhere" not in set(result["series"])


def test_get_school_history_without_local_authority_or_rows(tmp_path, monkeypatch):
    _touch_files(tmp_path)
    _mock_reads(monkeypatch)
    result = history_service.get_school_history(tmp_path, "missing")
    assert set(result["series"]) == {"England"}

    _mock_reads(
        monkeypatch,
        school=pd.DataFrame(columns=SCHOOL_HISTORY_COLUMNS),
        benchmarks=pd.DataFrame(columns=BENCHMARK_HISTORY_COLUMNS),
    )
    result = history_service.get_school_history(tmp_path, "100001")
    assert result.empty
    assert list(result.columns) == [
        "domain", "year", "metric", "series", "value", "source_urn",
        "source_school_name", "source_kind", "source_link_depth",
    ]


def test_get_school_history_requires_files_and_current_schema(tmp_path, monkeypatch):
    with pytest.raises(SchoolFinderError, match="trend data"):
        history_service.get_school_history(tmp_path, "100001")

    _touch_files(tmp_path)
    monkeypatch.setattr(
        history_service,
        "_read_parquet",
        lambda path, **kwargs: (
            pd.DataFrame({"urn": ["100001"]})
            if path.name == "history.parquet"
            else _benchmark_history()
        ),
    )
    with pytest.raises(SchoolFinderError, match="older history schema"):
        history_service.get_school_history(tmp_path, "100001")

    monkeypatch.setattr(
        history_service,
        "_read_parquet",
        lambda path, **kwargs: (
            _school_history()
            if path.name == "history.parquet"
            else pd.DataFrame({"benchmark_level": ["National"]})
        ),
    )
    with pytest.raises(SchoolFinderError, match="older history schema"):
        history_service.get_school_history(tmp_path, "100001")


def test_get_school_history_fills_missing_benchmark_names(tmp_path, monkeypatch):
    _touch_files(tmp_path)
    benchmarks = _benchmark_history()
    benchmarks.loc[benchmarks["benchmark_level"].eq("National"), "benchmark_name"] = None
    benchmarks.loc[benchmarks["benchmark_code"].eq("E10000014"), "benchmark_name"] = None
    _mock_reads(monkeypatch, benchmarks=benchmarks)

    result = history_service.get_school_history(tmp_path, "100001", "E10000014")
    assert {"England", "Local authority"}.issubset(set(result["series"]))


def test_read_parquet_wraps_errors(tmp_path, monkeypatch):
    path = tmp_path / "history.parquet"
    monkeypatch.setattr(history_service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(
        history_service.pd,
        "read_parquet",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("broken")),
    )
    with pytest.raises(SchoolFinderError, match="Could not read.*broken"):
        history_service._read_parquet(path, filters=[("urn", "==", "1")])


def test_get_school_history_skips_missing_local_authority_series(tmp_path, monkeypatch):
    _touch_files(tmp_path)
    _mock_reads(monkeypatch)

    result = history_service.get_school_history(tmp_path, "100001", "E00000000")

    assert set(result["series"]) == {"School", "England"}
