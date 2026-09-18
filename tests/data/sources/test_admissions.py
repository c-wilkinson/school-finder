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
        "time_period": "202627",
        "entry_year": "7",
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
            _row(time_period="202526", first_preferences="100", total_offers="200"),
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
    latest = result[result["admission_year"].eq("2026/27")].set_index("urn")

    # Split routes for one school/year are combined.
    assert latest.loc["100001", "first_preferences"] == 300
    assert latest.loc["100001", "total_preferences"] == 620
    assert latest.loc["100001", "total_offers"] == 250
    assert latest.loc["100001", "first_preferences_per_offer"] == pytest.approx(1.2)
    assert latest.loc["100001", "school_name"] == "Example School"
    assert latest.loc["100001", "laestab"] == "8504001"
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
                "entry_year": "7",
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
    assert result["entry_year"] == "7"
    assert result["first_preferences"] == 100
    assert pd.isna(result["second_preferences"])
    assert pd.isna(result["total_offers"])
    assert pd.isna(result["first_preferences_per_offer"])
    assert pd.isna(result["admissions_demand_band"])


def test_read_admissions_history_validates_required_columns_and_rows(tmp_path: Path):
    missing_urn = tmp_path / "missing-urn.csv"
    pd.DataFrame([{"time_period": "202627", "entry_year": "7", "school_phase": "Secondary"}]).to_csv(
        missing_urn, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing school identifier"):
        admissions.read_admissions_history(missing_urn)

    missing_time = tmp_path / "missing-time.csv"
    pd.DataFrame([{"school_urn": "1", "entry_year": "7", "school_phase": "Secondary"}]).to_csv(
        missing_time, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing time period"):
        admissions.read_admissions_history(missing_time)

    missing_entry = tmp_path / "missing-entry.csv"
    pd.DataFrame([{"school_urn": "1", "time_period": "202627", "school_phase": "Secondary"}]).to_csv(
        missing_entry, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing entry year"):
        admissions.read_admissions_history(missing_entry)

    missing_phase = tmp_path / "missing-phase.csv"
    pd.DataFrame([{"school_urn": "1", "time_period": "202627", "entry_year": "7"}]).to_csv(
        missing_phase, index=False
    )
    with pytest.raises(SchoolFinderError, match="missing school phase"):
        admissions.read_admissions_history(missing_phase)

    primary_only = tmp_path / "primary.csv"
    pd.DataFrame([_row(school_phase="Primary")]).to_csv(primary_only, index=False)
    with pytest.raises(SchoolFinderError, match="no secondary-school rows"):
        admissions.read_admissions_history(primary_only)

    no_identity = tmp_path / "no-identity.csv"
    pd.DataFrame([_row(school_urn="", school_laestab="")]).to_csv(no_identity, index=False)
    with pytest.raises(SchoolFinderError, match="no identifiable secondary schools"):
        admissions.read_admissions_history(no_identity)

    no_entry_value = tmp_path / "no-entry-value.csv"
    pd.DataFrame([_row(entry_year="")]).to_csv(no_entry_value, index=False)
    with pytest.raises(SchoolFinderError, match="no identifiable secondary schools"):
        admissions.read_admissions_history(no_entry_value)


def test_read_admissions_school_uses_latest_admissions_year(tmp_path: Path):
    path = tmp_path / "latest.csv"
    pd.DataFrame(
        [
            _row(time_period="202425", first_preferences="100"),
            _row(time_period="202526", first_preferences="150"),
            _row(time_period="202627", first_preferences="200"),
        ]
    ).to_csv(path, index=False)

    row = admissions.read_admissions_school(path).iloc[0]
    assert row["admission_year"] == "2026/27"
    assert row["entry_year"] == "7"
    assert row["first_preferences"] == 200


def test_read_admissions_history_accepts_laestab_without_urn_and_separate_codes(tmp_path: Path):
    path = tmp_path / "laestab-only.csv"
    pd.DataFrame(
        [
            {
                "time_period": "202627",
                "entry_year": "7",
                "Phase": "Secondary",
                "LA": "850",
                "Estab": "4001",
                "School": "LAEstab School",
                "Number of 1st preferences": "220",
                "Number of total offers": "200",
            }
        ]
    ).to_csv(path, index=False)

    row = admissions.read_admissions_history(path).iloc[0]
    assert row["urn"] == ""
    assert row["laestab"] == "8504001"
    assert row["first_preferences"] == 220
    assert row["total_offers"] == 200


def test_resolve_admissions_to_gias_uses_laestab_before_source_urn():
    source = pd.DataFrame(
        [
            {
                "urn": "999999",
                "laestab": "850/4001",
                "school_name": "Historic label",
                "admission_year": "2026/27",
                "entry_year": "7",
                "first_preferences": 220,
                "total_offers": 200,
            }
        ]
    )
    schools = pd.DataFrame(
        [{"urn": "100001", "laestab": "8504001", "school_name": "Current School"}]
    )

    row = admissions.resolve_admissions_to_gias(source, schools).iloc[0]
    assert row["urn"] == "100001"
    assert row["entry_year"] == "7"
    assert row["first_preferences_per_offer"] == pytest.approx(1.1)


def test_resolve_admissions_to_gias_retains_source_urn_without_laestab_lookup():
    source = pd.DataFrame(
        [
            {
                "urn": "100001",
                "admission_year": "2026",
                "first_preferences": 100,
                "total_offers": 100,
            }
        ]
    )
    schools = pd.DataFrame([{"urn": "100001", "school_name": "Current School"}])
    row = admissions.resolve_admissions_to_gias(source, schools).iloc[0]
    assert row["urn"] == "100001"
    assert row["entry_year"] == ""


def test_resolve_admissions_to_gias_does_not_guess_ambiguous_laestab():
    source = pd.DataFrame(
        [
            {
                "urn": "",
                "laestab": "8504001",
                "admission_year": "2026",
                "first_preferences": 100,
                "total_offers": 100,
            }
        ]
    )
    schools = pd.DataFrame(
        [
            {"urn": "1", "laestab": "8504001"},
            {"urn": "2", "laestab": "8504001"},
        ]
    )
    assert admissions.resolve_admissions_to_gias(source, schools).empty


def test_resolve_admissions_to_gias_accepts_frame_without_urn_column():
    source = pd.DataFrame(
        [
            {
                "laestab": "8504001",
                "admission_year": "2026",
                "first_preferences": 120,
                "total_offers": 100,
            }
        ]
    )
    schools = pd.DataFrame([{"urn": "100001", "laestab": "8504001"}])
    row = admissions.resolve_admissions_to_gias(source, schools).iloc[0]
    assert row["urn"] == "100001"


def test_read_admissions_history_accepts_publisher_2026_school_level_headers(tmp_path: Path):
    path = tmp_path / "publisher-2026.csv"
    pd.DataFrame(
        [
            {
                "school_phase": "Secondary",
                "time_period": "202627",
                "entry_year": "7",
                "school_laestab": "8504002",
                "school_name": "The Costello School",
                "school_urn": "138287",
                "times_put_as_1st_preference": "187",
                "times_put_as_2nd_preference": "130",
                "times_put_as_3rd_preference": "90",
                "times_put_as_any_preferred_school": "460",
                "number_1st_preference_offers": "161",
                "number_2nd_preference_offers": "32",
                "number_3rd_preference_offers": "10",
                "total_number_places_offered": "211",
                "all_applications_from_another_LA": "20",
                "offers_to_applicants_from_another_LA": "8",
                "proportion_1stprefs_v_totaloffers": "0.89",
            }
        ]
    ).to_csv(path, index=False)

    row = admissions.read_admissions_history(path).iloc[0]

    assert row["urn"] == "138287"
    assert row["laestab"] == "8504002"
    assert row["admission_year"] == "2026/27"
    assert row["entry_year"] == "7"
    assert row["first_preferences"] == 187
    assert row["second_preferences"] == 130
    assert row["third_preferences"] == 90
    assert row["total_preferences"] == 460
    assert row["first_preference_offers"] == 161
    assert row["second_preference_offers"] == 32
    assert row["third_preference_offers"] == 10
    assert row["total_offers"] == 211
    assert row["outside_la_preferences"] == 20
    assert row["outside_la_offers"] == 8
    assert row["first_preferences_per_offer"] == pytest.approx(187 / 211)


def test_read_admissions_history_keeps_time_period_and_entry_point_separate(tmp_path: Path):
    path = tmp_path / "separate-year-and-entry.csv"
    pd.DataFrame(
        [
            _row(time_period="202526", entry_year="7", first_preferences="100", total_offers="100"),
            _row(time_period="202627", entry_year="7", first_preferences="120", total_offers="100"),
            _row(time_period="202627", entry_year="9", first_preferences="60", total_offers="50"),
        ]
    ).to_csv(path, index=False)

    result = admissions.read_admissions_history(path)

    assert result[["admission_year", "entry_year"]].values.tolist() == [
        ["2025/26", "7"],
        ["2026/27", "7"],
        ["2026/27", "9"],
    ]
    assert result["first_preferences"].tolist() == [100, 120, 60]


def test_read_admissions_school_prefers_year_7_when_latest_period_has_multiple_entry_points(tmp_path: Path):
    path = tmp_path / "latest-entry-point.csv"
    pd.DataFrame(
        [
            _row(time_period="202627", entry_year="9", first_preferences="90"),
            _row(time_period="202627", entry_year="7", first_preferences="180"),
        ]
    ).to_csv(path, index=False)

    row = admissions.read_admissions_school(path).iloc[0]

    assert row["admission_year"] == "2026/27"
    assert row["entry_year"] == "7"
    assert row["first_preferences"] == 180


def test_read_admissions_school_uses_other_entry_point_when_no_year_7_or_9_exists(tmp_path: Path):
    path = tmp_path / "other-entry-point.csv"
    pd.DataFrame([_row(time_period="202627", entry_year="12", first_preferences="42")]).to_csv(
        path, index=False
    )

    row = admissions.read_admissions_school(path).iloc[0]

    assert row["entry_year"] == "12"
    assert row["first_preferences"] == 42


def test_read_admissions_history_rejects_unrecognised_core_metric_schema(tmp_path: Path):
    path = tmp_path / "schema-drift.csv"
    pd.DataFrame(
        [
            {
                "school_phase": "Secondary",
                "time_period": "202627",
                "entry_year": "7",
                "school_laestab": "8504002",
                "school_name": "The Costello School",
                "school_urn": "138287",
                "mystery_first_choices": "187",
                "mystery_places": "211",
            }
        ]
    ).to_csv(path, index=False)

    with pytest.raises(SchoolFinderError, match="publisher schema may have changed"):
        admissions.read_admissions_history(path)
