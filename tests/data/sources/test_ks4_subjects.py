from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import ks4_subjects
from school_finder.errors import SchoolFinderError


class Response:
    def __init__(self, error=None):
        self.error = error
        self.closed = False

    def raise_for_status(self):
        if self.error:
            raise self.error

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


def _row(**overrides):
    row = {
        "time_period": "202425",
        "geographic_level": "School",
        "school_urn": "100001",
        "qualification_type": "GCSE",
        "qualification_detailed": "GCSE (9-1) Full Course",
        "grade_structure": "9 / 8 / 7 / 6 / 5 / 4 / 3 / 2 / 1 / U / X",
        "subject": "Computing",
        "subject_discount_group": "Computer Science",
        "grade": "5",
        "number_achieving": "2",
    }
    row.update(overrides)
    return row


def test_discover_subject_source_checks_endpoint_and_wraps_errors():
    response = Response()
    source = ks4_subjects.discover_ks4_subject_source(Session(response))
    assert source.url == ks4_subjects.EES_KS4_SUBJECTS_CSV_URL
    assert ks4_subjects.EES_KS4_SUBJECTS_DATASET_ID in source.release_label
    assert response.closed

    with pytest.raises(SchoolFinderError, match="Could not retrieve DfE KS4 subject"):
        ks4_subjects.discover_ks4_subject_source(
            Session(error=requests.ConnectionError("offline"))
        )


def test_read_subjects_aggregates_latest_91_gcse_grades(tmp_path: Path):
    path = tmp_path / "subjects.csv"
    pd.DataFrame(
        [
            _row(time_period="202324", grade="9", number_achieving="99"),
            _row(grade="9", number_achieving="2"),
            _row(grade="7", number_achieving="3"),
            _row(grade="5", number_achieving="4"),
            _row(grade="4", number_achieving="1"),
            _row(grade="3", number_achieving="2"),
            _row(grade="U", number_achieving="1"),
            _row(grade="X", number_achieving="1"),
            _row(geographic_level="Local authority", grade="9", number_achieving="100"),
        ]
    ).to_csv(path, index=False)

    result = ks4_subjects.read_ks4_subjects(path)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["urn"] == "100001"
    assert row["data_year"] == "202425"
    assert row["subject"] == "Computer Science"
    assert row["entries"] == 14
    assert row["grade4_plus"] == 10
    assert row["grade5_plus"] == 9
    assert row["grade7_plus"] == 5
    assert row["grade4_plus_pct"] == pytest.approx(71.429)
    assert row["grade5_plus_pct"] == pytest.approx(64.286)
    assert row["grade7_plus_pct"] == pytest.approx(35.714)
    assert row["source_dataset_id"] == ks4_subjects.EES_KS4_SUBJECTS_DATASET_ID


def test_read_subjects_handles_suppression_non_91_and_fallback_columns(tmp_path: Path):
    path = tmp_path / "subjects.csv"
    pd.DataFrame(
        [
            _row(subject_discount_group="", subject="History", number_achieving="c"),
            _row(
                school_urn="100002",
                subject_discount_group="",
                subject="Other qualification",
                qualification_detailed="",
                qualification_type="Other",
                grade_structure="A / B / C",
                grade="A",
                number_achieving="4",
            ),
        ]
    ).to_csv(path, index=False)
    # Empty subject_discount_group is a real column, so rows with no specific subject are discarded.
    result = ks4_subjects.read_ks4_subjects(path)
    assert result.empty

    path2 = tmp_path / "fallback.csv"
    pd.DataFrame(
        [{
            "time_period": "202425",
            "school_urn": "100003",
            "subject": "History",
            "qualification_type": "Other",
            "grade": "A",
            "number_achieving": "4",
        }]
    ).to_csv(path2, index=False)
    result = ks4_subjects.read_ks4_subjects(path2).iloc[0]
    assert result["subject"] == "History"
    assert result["qualification"] == "Other"
    assert result["entries"] == 4
    assert pd.isna(result["grade4_plus"])


def test_read_subjects_suppressed_grade_makes_totals_unknown(tmp_path: Path):
    path = tmp_path / "subjects.csv"
    pd.DataFrame([
        _row(grade="5", number_achieving="2"),
        _row(grade="4", number_achieving="c"),
    ]).to_csv(path, index=False)
    row = ks4_subjects.read_ks4_subjects(path).iloc[0]
    assert pd.isna(row["entries"])
    assert pd.isna(row["grade5_plus"])


def test_read_subjects_validates_required_columns_and_time(tmp_path: Path):
    missing = tmp_path / "missing.csv"
    pd.DataFrame({"school_urn": ["1"], "time_period": ["202425"]}).to_csv(missing, index=False)
    with pytest.raises(SchoolFinderError, match="missing school, time, subject"):
        ks4_subjects.read_ks4_subjects(missing)

    invalid = tmp_path / "invalid.csv"
    pd.DataFrame([_row(time_period="not-a-year")]).to_csv(invalid, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        ks4_subjects.read_ks4_subjects(invalid)


def test_threshold_count_returns_none_for_suppressed_values():
    assert ks4_subjects._threshold_count(
        pd.Series(["5", "4"]), pd.Series(["2", "c"]), 4
    ) is None
