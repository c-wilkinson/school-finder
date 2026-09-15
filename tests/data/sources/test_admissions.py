from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import admissions
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
        "school_urn": "100001",
        "entry_year": "2026",
        "school_name": "Example School",
        "school_laestab": "850/4001",
        "school_phase": "Secondary",
        "first_preferences": "240",
        "second_preferences": "120",
        "third_preferences": "80",
        "total_preferences": "520",
        "first_preference_offers": "170",
        "second_preference_offers": "40",
        "third_preference_offers": "20",
        "total_offers": "200",
        "outside_la_preferences": "30",
        "outside_la_offers": "10",
    }
    row.update(overrides)
    return row


def test_discover_admissions_source_and_errors():
    response = Response()
    source = admissions.discover_admissions_source(Session(response=response))
    assert source.name == admissions.ADMISSIONS_SOURCE_NAME
    assert "applications and offers 2026" in source.release_label.lower()
    assert response.closed

    with pytest.raises(SchoolFinderError, match="Could not retrieve DfE school admissions data"):
        admissions.discover_admissions_source(
            Session(error=requests.ConnectionError("offline"))
        )
    with pytest.raises(SchoolFinderError, match="Could not retrieve DfE school admissions data"):
        admissions.discover_admissions_source(
            Session(response=Response(requests.HTTPError("bad")))
        )


def test_read_admissions_history_filters_secondary_aggregates_routes_and_bands(tmp_path: Path):
    path = tmp_path / "admissions.csv"
    pd.DataFrame(
        [
            _row(entry_year="2025", first_preferences="100", total_offers="200"),
            _row(),
            _row(first_preferences="60", total_preferences="100", total_offers="50"),
            _row(
                school_urn="100002",
                school_name="Second School",
                first_preferences="80",
                total_preferences="200",
                total_offers="200",
            ),
            _row(
                school_urn="100003",
                school_name="Third School",
                first_preferences="180",
                total_preferences="300",
                total_offers="200",
            ),
            _row(
                school_urn="100004",
                school_name="Fourth School",
                first_preferences="300",
                total_preferences="400",
                total_offers="200",
            ),
            _row(
                school_urn="100005",
                school_name="Fifth School",
                first_preferences="200",
                total_preferences="300",
                total_offers="200",
            ),
            _row(
                school_urn="999999",
                school_phase="Primary",
                first_preferences="9999",
                total_offers="1",
            ),
        ]
    ).to_csv(path, index=False)

    result = admissions.read_admissions_history(path)
    latest = result[result["admission_year"].eq("2026")].set_index("urn")

    # Split routes for one school/year are combined.
    assert latest.loc["100001", "first_preferences"] == 300
    assert latest.loc["100001", "total_preferences"] == 620
    assert latest.loc["100001", "total_offers"] == 250
    assert latest.loc["100001", "first_preferences_per_offer"] == pytest.approx(1.2)
    assert latest.loc["100001", "school_name"] == "Example School"
    assert latest.loc["100001", "laestab"] == "850/4001"
    assert latest.loc["100001", "admissions_source"] == admissions.ADMISSIONS_SOURCE_NAME
    assert latest.loc["100001", "admissions_source_url"] == admissions.ADMISSIONS_SOURCE_URL

    # Bands are percentile-based within the same entry year.
    assert latest.loc["100002", "admissions_demand_band"] == "Low"
    assert latest.loc["100003", "admissions_demand_band"] == "Moderate"
    assert latest.loc["100001", "admissions_demand_band"] == "High"
    assert latest.loc["100004", "admissions_demand_band"] == "Very high"
    assert "999999" not in latest.index


def test_read_admissions_history_accepts_aliases_and_preserves_missing_metrics(tmp_path: Path):
    path = tmp_path / "aliases.csv"
    pd.DataFrame(
        [
            {
                "URN_GIAS": "1",
                "academic_year": "2026/27",
                "establishmentname": "Alias School",
                "laestab_gias": "8504001",
                "phase_of_education": "State-funded secondary",
                "1st preferences expressed": "100",
                "total offers": "z",
            }
        ]
    ).to_csv(path, index=False)

    result = admissions.read_admissions_history(path).iloc[0]
    assert result["urn"] == "1"
    assert result["admission_year"] == "2026/27"
    assert result["first_preferences"] == 100
    assert pd.isna(result["second_preferences"])
    assert pd.isna(result["total_offers"])
    assert pd.isna(result["first_preferences_per_offer"])
    assert pd.isna(result["admissions_demand_band"])


def test_read_admissions_history_validates_required_columns_and_rows(tmp_path: Path):
    missing_urn = tmp_path / "missing-urn.csv"
    pd.DataFrame([{"entry_year": "2026", "school_phase": "Secondary"}]).to_csv(
        missing_urn, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing school URN"):
        admissions.read_admissions_history(missing_urn)

    missing_year = tmp_path / "missing-year.csv"
    pd.DataFrame([{"school_urn": "1", "school_phase": "Secondary"}]).to_csv(
        missing_year, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing entry year"):
        admissions.read_admissions_history(missing_year)

    missing_phase = tmp_path / "missing-phase.csv"
    pd.DataFrame([{"school_urn": "1", "entry_year": "2026"}]).to_csv(
        missing_phase, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing school phase"):
        admissions.read_admissions_history(missing_phase)

    primary_only = tmp_path / "primary.csv"
    pd.DataFrame([_row(school_phase="Primary")]).to_csv(primary_only, index=False)
    with pytest.raises(SchoolFinderError, match="no secondary-school rows"):
        admissions.read_admissions_history(primary_only)

    no_identity = tmp_path / "no-identity.csv"
    pd.DataFrame([_row(school_urn="")]).to_csv(no_identity, index=False)
    with pytest.raises(SchoolFinderError, match="no identifiable secondary schools"):
        admissions.read_admissions_history(no_identity)


def test_read_admissions_school_uses_latest_entry_year(tmp_path: Path):
    path = tmp_path / "latest.csv"
    pd.DataFrame(
        [
            _row(entry_year="2024/25", first_preferences="100"),
            _row(entry_year="2025/26", first_preferences="150"),
            _row(entry_year="2026/27", first_preferences="200"),
        ]
    ).to_csv(path, index=False)

    row = admissions.read_admissions_school(path).iloc[0]
    assert row["admission_year"] == "2026/27"
    assert row["first_preferences"] == 200
