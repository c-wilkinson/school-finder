from pathlib import Path

import pandas as pd
import pytest

from school_finder.errors import SchoolFinderError
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest
from school_finder.services import search as service


def _school_row(**overrides):
    row = {
        "urn": "100001", "school_name": "Example Secondary", "sector": "State-funded",
        "establishment_type": "Academy converter", "phase": "Secondary", "low_age": 11,
        "high_age": 16, "gender": "Mixed", "religious_character": "None",
        "admissions_policy": "Non-selective", "street": "Example Road", "locality": "",
        "address_3": "", "town": "Exampletown", "county": "Hampshire", "postcode": "RG22 6AA",
        "easting": 463000, "northing": 150000, "website": "https://example.test",
        "telephone": "01234567890", "source_date": pd.Timestamp("2026-09-01"),
        "ofsted_rating": "Good", "ofsted_inspection_date": pd.Timestamp("2025-06-11"),
        "ofsted_publication_date": pd.Timestamp("2025-07-01"), "ofsted_safeguarding": "Met",
        "ofsted_inclusion": None, "ofsted_curriculum_teaching": None, "ofsted_achievement": None,
        "ofsted_attendance_behaviour": None, "ofsted_personal_development": None,
        "ofsted_leadership": None, "performance_year": "202425", "attainment8": 50.2,
        "english_maths_grade5_pct": 55.0, "english_maths_grade4_pct": 75.0,
        "ebacc_entry_pct": 40.0, "ebacc_aps": 4.5, "progress8": 0.17,
        "progress8_year": "202324",
    }
    row.update(overrides)
    return row


def test_is_mainstream_excludes_all_non_mainstream_terms_and_keeps_nulls():
    series = pd.Series(["Academy", "Special school", "Pupil Referral Unit", "Alternative Provision", "Secure Unit", "Hospital School", None])
    assert service.is_mainstream(series).tolist() == [True, False, False, False, False, False, True]


def test_build_address_omits_missing_and_blank_parts():
    row = pd.Series({"street":" Road ", "locality":"", "address_3":None, "town":"Town", "county":"County", "postcode":"RG1 1AA"})
    assert service.build_address(row) == "Road, Town, County, RG1 1AA"


def test_find_nearest_schools_filters_age_special_and_sorts_by_distance(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    frame = pd.DataFrame([
        _school_row(urn="1", school_name="Near", easting=462000, northing=149000),
        _school_row(urn="2", school_name="Far", easting=463609.344, northing=149000),
        _school_row(urn="3", school_name="Special", establishment_type="Special school", easting=462100, northing=149000),
        _school_row(urn="4", school_name="Primary", low_age=4, high_age=11, easting=462050, northing=149000),
    ])
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: frame)
    postcode = PostcodeLocation("RG22 6SX", 462000, 149000, True)
    result = service.find_nearest_schools(Path("schools.parquet"), postcode, limit=10, entry_age=11, minimum_exit_age=16, include_special=False)
    assert result["school_name"].tolist() == ["Near", "Far"]
    assert result["distance_miles"].tolist() == [0.0, 1.0]
    assert result.iloc[0]["address"].startswith("Example Road")
    assert result.iloc[0]["age_range"] == "11–16"


def test_find_nearest_schools_can_include_special(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    frame = pd.DataFrame([_school_row(establishment_type="Special school")])
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: frame)
    result = service.find_nearest_schools(Path("x"), PostcodeLocation("X",463000,150000,True), limit=1, entry_age=11, minimum_exit_age=16, include_special=True)
    assert len(result) == 1


def test_find_nearest_schools_wraps_read_errors(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(ValueError("broken")))
    with pytest.raises(SchoolFinderError, match="Could not read"):
        service.find_nearest_schools(Path("x"), PostcodeLocation("X",1,1,True), limit=1, entry_age=11, minimum_exit_age=16, include_special=False)


def test_serialisable_records_formats_datetimes_and_missing_values():
    frame = pd.DataFrame({"when": pd.to_datetime(["2026-09-07", None]), "score":[1.0, float("nan")]})
    records = service.serialisable_records(frame)
    assert records[0]["when"] == "2026-09-07"
    assert records[1]["when"] is None
    assert records[1]["score"] is None


def test_school_results_from_frame_returns_models():
    frame = pd.DataFrame([{"urn":"1", "school_name":"Example", "distance_miles":1.2}])
    result = service.school_results_from_frame(frame)
    assert result[0].identity.name == "Example"
    assert result[0].travel.distance_miles == 1.2


def test_search_schools_rejects_non_positive_limit(tmp_path):
    with pytest.raises(SchoolFinderError, match="limit must be at least 1"):
        service.search_schools(tmp_path, SchoolSearchRequest("RG22 6SX", limit=0))


def test_search_schools_requires_both_datasets(tmp_path):
    (tmp_path / "postcodes.parquet").touch()
    with pytest.raises(SchoolFinderError, match="Datasets are missing"):
        service.search_schools(tmp_path, SchoolSearchRequest("RG22 6SX"))


def test_search_service_returns_application_models(tmp_path: Path, monkeypatch):
    (tmp_path / "postcodes.parquet").touch()
    (tmp_path / "schools.parquet").touch()
    monkeypatch.setattr(service, "lookup_postcode", lambda path, postcode: PostcodeLocation("RG22 6SX",462000,149000,True))
    called = {}
    def fake_find(*args, **kwargs):
        called.update(kwargs)
        return pd.DataFrame([_school_row()])
    monkeypatch.setattr(service, "find_nearest_schools", fake_find)
    request = SchoolSearchRequest("RG22 6SX", limit=10, entry_age=11, minimum_exit_age=18, include_special=True)
    result = service.search_schools(tmp_path, request)
    assert result.request is request
    assert result.postcode.postcode == "RG22 6SX"
    assert result.schools[0].identity.name == "Example Secondary"
    assert result.schools[0].academics.attainment8 == 50.2
    assert result.flat_records[0]["school_name"] == "Example Secondary"
    assert called == {"limit":10, "entry_age":11, "minimum_exit_age":18, "include_special":True}
