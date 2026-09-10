from pathlib import Path

import pandas as pd
import pytest

from school_finder.errors import SchoolFinderError
from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SchoolSort,
    SchoolSortField,
    SelectionFilter,
    SortDirection,
)
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest
from school_finder.services import search as service


def _school_row(**overrides):
    row = {
        "urn": "100001",
        "school_name": "Example Secondary",
        "sector": "State-funded",
        "establishment_type": "Academy converter",
        "phase": "Secondary",
        "low_age": 11,
        "high_age": 16,
        "gender": "Mixed",
        "religious_character": "Does not apply",
        "religious_ethos": "Does not apply",
        "faith_status": "Non-faith",
        "admissions_policy": "Non-selective",
        "street": "Example Road",
        "locality": "",
        "address_3": "",
        "town": "Exampletown",
        "county": "Hampshire",
        "postcode": "RG22 6AA",
        "local_authority_code": "E10000014",
        "local_authority_name": "Hampshire",
        "easting": 463000,
        "northing": 150000,
        "website": "https://example.test",
        "telephone": "01234567890",
        "source_date": pd.Timestamp("2026-09-01"),
        "ofsted_rating": "Good",
        "ofsted_equivalent_rating": "Good",
        "ofsted_equivalent_basis": "official",
        "ofsted_equivalent_explanation": "Official Ofsted overall effectiveness grade.",
        "ofsted_source_urn": "100001",
        "ofsted_source_school_name": "Example Secondary",
        "ofsted_source_kind": "current",
        "ofsted_source_link_depth": 0,
        "ofsted_inspection_date": pd.Timestamp("2025-06-11"),
        "ofsted_publication_date": pd.Timestamp("2025-07-01"),
        "ofsted_safeguarding": "Met",
        "ofsted_inclusion": None,
        "ofsted_curriculum_teaching": None,
        "ofsted_achievement": None,
        "ofsted_attendance_behaviour": None,
        "ofsted_personal_development": None,
        "ofsted_leadership": None,
        "performance_year": "202425",
        "pupil_count": 200,
        "attainment8": 50.2,
        "attainment8_english": 10.4,
        "attainment8_maths": 9.9,
        "attainment8_ebacc": 13.7,
        "attainment8_open": 16.2,
        "english_maths_grade5_pct": 55.0,
        "english_maths_grade4_pct": 75.0,
        "ebacc_entry_pct": 40.0,
        "ebacc_grade5_pct": 22.0,
        "ebacc_grade4_pct": 35.0,
        "ebacc_aps": 4.5,
        "triple_science_entry_pct": 30.0,
        "multiple_languages_entry_pct": 10.0,
        "gcse_entries_per_pupil": 7.5,
        "qualification_entries_per_pupil": 8.0,
        "progress8_pupil_count": 180,
        "progress8": 0.17,
        "progress8_english": 0.2,
        "progress8_maths": 0.1,
        "progress8_ebacc": 0.15,
        "progress8_open": 0.23,
        "progress8_year": "202324",
        "pastoral_score": 75.0,
        "pastoral_response_count": 40,
        "pastoral_score_coverage_pct": 100.0,
    }
    row.update(overrides)
    return row


def _run_find(monkeypatch, rows, request=None, postcode=None):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: pd.DataFrame(rows))
    monkeypatch.setattr(service, "refresh_parent_view_for_frame", lambda frame: frame)
    return service.find_schools(
        Path("schools.parquet"),
        postcode or PostcodeLocation("SW1A 2AA", 462000, 149000, True),
        request or SchoolSearchRequest("SW1A 2AA"),
    )


def test_is_mainstream_excludes_all_non_mainstream_terms_and_keeps_nulls():
    series = pd.Series([
        "Academy",
        "Special school",
        "Pupil Referral Unit",
        "Alternative Provision",
        "Secure Unit",
        "Hospital School",
        None,
    ])
    assert service.is_mainstream(series).tolist() == [True, False, False, False, False, False, True]


def test_build_address_omits_missing_and_blank_parts():
    row = pd.Series({"street": " Road ", "locality": "", "address_3": None, "town": "Town", "county": "County", "postcode": "RG1 1AA"})
    assert service.build_address(row) == "Road, Town, County, RG1 1AA"


def test_find_schools_filters_age_special_and_defaults_to_distance(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Near", easting=462000, northing=149000),
        _school_row(urn="2", school_name="Far", easting=463609.344, northing=149000),
        _school_row(urn="3", school_name="Special", establishment_type="Special school", easting=462100, northing=149000),
        _school_row(urn="4", school_name="Primary", low_age=4, high_age=11, easting=462050, northing=149000),
    ]
    result = _run_find(monkeypatch, rows, SchoolSearchRequest("SW1A 2AA", limit=10))
    assert result["school_name"].tolist() == ["Near", "Far"]
    assert result["distance_miles"].tolist() == [0.0, 1.0]
    assert result.iloc[0]["address"].startswith("Example Road")
    assert result.iloc[0]["age_range"] == "11–16"


def test_find_schools_can_include_special(monkeypatch):
    result = _run_find(
        monkeypatch,
        [_school_row(establishment_type="Special school")],
        SchoolSearchRequest("X", include_special=True),
        PostcodeLocation("X", 463000, 150000, True),
    )
    assert len(result) == 1


def test_find_schools_wraps_read_errors(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(ValueError("broken")))
    with pytest.raises(SchoolFinderError, match="Could not read"):
        service.find_schools(Path("x"), PostcodeLocation("X", 1, 1, True), SchoolSearchRequest("X"))


def test_radius_filter_is_applied_before_limit(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Inside", easting=462000, northing=149000),
        _school_row(urn="2", school_name="Outside", easting=465218.688, northing=149000),
    ]
    result = _run_find(monkeypatch, rows, SchoolSearchRequest("X", radius_miles=1.5, limit=20))
    assert result["school_name"].tolist() == ["Inside"]


@pytest.mark.parametrize(
    ("search_request", "expected"),
    [
        (SchoolSearchRequest("X", phases=(SchoolPhase.SECONDARY,)), {"Secondary", "Independent", "Girls"}),
        (SchoolSearchRequest("X", sectors=(SchoolSector.INDEPENDENT,)), {"Independent"}),
        (SchoolSearchRequest("X", genders=(SchoolGender.GIRLS,)), {"Girls"}),
    ],
)
def test_categorical_filters(monkeypatch, search_request, expected):
    rows = [
        _school_row(urn="1", school_name="Secondary", phase="Secondary", sector="State-funded", gender="Mixed"),
        _school_row(urn="2", school_name="Independent", phase="Secondary", sector="Independent", gender="Boys"),
        _school_row(urn="3", school_name="Girls", phase="Secondary", sector="State-funded", gender="Girls"),
        _school_row(urn="4", school_name="Primary", phase="Primary", low_age=4, high_age=16, sector="State-funded", gender="Mixed"),
    ]
    result = _run_find(monkeypatch, rows, search_request)
    assert set(result["school_name"]) == expected


def test_multiple_values_in_same_categorical_filter_are_or_conditions(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Mixed", gender="Mixed"),
        _school_row(urn="2", school_name="Girls", gender="Girls"),
        _school_row(urn="3", school_name="Boys", gender="Boys"),
    ]
    request = SchoolSearchRequest("X", genders=(SchoolGender.MIXED, SchoolGender.GIRLS))
    assert set(_run_find(monkeypatch, rows, request)["school_name"]) == {"Mixed", "Girls"}


def test_faith_filters_distinguish_faith_non_faith_and_unknown(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Faith", religious_character="Church of England", faith_status="Faith"),
        _school_row(urn="2", school_name="None", religious_character="None", faith_status="Non-faith"),
        _school_row(urn="3", school_name="Does not apply", religious_character="Does not apply", faith_status="Non-faith"),
        _school_row(urn="4", school_name="Unknown", religious_character=None, faith_status="Unknown"),
    ]
    assert set(_run_find(monkeypatch, rows, SchoolSearchRequest("X", faith=FaithFilter.ANY))["school_name"]) == {"Faith", "None", "Does not apply", "Unknown"}
    assert _run_find(monkeypatch, rows, SchoolSearchRequest("X", faith=FaithFilter.FAITH))["school_name"].tolist() == ["Faith"]
    assert set(_run_find(monkeypatch, rows, SchoolSearchRequest("X", faith=FaithFilter.NON_FAITH))["school_name"]) == {"None", "Does not apply"}


def test_selection_filters(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Selective", admissions_policy="Selective"),
        _school_row(urn="2", school_name="Non-selective", admissions_policy="Non-selective"),
        _school_row(urn="3", school_name="Unknown", admissions_policy="Not applicable"),
    ]
    assert len(_run_find(monkeypatch, rows, SchoolSearchRequest("X", selection=SelectionFilter.ANY))) == 3
    assert _run_find(monkeypatch, rows, SchoolSearchRequest("X", selection=SelectionFilter.SELECTIVE))["school_name"].tolist() == ["Selective"]
    assert _run_find(monkeypatch, rows, SchoolSearchRequest("X", selection=SelectionFilter.NON_SELECTIVE))["school_name"].tolist() == ["Non-selective"]


def test_minimum_ofsted_uses_rating_order_and_excludes_unknown(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Outstanding", ofsted_rating="Outstanding"),
        _school_row(urn="2", school_name="Good", ofsted_rating="Good"),
        _school_row(urn="3", school_name="RI", ofsted_rating="Requires Improvement"),
        _school_row(urn="4", school_name="Inadequate", ofsted_rating="Inadequate"),
        _school_row(urn="5", school_name="Unrated", ofsted_rating=None),
    ]
    result = _run_find(monkeypatch, rows, SchoolSearchRequest("X", minimum_ofsted_rating=OfstedRating.GOOD))
    assert set(result["school_name"]) == {"Outstanding", "Good"}


@pytest.mark.parametrize(
    ("field", "request_kw", "minimum", "expected"),
    [
        ("attainment8", "minimum_attainment8", 50.0, {"Equal", "Above"}),
        ("progress8", "minimum_progress8", 0.0, {"Equal", "Above"}),
        ("english_maths_grade5_pct", "minimum_grade5_english_maths_pct", 50.0, {"Equal", "Above"}),
        ("ebacc_aps", "minimum_ebacc_aps", 4.0, {"Equal", "Above"}),
        ("pastoral_score", "minimum_pastoral_score", 70.0, {"Equal", "Above"}),
    ],
)
def test_numeric_minimum_filters_include_boundary_and_exclude_missing(monkeypatch, field, request_kw, minimum, expected):
    rows = [
        _school_row(urn="1", school_name="Below", **{field: minimum - 0.1}),
        _school_row(urn="2", school_name="Equal", **{field: minimum}),
        _school_row(urn="3", school_name="Above", **{field: minimum + 0.1}),
        _school_row(urn="4", school_name="Missing", **{field: None}),
    ]
    request = SchoolSearchRequest("X", **{request_kw: minimum})
    assert set(_run_find(monkeypatch, rows, request)["school_name"]) == expected


def test_combined_filters_are_and_conditions(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Match", sector="State-funded", gender="Mixed", attainment8=55, ofsted_rating="Good"),
        _school_row(urn="2", school_name="Wrong sector", sector="Independent", gender="Mixed", attainment8=55, ofsted_rating="Good"),
        _school_row(urn="3", school_name="Low attainment", sector="State-funded", gender="Mixed", attainment8=40, ofsted_rating="Good"),
    ]
    request = SchoolSearchRequest(
        "X",
        sectors=(SchoolSector.STATE_FUNDED,),
        genders=(SchoolGender.MIXED,),
        minimum_attainment8=50,
        minimum_ofsted_rating=OfstedRating.GOOD,
    )
    assert _run_find(monkeypatch, rows, request)["school_name"].tolist() == ["Match"]


@pytest.mark.parametrize(
    ("field", "row_field", "low", "high"),
    [
        (SchoolSortField.ATTAINMENT8, "attainment8", 40.0, 60.0),
        (SchoolSortField.PROGRESS8, "progress8", -0.2, 0.4),
        (SchoolSortField.GRADE5_ENGLISH_MATHS, "english_maths_grade5_pct", 40.0, 70.0),
        (SchoolSortField.EBACC_APS, "ebacc_aps", 3.5, 5.2),
        (SchoolSortField.PASTORAL_CARE, "pastoral_score", 55.0, 90.0),
    ],
)
def test_numeric_sort_fields_support_ascending_and_descending(monkeypatch, field, row_field, low, high):
    rows = [
        _school_row(urn="1", school_name="Low", **{row_field: low}),
        _school_row(urn="2", school_name="High", **{row_field: high}),
        _school_row(urn="3", school_name="Missing", **{row_field: None}),
    ]
    asc = SchoolSearchRequest("X", sort=SchoolSort(field, SortDirection.ASC))
    desc = SchoolSearchRequest("X", sort=SchoolSort(field, SortDirection.DESC))
    assert _run_find(monkeypatch, rows, asc)["school_name"].tolist() == ["Low", "High", "Missing"]
    assert _run_find(monkeypatch, rows, desc)["school_name"].tolist() == ["High", "Low", "Missing"]


def test_ofsted_sort_supports_both_directions_and_missing_last(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Good", ofsted_rating="Good"),
        _school_row(urn="2", school_name="Outstanding", ofsted_rating="Outstanding"),
        _school_row(urn="3", school_name="Inadequate", ofsted_rating="Inadequate"),
        _school_row(urn="4", school_name="Missing", ofsted_rating=None),
    ]
    asc = SchoolSearchRequest("X", sort=SchoolSort(SchoolSortField.OFSTED, SortDirection.ASC))
    desc = SchoolSearchRequest("X", sort=SchoolSort(SchoolSortField.OFSTED, SortDirection.DESC))
    assert _run_find(monkeypatch, rows, asc)["school_name"].tolist() == ["Inadequate", "Good", "Outstanding", "Missing"]
    assert _run_find(monkeypatch, rows, desc)["school_name"].tolist() == ["Outstanding", "Good", "Inadequate", "Missing"]


def test_name_sort_and_distance_sort_have_deterministic_ties(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Zulu", easting=462000, northing=149000),
        _school_row(urn="2", school_name="Alpha", easting=462000, northing=149000),
        _school_row(urn="3", school_name="Beta", easting=463609.344, northing=149000),
    ]
    distance = SchoolSearchRequest("X", sort=SchoolSort(SchoolSortField.DISTANCE, SortDirection.ASC))
    assert _run_find(monkeypatch, rows, distance)["school_name"].tolist() == ["Alpha", "Zulu", "Beta"]

    name_desc = SchoolSearchRequest("X", sort=SchoolSort(SchoolSortField.NAME, SortDirection.DESC))
    assert _run_find(monkeypatch, rows, name_desc)["school_name"].tolist() == ["Zulu", "Beta", "Alpha"]


def test_non_distance_sort_uses_distance_then_name_as_tie_breakers(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Zulu", attainment8=50, easting=462000, northing=149000),
        _school_row(urn="2", school_name="Alpha", attainment8=50, easting=462000, northing=149000),
        _school_row(urn="3", school_name="Closer", attainment8=50, easting=462100, northing=149000),
    ]
    request = SchoolSearchRequest("X", sort=SchoolSort(SchoolSortField.ATTAINMENT8, SortDirection.DESC))
    assert _run_find(monkeypatch, rows, request)["school_name"].tolist() == ["Alpha", "Zulu", "Closer"]


def test_limit_is_applied_after_sorting(monkeypatch):
    rows = [
        _school_row(urn="1", school_name="Low", attainment8=40),
        _school_row(urn="2", school_name="High", attainment8=60),
        _school_row(urn="3", school_name="Middle", attainment8=50),
    ]
    request = SchoolSearchRequest("X", limit=2, sort=SchoolSort(SchoolSortField.ATTAINMENT8, SortDirection.DESC))
    assert _run_find(monkeypatch, rows, request)["school_name"].tolist() == ["High", "Middle"]


def test_serialisable_records_formats_datetimes_and_missing_values():
    frame = pd.DataFrame({"when": pd.to_datetime(["2026-09-07", None]), "score": [1.0, float("nan")]})
    records = service.serialisable_records(frame)
    assert records[0]["when"] == "2026-09-07"
    assert records[1]["when"] is None
    assert records[1]["score"] is None


def test_school_results_from_frame_returns_models():
    frame = pd.DataFrame([{"urn": "1", "school_name": "Example", "distance_miles": 1.2}])
    result = service.school_results_from_frame(frame)
    assert result[0].identity.name == "Example"
    assert result[0].travel.distance_miles == 1.2


@pytest.mark.parametrize(
    "present",
    [
        (),
        ("postcodes.parquet",),
        ("postcodes.parquet", "schools.parquet"),
    ],
)
def test_search_schools_requires_all_datasets(tmp_path, present):
    for filename in present:
        (tmp_path / filename).touch()
    with pytest.raises(SchoolFinderError, match="Datasets are missing"):
        service.search_schools(tmp_path, SchoolSearchRequest("SW1A 2AA"))


def test_search_service_returns_application_models_and_passes_request(tmp_path: Path, monkeypatch):
    (tmp_path / "postcodes.parquet").touch()
    (tmp_path / "schools.parquet").touch()
    (tmp_path / "benchmarks.parquet").touch()
    postcode = PostcodeLocation("SW1A 2AA", 462000, 149000, True)
    monkeypatch.setattr(service, "lookup_postcode", lambda path, value: postcode)
    called = {}

    def fake_find(path, resolved, request):
        called.update(path=path, resolved=resolved, request=request)
        row = _school_row(distance_miles=0.88, age_range="11–16", address="Example Road, Exampletown")
        return pd.DataFrame([row])[service.OUTPUT_COLUMNS]

    monkeypatch.setattr(service, "find_schools", fake_find)
    benchmark_called = {}

    def fake_benchmarks(path, schools):
        benchmark_called["path"] = path
        benchmark_called["schools"] = schools
        return pd.DataFrame([
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
                "source": "DfE benchmarks",
                "source_dataset_id": "dataset-id",
            }
        ])

    monkeypatch.setattr(service, "find_relevant_benchmarks", fake_benchmarks)
    request = SchoolSearchRequest("SW1A 2AA", radius_miles=5, minimum_attainment8=45)
    result = service.search_schools(tmp_path, request)
    assert result.request is request
    assert result.postcode is postcode
    assert result.schools[0].identity.name == "Example Secondary"
    assert result.schools[0].academics.attainment8 == 50.2
    assert result.flat_records[0]["school_name"] == "Example Secondary"
    assert called["request"] is request
    assert called["resolved"] is postcode
    assert called["path"] == tmp_path / "schools.parquet"
    assert benchmark_called["path"] == tmp_path / "benchmarks.parquet"
    assert benchmark_called["schools"].iloc[0]["school_name"] == "Example Secondary"
    assert result.benchmarks[0].label == "England"
    assert result.benchmarks[0].academics.attainment8 == 46.1


def test_minimum_ofsted_uses_derived_renewed_eif_equivalent_when_overall_missing(monkeypatch):
    common = dict(
        ofsted_rating=None,
        ofsted_safeguarding="Met",
        ofsted_inclusion="Strong standard",
        ofsted_achievement="Strong standard",
        ofsted_attendance_behaviour="Strong standard",
        ofsted_personal_development="Strong standard",
        ofsted_leadership="Strong standard",
    )
    rows = [
        _school_row(
            urn="1",
            school_name="Strong school",
            ofsted_curriculum_teaching="Strong standard",
            **common,
        ),
        _school_row(
            urn="2",
            school_name="Expected school",
            ofsted_curriculum_teaching="Expected standard",
            **common,
        ),
        _school_row(
            urn="3",
            school_name="Needs attention school",
            ofsted_curriculum_teaching="Needs attention",
            **common,
        ),
    ]
    result = _run_find(
        monkeypatch,
        rows,
        SchoolSearchRequest("X", minimum_ofsted_rating=OfstedRating.GOOD),
    )
    assert set(result["school_name"]) == {"Strong school", "Expected school"}
    equivalents = dict(zip(result["school_name"], result["ofsted_equivalent_rating"], strict=True))
    assert equivalents["Strong school"] == "Outstanding"
    assert equivalents["Expected school"] == "Good"


def test_minimum_ofsted_uses_original_eif_key_judgements_when_overall_missing(monkeypatch):
    rows = [
        _school_row(
            urn="1",
            school_name="Old Good",
            ofsted_rating=None,
            ofsted_safeguarding="Effective",
            ofsted_curriculum_teaching="Good",
            ofsted_attendance_behaviour="Outstanding",
            ofsted_personal_development="Good",
            ofsted_leadership="Good",
        ),
        _school_row(
            urn="2",
            school_name="Old RI",
            ofsted_rating=None,
            ofsted_safeguarding="Effective",
            ofsted_curriculum_teaching="Requires improvement",
            ofsted_attendance_behaviour="Good",
            ofsted_personal_development="Good",
            ofsted_leadership="Good",
        ),
    ]
    result = _run_find(
        monkeypatch,
        rows,
        SchoolSearchRequest("X", minimum_ofsted_rating=OfstedRating.GOOD),
    )
    assert result["school_name"].tolist() == ["Old Good"]
    assert result.iloc[0]["ofsted_equivalent_basis"] == "derived-original-eif"


def test_ofsted_sort_uses_equivalent_rating_not_only_official_overall(monkeypatch):
    renewed = dict(
        ofsted_rating=None,
        ofsted_safeguarding="Met",
        ofsted_inclusion="Strong standard",
        ofsted_curriculum_teaching="Strong standard",
        ofsted_achievement="Strong standard",
        ofsted_attendance_behaviour="Strong standard",
        ofsted_personal_development="Strong standard",
        ofsted_leadership="Strong standard",
    )
    rows = [
        _school_row(urn="1", school_name="Official Good", ofsted_rating="Good"),
        _school_row(urn="2", school_name="Renewed Strong", **renewed),
    ]
    request = SchoolSearchRequest(
        "X",
        sort=SchoolSort(SchoolSortField.OFSTED, SortDirection.DESC),
    )
    result = _run_find(monkeypatch, rows, request)
    assert result["school_name"].tolist() == ["Renewed Strong", "Official Good"]


def test_faith_filter_falls_back_to_religious_character_for_older_dataset():
    frame = pd.DataFrame([
        {"religious_character": "Church of England", "name": "Faith"},
        {"religious_character": "None", "name": "Non-faith"},
        {"religious_character": None, "name": "Unknown"},
    ])
    assert service._filter_faith(frame, FaithFilter.FAITH)["name"].tolist() == ["Faith"]
    assert service._filter_faith(frame, FaithFilter.NON_FAITH)["name"].tolist() == ["Non-faith"]


def test_equivalent_ofsted_explanation_identifies_predecessor_source(monkeypatch):
    row = _school_row(
        urn="150839",
        school_name="The Blue Coat School Basingstoke",
        ofsted_rating="Requires improvement",
        ofsted_source_urn="116427",
        ofsted_source_school_name="Aldworth School",
        ofsted_source_kind="predecessor",
        ofsted_source_link_depth=1,
    )
    result = _run_find(monkeypatch, [row])
    explanation = result.iloc[0]["ofsted_equivalent_explanation"]
    assert "predecessor Aldworth School" in explanation
    assert "URN 116427" in explanation


def test_ofsted_provenance_explanation_handles_missing_predecessor_name():
    row = pd.Series({
        "ofsted_source_kind": "predecessor",
        "ofsted_source_urn": "123",
        "ofsted_source_school_name": pd.NA,
    })
    explanation = service._with_ofsted_provenance(row, "Derived rating.")
    assert "predecessor URN 123" in explanation


def test_preferences_score_and_rank_filtered_candidates_before_limit(monkeypatch):
    from school_finder.models.preferences import SchoolPreferences

    rows = [
        _school_row(
            urn="1",
            school_name="Closest",
            easting=462000,
            northing=149000,
            attainment8=40,
        ),
        _school_row(
            urn="2",
            school_name="Academic",
            easting=465218.688,
            northing=149000,
            attainment8=70,
        ),
        _school_row(
            urn="3",
            school_name="Middle",
            easting=463609.344,
            northing=149000,
            attainment8=50,
        ),
    ]
    request = SchoolSearchRequest(
        "X",
        limit=2,
        preferences=SchoolPreferences(attainment8=1),
    )
    result = _run_find(monkeypatch, rows, request)

    assert result["school_name"].tolist() == ["Academic", "Middle"]
    assert "preference_score" in result.columns
    assert result.iloc[0]["preference_score"] == 100


def test_preferences_with_no_available_weighted_data_rank_missing_scores_last(monkeypatch):
    from school_finder.models.preferences import SchoolPreferences

    rows = [
        _school_row(urn="1", school_name="Rated", ofsted_rating="Good"),
        _school_row(
            urn="2",
            school_name="Unrated",
            ofsted_rating=None,
            ofsted_safeguarding=None,
        ),
    ]
    request = SchoolSearchRequest("X", preferences=SchoolPreferences(ofsted=1))
    result = _run_find(monkeypatch, rows, request)
    assert result["school_name"].tolist() == ["Rated", "Unrated"]
    assert pd.isna(result.iloc[1]["preference_score"])


def test_pastoral_refresh_happens_before_filtering_and_ranking(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(
        pd,
        "read_parquet",
        lambda *a, **k: pd.DataFrame(
            [
                _school_row(urn="1", school_name="Initially missing", pastoral_score=None),
                _school_row(urn="2", school_name="Low", pastoral_score=40.0),
            ]
        ),
    )

    def refresh(frame):
        refreshed = frame.copy()
        refreshed.loc[refreshed["urn"].eq("1"), "pastoral_score"] = 85.0
        refreshed.loc[refreshed["urn"].eq("1"), "pastoral_response_count"] = 80
        return refreshed

    monkeypatch.setattr(service, "refresh_parent_view_for_frame", refresh)
    request = SchoolSearchRequest("X", minimum_pastoral_score=70)
    result = service.find_schools(
        Path("schools.parquet"),
        PostcodeLocation("X", 463000, 150000, True),
        request,
    )
    assert result["school_name"].tolist() == ["Initially missing"]
    assert result.iloc[0]["pastoral_score"] == 85
