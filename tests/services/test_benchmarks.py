from pathlib import Path

import pandas as pd
import pytest

from school_finder.errors import SchoolFinderError
from school_finder.services import benchmarks


def _benchmark_frame():
    frame = pd.DataFrame(
        [
            {
                "benchmark_level": "Local authority",
                "benchmark_code": "E10000014",
                "benchmark_name": "Hampshire",
                "performance_year": "202425",
                "attainment8": 46.8,
                "english_maths_grade5_pct": 47.1,
                "english_maths_grade4_pct": 66.2,
                "ebacc_entry_pct": 39.2,
                "ebacc_aps": 4.15,
                "progress8": -0.01,
                "progress8_year": "202324",
                "source": "DfE Key stage 4 performance benchmarks",
                "source_dataset_id": "dataset-id",
            },
            {
                "benchmark_level": "National",
                "benchmark_code": "E92000001",
                "benchmark_name": "England",
                "performance_year": "202425",
                "attainment8": 46.1,
                "english_maths_grade5_pct": 45.4,
                "english_maths_grade4_pct": 64.8,
                "ebacc_entry_pct": 40.5,
                "ebacc_aps": 4.09,
                "progress8": 0.02,
                "progress8_year": "202324",
                "source": "DfE Key stage 4 performance benchmarks",
                "source_dataset_id": "dataset-id",
            },
            {
                "benchmark_level": "Local authority",
                "benchmark_code": "E06000036",
                "benchmark_name": "Bracknell Forest",
                "performance_year": "202425",
                "attainment8": 48.0,
                "english_maths_grade5_pct": 49.0,
                "english_maths_grade4_pct": 67.0,
                "ebacc_entry_pct": 42.0,
                "ebacc_aps": 4.2,
                "progress8": None,
                "progress8_year": None,
                "source": "DfE Key stage 4 performance benchmarks",
                "source_dataset_id": "dataset-id",
            },
        ]
    )
    for column in sorted(benchmarks._REQUIRED_COLUMNS - set(frame.columns)):
        frame[column] = None
    return frame


def _mock_parquet(monkeypatch, frame):
    monkeypatch.setattr(benchmarks, "require_pyarrow", lambda: None)
    monkeypatch.setattr(benchmarks.pd, "read_parquet", lambda *a, **k: frame.copy())


def test_find_relevant_benchmarks_returns_england_and_represented_local_authorities(monkeypatch):
    _mock_parquet(monkeypatch, _benchmark_frame())
    schools = pd.DataFrame(
        {
            "local_authority_code": ["E10000014", "E06000036", "E10000014", None, ""],
        }
    )

    result = benchmarks.find_relevant_benchmarks(Path("benchmarks.parquet"), schools)

    assert result["benchmark_name"].tolist() == [
        "England",
        "Bracknell Forest",
        "Hampshire",
    ]


def test_find_relevant_benchmarks_without_la_column_returns_national_only(monkeypatch):
    _mock_parquet(monkeypatch, _benchmark_frame())
    result = benchmarks.find_relevant_benchmarks(
        Path("benchmarks.parquet"), pd.DataFrame({"urn": ["1"]})
    )
    assert result["benchmark_name"].tolist() == ["England"]


def test_find_relevant_benchmarks_empty_schools_returns_empty_frame(monkeypatch):
    frame = _benchmark_frame()
    _mock_parquet(monkeypatch, frame)
    result = benchmarks.find_relevant_benchmarks(Path("benchmarks.parquet"), pd.DataFrame())
    assert result.empty
    assert list(result.columns) == list(frame.columns)


def test_find_relevant_benchmarks_wraps_parquet_read_errors(monkeypatch):
    monkeypatch.setattr(benchmarks, "require_pyarrow", lambda: None)

    def fail(*args, **kwargs):
        raise OSError("broken")

    monkeypatch.setattr(benchmarks.pd, "read_parquet", fail)
    with pytest.raises(SchoolFinderError, match="Could not read benchmarks.parquet: broken"):
        benchmarks.find_relevant_benchmarks(
            Path("benchmarks.parquet"), pd.DataFrame({"urn": ["1"]})
        )


def test_find_relevant_benchmarks_rejects_old_schema(monkeypatch):
    frame = _benchmark_frame().drop(columns=["source_dataset_id", "progress8_year"])
    _mock_parquet(monkeypatch, frame)
    with pytest.raises(SchoolFinderError, match="older benchmark schema") as exc:
        benchmarks.find_relevant_benchmarks(
            Path("benchmarks.parquet"), pd.DataFrame({"urn": ["1"]})
        )
    assert "progress8_year" in str(exc.value)
    assert "source_dataset_id" in str(exc.value)


def test_benchmark_results_from_frame_maps_models_and_missing_values():
    frame = _benchmark_frame().iloc[[0, 2]].copy()
    result = benchmarks.benchmark_results_from_frame(frame)

    assert len(result) == 2
    assert result[0].label == "Hampshire"
    assert result[0].level == "Local authority"
    assert result[0].code == "E10000014"
    assert result[0].source_dataset_id == "dataset-id"
    assert result[0].academics.attainment8 == 46.8
    assert result[0].academics.progress8 == -0.01
    assert result[0].academics.progress8_year == "202324"
    assert result[1].academics.progress8 is None
    assert result[1].academics.progress8_year is None
