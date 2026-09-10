import argparse
import json
import runpy
import sys
from pathlib import Path

import pytest

from school_finder import cli
from school_finder.data.build import BuildResult
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
from school_finder.models.school import SchoolIdentity, SchoolResult
from school_finder.models.search import PostcodeLocation, SchoolSearchRequest, SchoolSearchResult


def _lookup_result(*, current=True, termination=None, with_school=True):
    request = SchoolSearchRequest("SW1A 2AA")
    postcode = PostcodeLocation("SW1A 2AA", 1, 2, current, termination)
    if not with_school:
        return SchoolSearchResult(request, postcode, (), ())
    school = SchoolResult(SchoolIdentity("100001", "Example"))
    flat = ({
        "school_name": "Example",
        "distance_miles": 1.2,
        "sector": "State-funded",
        "establishment_type": "Academy",
        "age_range": "11–16",
        "faith_status": "Non-faith",
        "ofsted_rating": "Good",
        "ofsted_equivalent_rating": "Good",
        "ofsted_inspection_date": "2025-01-01",
        "ofsted_source_school_name": "Example",
        "attainment8": 50.0,
        "progress8": 0.1,
        "progress8_year": "202324",
        "town": "Town",
        "postcode": "RG1 1AA",
        "urn": "100001",
    },)
    return SchoolSearchResult(request, postcode, (school,), flat)


def _lookup_args(**overrides):
    values = dict(
        data_dir=Path("data"),
        postcode="SW1A 2AA",
        limit=20,
        entry_age=11,
        minimum_exit_age=16,
        include_special=False,
        radius_miles=None,
        phase=[],
        sector=[],
        gender=[],
        faith=FaithFilter.ANY,
        selection=SelectionFilter.ANY,
        minimum_ofsted_rating=None,
        minimum_attainment8=None,
        minimum_progress8=None,
        minimum_grade5_english_maths_pct=None,
        minimum_ebacc_aps=None,
        sort=SchoolSortField.DISTANCE,
        descending=False,
        json=False,
        structured_json=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def test_create_parser_build_and_lookup_defaults():
    parser = cli.create_parser()
    build_args = parser.parse_args(["build"])
    assert build_args.command == "build"
    assert build_args.force is False

    lookup = parser.parse_args(["lookup", "SW1A 2AA"])
    assert lookup.limit == 20
    assert lookup.entry_age == 11
    assert lookup.minimum_exit_age == 16
    assert lookup.include_special is False
    assert lookup.radius_miles is None
    assert lookup.phase == []
    assert lookup.sector == []
    assert lookup.gender == []
    assert lookup.faith is FaithFilter.ANY
    assert lookup.selection is SelectionFilter.ANY
    assert lookup.sort is SchoolSortField.DISTANCE
    assert lookup.descending is False


def test_parser_accepts_all_search_filters_case_insensitively():
    parser = cli.create_parser()
    args = parser.parse_args([
        "lookup", "SW1A 2AA",
        "--radius", "7.5",
        "--phase", "secondary",
        "--phase", "ALL_THROUGH",
        "--sector", "STATE_FUNDED",
        "--sector", "independent",
        "--gender", "mixed",
        "--gender", "GIRLS",
        "--faith", "non-faith",
        "--selection", "non_selective",
        "--include-special",
        "--minimum-ofsted", "requires-improvement",
        "--minimum-attainment8", "45",
        "--minimum-progress8", "-0.2",
        "--minimum-grade5-english-maths", "50",
        "--minimum-ebacc-aps", "4.1",
        "--sort", "grade5_english_maths",
        "--descending",
    ])
    assert args.radius_miles == 7.5
    assert args.phase == [SchoolPhase.SECONDARY, SchoolPhase.ALL_THROUGH]
    assert args.sector == [SchoolSector.STATE_FUNDED, SchoolSector.INDEPENDENT]
    assert args.gender == [SchoolGender.MIXED, SchoolGender.GIRLS]
    assert args.faith is FaithFilter.NON_FAITH
    assert args.selection is SelectionFilter.NON_SELECTIVE
    assert args.include_special is True
    assert args.minimum_ofsted_rating is OfstedRating.REQUIRES_IMPROVEMENT
    assert args.minimum_attainment8 == 45
    assert args.minimum_progress8 == -0.2
    assert args.minimum_grade5_english_maths_pct == 50
    assert args.minimum_ebacc_aps == 4.1
    assert args.sort is SchoolSortField.GRADE5_ENGLISH_MATHS
    assert args.descending is True


def test_parser_rejects_invalid_enum_value(capsys):
    parser = cli.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["lookup", "SW1A 2AA", "--faith", "sometimes"])
    assert "invalid value 'sometimes'" in capsys.readouterr().err


def test_parser_rejects_mutually_exclusive_json_flags():
    parser = cli.create_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["lookup", "SW1A 2AA", "--json", "--structured-json"])


def test_run_build_prints_json(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "build_datasets", lambda *a, **k: BuildResult(True, True, True, {"x": 1}))
    args = argparse.Namespace(data_dir=tmp_path, force=False, onspd_item_id=None, json=True)
    assert cli._run_build(args) == 0
    assert json.loads(capsys.readouterr().out) == {"x": 1}


def test_run_build_prints_updated_files(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "build_datasets", lambda *a, **k: BuildResult(True, False, True, {}))
    args = argparse.Namespace(data_dir=tmp_path, force=True, onspd_item_id="id", json=False)
    assert cli._run_build(args) == 0
    out = capsys.readouterr().out
    assert "Updated: schools.parquet" in out
    assert f"Published: {tmp_path / 'manifest.json'}" in out


def test_run_build_prints_no_changes(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "build_datasets", lambda *a, **k: BuildResult(False, False, False, {}))
    args = argparse.Namespace(data_dir=tmp_path, force=False, onspd_item_id=None, json=False)
    cli._run_build(args)
    assert "already current" in capsys.readouterr().out


def test_run_lookup_structured_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "search_schools", lambda *a, **k: _lookup_result())
    cli._run_lookup(_lookup_args(structured_json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["identity"]["name"] == "Example"


def test_run_lookup_flat_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "search_schools", lambda *a, **k: _lookup_result())
    cli._run_lookup(_lookup_args(json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["school_name"] == "Example"


def test_run_lookup_table_output(monkeypatch, capsys):
    monkeypatch.setattr(cli, "search_schools", lambda *a, **k: _lookup_result())
    cli._run_lookup(_lookup_args())
    out = capsys.readouterr().out
    assert "Found 1 schools matching search" in out
    assert "Example" in out
    assert "attainment8" in out


def test_run_lookup_table_handles_no_results(monkeypatch, capsys):
    monkeypatch.setattr(cli, "search_schools", lambda *a, **k: _lookup_result(with_school=False))
    assert cli._run_lookup(_lookup_args()) == 0
    assert "No schools matched" in capsys.readouterr().out


def test_run_lookup_warns_for_terminated_postcode_with_date(monkeypatch, capsys):
    monkeypatch.setattr(cli, "search_schools", lambda *a, **k: _lookup_result(current=False, termination="202001"))
    cli._run_lookup(_lookup_args(json=True))
    assert "marked as terminated in 202001" in capsys.readouterr().err


def test_run_lookup_warns_for_terminated_postcode_without_date(monkeypatch, capsys):
    monkeypatch.setattr(cli, "search_schools", lambda *a, **k: _lookup_result(current=False))
    cli._run_lookup(_lookup_args(json=True))
    assert "marked as terminated;" in capsys.readouterr().err


def test_run_lookup_passes_all_search_request_fields(monkeypatch):
    seen = {}

    def fake(data_dir, request):
        seen["data_dir"] = data_dir
        seen["request"] = request
        return _lookup_result()

    monkeypatch.setattr(cli, "search_schools", fake)
    cli._run_lookup(_lookup_args(
        limit=5,
        entry_age=10,
        minimum_exit_age=18,
        include_special=True,
        radius_miles=6,
        phase=[SchoolPhase.SECONDARY],
        sector=[SchoolSector.STATE_FUNDED],
        gender=[SchoolGender.MIXED],
        faith=FaithFilter.FAITH,
        selection=SelectionFilter.SELECTIVE,
        minimum_ofsted_rating=OfstedRating.GOOD,
        minimum_attainment8=48,
        minimum_progress8=0.1,
        minimum_grade5_english_maths_pct=60,
        minimum_ebacc_aps=4.5,
        sort=SchoolSortField.ATTAINMENT8,
        descending=True,
        json=True,
    ))
    assert seen["data_dir"] == Path("data")
    assert seen["request"] == SchoolSearchRequest(
        postcode="SW1A 2AA",
        limit=5,
        entry_age=10,
        minimum_exit_age=18,
        include_special=True,
        radius_miles=6,
        phases=(SchoolPhase.SECONDARY,),
        sectors=(SchoolSector.STATE_FUNDED,),
        genders=(SchoolGender.MIXED,),
        faith=FaithFilter.FAITH,
        selection=SelectionFilter.SELECTIVE,
        minimum_ofsted_rating=OfstedRating.GOOD,
        minimum_attainment8=48,
        minimum_progress8=0.1,
        minimum_grade5_english_maths_pct=60,
        minimum_ebacc_aps=4.5,
        sort=SchoolSort(SchoolSortField.ATTAINMENT8, SortDirection.DESC),
    )


def test_main_dispatches_build(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["school-finder", "build"])
    monkeypatch.setattr(cli, "_run_build", lambda args: 7)
    assert cli.main() == 7


def test_main_dispatches_lookup(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["school-finder", "lookup", "SW1A 2AA"])
    monkeypatch.setattr(cli, "_run_lookup", lambda args: 8)
    assert cli.main() == 8


@pytest.mark.parametrize("exc", [SchoolFinderError("bad"), OSError("bad"), ImportError("bad"), ValueError("bad")])
def test_main_converts_expected_errors_to_exit_code_one(monkeypatch, capsys, exc):
    monkeypatch.setattr(sys, "argv", ["school-finder", "build"])
    monkeypatch.setattr(cli, "_run_build", lambda args: (_ for _ in ()).throw(exc))
    assert cli.main() == 1
    assert "Error: bad" in capsys.readouterr().err


def test_module_main_exits_with_cli_return_code(monkeypatch):
    monkeypatch.setattr(cli, "main", lambda: 9)
    sys.modules.pop("school_finder.__main__", None)
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("school_finder.__main__", run_name="__main__")
    assert exc.value.code == 9


def test_run_build_prints_postcodes_when_only_postcodes_updated(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "build_datasets", lambda *a, **k: BuildResult(False, True, True, {}))
    args = argparse.Namespace(data_dir=tmp_path, force=False, onspd_item_id=None, json=False)
    cli._run_build(args)
    assert "Updated: postcodes.parquet" in capsys.readouterr().out
