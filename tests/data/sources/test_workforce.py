from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import workforce
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


def _size_school(**overrides):
    row = {
        "time_period": "202526", "geographic_level": "School", "school_urn": "100001",
        "fte_all_teachers": "60", "fte_classroom_teachers": "50", "fte_teaching_assistants": "12",
        "fte_all_support_staff": "30", "fte_all_teachers_without_qts": "2", "percent_pt_teacher": "20",
    }
    row.update(overrides)
    return row


def _ratio_school(**overrides):
    row = {
        "time_period": "202526", "geographic_level": "School", "school_urn": "100001",
        "pupils_fte": "1000", "qualified_teachers_fte": "58",
        "pupil_to_qual_teacher_ratio": "17.2", "pupil_to_qual_unqual_teacher_ratio": "16.7",
        "pupil_to_adult_ratio": "11.1",
    }
    row.update(overrides)
    return row


def _benchmark(**overrides):
    row = {
        "time_period": "202526", "geographic_level": "National",
        "country_code": "E92000001", "country_name": "England", "new_la_code": "", "la_name": "",
        "establishment_type_group": "State-funded secondary",
        **_size_school(), **_ratio_school(),
    }
    # restore benchmark geography overwritten by helpers
    row.update({
        "time_period": "202526", "geographic_level": "National",
        "country_code": "E92000001", "country_name": "England", "new_la_code": "", "la_name": "",
        "establishment_type_group": "State-funded secondary",
    })
    row.update(overrides)
    return row


def test_discover_all_workforce_sources_and_wraps_errors():
    discoverers = [
        (workforce.discover_workforce_school_source, workforce.WORKFORCE_SCHOOL_DATASET_ID),
        (workforce.discover_workforce_ratio_school_source, workforce.WORKFORCE_RATIO_SCHOOL_DATASET_ID),
        (workforce.discover_workforce_benchmark_source, workforce.WORKFORCE_BENCHMARK_DATASET_ID),
        (workforce.discover_workforce_ratio_benchmark_source, workforce.WORKFORCE_RATIO_BENCHMARK_DATASET_ID),
    ]
    for discover, dataset_id in discoverers:
        response = Response()
        source = discover(Session(response))
        assert dataset_id in source.url
        assert response.closed
    with pytest.raises(SchoolFinderError, match="school workforce school-level"):
        workforce.discover_workforce_school_source(Session(error=requests.ConnectionError("offline")))
    with pytest.raises(SchoolFinderError, match="pupil-to-teacher ratio benchmark"):
        workforce.discover_workforce_ratio_benchmark_source(Session(response=Response(requests.HTTPError("bad"))))


def test_read_workforce_school_combines_latest_staff_and_ratio_rows(tmp_path: Path):
    size = tmp_path / "size.csv"
    ratio = tmp_path / "ratio.csv"
    pd.DataFrame([
        _size_school(time_period="202425", fte_all_teachers="99"),
        _size_school(),
        _size_school(school_urn="100002", fte_all_teachers="z"),
        _size_school(geographic_level="Local authority", school_urn="9"),
        _size_school(school_urn=""),
    ]).to_csv(size, index=False)
    pd.DataFrame([
        _ratio_school(time_period="202425", pupils_fte="9999"),
        _ratio_school(),
        _ratio_school(school_urn="100003", pupils_fte="500", pupil_to_qual_unqual_teacher_ratio="15"),
        _ratio_school(geographic_level="National", school_urn="9"),
    ]).to_csv(ratio, index=False)

    result = workforce.read_workforce_school(size, ratio).set_index("urn")
    assert set(result.index) == {"100001", "100002", "100003"}
    one = result.loc["100001"]
    assert one["workforce_year"] == "202526"
    assert one["teacher_fte"] == 60
    assert one["classroom_teacher_fte"] == 50
    assert one["teaching_assistant_fte"] == 12
    assert one["support_staff_fte"] == 30
    assert one["teachers_without_qts_fte"] == 2
    assert one["part_time_teacher_pct"] == 20
    assert one["pupil_fte"] == 1000
    assert one["qualified_teacher_fte"] == 58
    assert one["pupil_qualified_teacher_ratio"] == 17.2
    assert one["pupil_teacher_ratio"] == 16.7
    assert one["pupil_adult_ratio"] == 11.1
    assert one["workforce_source_dataset_id"] == workforce.WORKFORCE_SCHOOL_DATASET_ID
    assert one["workforce_ratio_source_dataset_id"] == workforce.WORKFORCE_RATIO_SCHOOL_DATASET_ID
    assert pd.isna(result.loc["100002", "teacher_fte"])
    assert result.loc["100003", "pupil_fte"] == 500


def test_workforce_school_allows_missing_level_and_optional_metrics(tmp_path: Path):
    size = tmp_path / "size.csv"; ratio = tmp_path / "ratio.csv"
    pd.DataFrame([{"time_period": "202526", "school_urn": "1", "fte_all_teachers": "10"}]).to_csv(size, index=False)
    pd.DataFrame([{"time_period": "202526", "school_urn": "1", "pupils_fte": "100"}]).to_csv(ratio, index=False)
    result = workforce.read_workforce_school(size, ratio).iloc[0]
    assert result["teacher_fte"] == 10
    assert result["pupil_fte"] == 100
    assert pd.isna(result["support_staff_fte"])


def test_workforce_school_validation(tmp_path: Path):
    valid_ratio = tmp_path / "valid-ratio.csv"
    pd.DataFrame([_ratio_school()]).to_csv(valid_ratio, index=False)

    missing_urn = tmp_path / "missing-urn.csv"
    pd.DataFrame([{"time_period": "202526"}]).to_csv(missing_urn, index=False)
    with pytest.raises(SchoolFinderError, match="missing school_urn"):
        workforce.read_workforce_school(missing_urn, valid_ratio)

    missing_time = tmp_path / "missing-time.csv"
    pd.DataFrame([{"school_urn": "1"}]).to_csv(missing_time, index=False)
    with pytest.raises(SchoolFinderError, match="missing time_period"):
        workforce.read_workforce_school(missing_time, valid_ratio)

    bad_time = tmp_path / "bad-time.csv"
    pd.DataFrame([{"time_period": "bad", "school_urn": "1"}]).to_csv(bad_time, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        workforce.read_workforce_school(bad_time, valid_ratio)


def test_read_workforce_benchmarks_combines_staff_and_official_ratios(tmp_path: Path):
    size = tmp_path / "size-bench.csv"; ratio = tmp_path / "ratio-bench.csv"
    rows = [
        _benchmark(time_period="202425", fte_all_teachers="99"),
        _benchmark(),
        _benchmark(geographic_level="Local authority", new_la_code="E10000014", la_name="Hampshire", fte_all_teachers="55", pupils_fte="900", pupil_to_qual_unqual_teacher_ratio="16.4"),
        _benchmark(establishment_type_group="State-funded primary", fte_all_teachers="999"),
        _benchmark(geographic_level="Regional", fte_all_teachers="999"),
    ]
    size_columns = [
        "time_period", "geographic_level", "country_code", "country_name", "new_la_code", "la_name", "establishment_type_group",
        "fte_all_teachers", "fte_classroom_teachers", "fte_teaching_assistants", "fte_all_support_staff", "fte_all_teachers_without_qts", "percent_pt_teacher",
    ]
    ratio_columns = [
        "time_period", "geographic_level", "country_code", "country_name", "new_la_code", "la_name", "establishment_type_group",
        "pupils_fte", "qualified_teachers_fte", "pupil_to_qual_teacher_ratio", "pupil_to_qual_unqual_teacher_ratio", "pupil_to_adult_ratio",
    ]
    pd.DataFrame(rows)[size_columns].to_csv(size, index=False)
    pd.DataFrame(rows)[ratio_columns].to_csv(ratio, index=False)

    result = workforce.read_workforce_benchmarks(size, ratio).set_index("benchmark_code")
    eng = result.loc["E92000001"]
    assert eng["benchmark_name"] == "England"
    assert eng["workforce_year"] == "202526"
    assert eng["teacher_fte"] == 60
    assert eng["pupil_fte"] == 1000
    assert eng["pupil_teacher_ratio"] == 16.7
    hampshire = result.loc["E10000014"]
    assert hampshire["benchmark_name"] == "Hampshire"
    assert hampshire["teacher_fte"] == 55
    assert hampshire["pupil_teacher_ratio"] == 16.4


def test_workforce_benchmark_validation(tmp_path: Path):
    ratio = tmp_path / "ratio.csv"
    pd.DataFrame([_benchmark()]).to_csv(ratio, index=False)

    missing_type = tmp_path / "missing-type.csv"
    row = _benchmark(); row.pop("establishment_type_group")
    pd.DataFrame([row]).to_csv(missing_type, index=False)
    with pytest.raises(SchoolFinderError, match="geographic_level or school type"):
        workforce.read_workforce_benchmarks(missing_type, ratio)

    no_secondary = tmp_path / "no-secondary.csv"
    pd.DataFrame([_benchmark(establishment_type_group="State-funded primary")]).to_csv(no_secondary, index=False)
    with pytest.raises(SchoolFinderError, match="no secondary benchmark rows"):
        workforce.read_workforce_benchmarks(no_secondary, ratio)

    bad_identity = tmp_path / "bad-identity.csv"
    row = _benchmark(); row.pop("la_name")
    pd.DataFrame([row]).to_csv(bad_identity, index=False)
    with pytest.raises(SchoolFinderError, match="geography identity columns"):
        workforce.read_workforce_benchmarks(bad_identity, ratio)

    bad_time = tmp_path / "bad-time.csv"
    pd.DataFrame([_benchmark(time_period="bad")]).to_csv(bad_time, index=False)
    with pytest.raises(SchoolFinderError, match="no valid time periods"):
        workforce.read_workforce_benchmarks(bad_time, ratio)


def test_workforce_history_keeps_multiple_school_and_benchmark_years(tmp_path: Path):
    size = tmp_path / "size-history.csv"
    ratio = tmp_path / "ratio-history.csv"
    pd.DataFrame([
        _size_school(time_period="202425", fte_all_teachers="58"),
        _size_school(time_period="202526", fte_all_teachers="60"),
    ]).to_csv(size, index=False)
    pd.DataFrame([
        _ratio_school(time_period="202425", pupil_to_qual_unqual_teacher_ratio="17.1"),
        _ratio_school(time_period="202526", pupil_to_qual_unqual_teacher_ratio="16.7"),
    ]).to_csv(ratio, index=False)

    school = workforce.read_workforce_school_history(size, ratio)
    assert school["history_year"].tolist() == ["202425", "202526"]
    assert school["teacher_fte"].tolist() == [58, 60]
    assert school["pupil_teacher_ratio"].tolist() == [17.1, 16.7]

    size_bench = tmp_path / "size-benchmark-history.csv"
    ratio_bench = tmp_path / "ratio-benchmark-history.csv"
    rows = [
        _benchmark(time_period="202425", fte_all_teachers="58", pupil_to_qual_unqual_teacher_ratio="17.1"),
        _benchmark(time_period="202526", fte_all_teachers="60", pupil_to_qual_unqual_teacher_ratio="16.7"),
        _benchmark(
            time_period="202425",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            fte_all_teachers="55",
            pupil_to_qual_unqual_teacher_ratio="16.9",
        ),
        _benchmark(
            time_period="202526",
            geographic_level="Local authority",
            new_la_code="E10000014",
            la_name="Hampshire",
            fte_all_teachers="56",
            pupil_to_qual_unqual_teacher_ratio="16.4",
        ),
    ]
    size_columns = [
        "time_period", "geographic_level", "country_code", "country_name",
        "new_la_code", "la_name", "establishment_type_group",
        "fte_all_teachers", "fte_classroom_teachers", "fte_teaching_assistants",
        "fte_all_support_staff", "fte_all_teachers_without_qts", "percent_pt_teacher",
    ]
    ratio_columns = [
        "time_period", "geographic_level", "country_code", "country_name",
        "new_la_code", "la_name", "establishment_type_group",
        "pupils_fte", "qualified_teachers_fte", "pupil_to_qual_teacher_ratio",
        "pupil_to_qual_unqual_teacher_ratio", "pupil_to_adult_ratio",
    ]
    pd.DataFrame(rows)[size_columns].to_csv(size_bench, index=False)
    pd.DataFrame(rows)[ratio_columns].to_csv(ratio_bench, index=False)

    benchmarks = workforce.read_workforce_benchmark_history(size_bench, ratio_bench)
    england = benchmarks[benchmarks["benchmark_code"].eq("E92000001")]
    hampshire = benchmarks[benchmarks["benchmark_code"].eq("E10000014")]
    assert england["history_year"].tolist() == ["202425", "202526"]
    assert hampshire["history_year"].tolist() == ["202425", "202526"]
    assert hampshire["pupil_teacher_ratio"].tolist() == [16.9, 16.4]
