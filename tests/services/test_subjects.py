from pathlib import Path

import pandas as pd
import pytest

from school_finder.errors import SchoolFinderError
from school_finder.services import subjects as service


def _row(**overrides):
    row = {
        "urn": "100001",
        "data_year": "202425",
        "subject": "Computer Science",
        "qualification": "GCSE (9-1) Full Course",
        "grade_structure": "9 / 8 / 7 / 6 / 5 / 4 / 3 / 2 / 1 / U / X",
        "entries": 30,
        "grade4_plus": 25,
        "grade4_plus_pct": 83.333,
        "grade5_plus": 20,
        "grade5_plus_pct": 66.667,
        "grade7_plus": 8,
        "grade7_plus_pct": 26.667,
        "source": "DfE subjects",
        "source_dataset_id": "id",
    }
    row.update(overrides)
    return row


def test_get_school_subject_results_reads_and_maps_rows(tmp_path: Path, monkeypatch):
    (tmp_path / "subjects.parquet").touch()
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    called = {}
    def read(*args, **kwargs):
        called["filters"] = kwargs["filters"]
        return pd.DataFrame([_row()])
    monkeypatch.setattr(pd, "read_parquet", read)
    result = service.get_school_subject_results(tmp_path, " 100001 ")
    assert called["filters"] == [("urn", "==", "100001")]
    assert result[0].subject == "Computer Science"
    assert result[0].entries == 30
    assert result[0].to_dict()["grade7_plus_pct"] == 26.667


def test_get_school_subject_results_handles_missing_empty_old_and_read_error(tmp_path: Path, monkeypatch):
    with pytest.raises(SchoolFinderError, match="subjects.parquet is missing"):
        service.get_school_subject_results(tmp_path, "1")

    path = tmp_path / "subjects.parquet"
    path.touch()
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: pd.DataFrame(columns=sorted(service._REQUIRED_COLUMNS)))
    assert service.get_school_subject_results(tmp_path, "1") == ()

    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: pd.DataFrame({"urn": []}))
    with pytest.raises(SchoolFinderError, match="older subject schema"):
        service.get_school_subject_results(tmp_path, "1")

    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(SchoolFinderError, match="Could not read"):
        service.get_school_subject_results(tmp_path, "1")
