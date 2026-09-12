import pandas as pd

from school_finder.data.history import (
    BENCHMARK_HISTORY_COLUMNS,
    SCHOOL_HISTORY_COLUMNS,
    combine_benchmark_history,
    normalise_benchmark_history,
    normalise_school_history,
    resolve_school_history_lineage,
)


def test_normalise_school_history_melts_metrics_and_drops_unusable_rows():
    frame = pd.DataFrame(
        [
            {"urn": " 100001 ", "period": "202324", "attainment8": "51.2", "progress8": "0.2"},
            {"urn": "100001", "period": "202324", "attainment8": "52.0", "progress8": "bad"},
            {"urn": "", "period": "202425", "attainment8": 99, "progress8": 1},
            {"urn": "100002", "period": "", "attainment8": 40, "progress8": 0},
        ]
    )

    result = normalise_school_history(
        frame,
        domain="academics",
        year_column="period",
        metric_columns=("attainment8", "progress8", "missing"),
    )

    assert list(result.columns) == ["urn", "domain", "year", "metric", "value"]
    assert result.to_dict("records") == [
        {"urn": "100001", "domain": "academics", "year": "202324", "metric": "attainment8", "value": 52.0},
        {"urn": "100001", "domain": "academics", "year": "202324", "metric": "progress8", "value": 0.2},
    ]

    assert normalise_school_history(
        pd.DataFrame(), domain="x", year_column="year", metric_columns=("value",)
    ).empty
    assert normalise_school_history(
        pd.DataFrame({"urn": ["1"]}), domain="x", year_column="year", metric_columns=("value",)
    ).empty


def test_normalise_benchmark_history_melts_and_deduplicates():
    frame = pd.DataFrame(
        [
            {"benchmark_level": " National ", "benchmark_code": " E92000001 ", "benchmark_name": " England ", "period": "202324", "attainment8": 47.0},
            {"benchmark_level": "National", "benchmark_code": "E92000001", "benchmark_name": "England", "period": "202324", "attainment8": 48.0},
            {"benchmark_level": "National", "benchmark_code": "", "benchmark_name": "England", "period": "202425", "attainment8": 49.0},
        ]
    )

    result = normalise_benchmark_history(
        frame,
        domain="academics",
        year_column="period",
        metric_columns=("attainment8", "missing"),
    )

    assert list(result.columns) == list(BENCHMARK_HISTORY_COLUMNS)
    assert result.to_dict("records") == [
        {
            "benchmark_level": "National",
            "benchmark_code": "E92000001",
            "benchmark_name": "England",
            "domain": "academics",
            "year": "202324",
            "metric": "attainment8",
            "value": 48.0,
        }
    ]
    assert normalise_benchmark_history(
        pd.DataFrame(), domain="x", year_column="year", metric_columns=("value",)
    ).empty


def test_resolve_school_history_lineage_prefers_current_then_nearest_predecessor():
    schools = pd.DataFrame(
        [
            {"urn": "300", "school_name": "Current Academy"},
            {"urn": "900", "school_name": "Unrelated"},
        ]
    )
    links = pd.DataFrame(
        [
            {"successor_urn": "300", "predecessor_urn": "200", "predecessor_name": "Previous Academy"},
            {"successor_urn": "200", "predecessor_urn": "100", "predecessor_name": "Original School"},
            # Duplicate link should not create ambiguity.
            {"successor_urn": "300", "predecessor_urn": "200", "predecessor_name": "Previous Academy"},
            {"successor_urn": "", "predecessor_urn": "999", "predecessor_name": "Ignored"},
        ]
    )
    history = pd.DataFrame(
        [
            {"urn": "300", "domain": "academics", "year": "202425", "metric": "attainment8", "value": 55.0},
            {"urn": "200", "domain": "academics", "year": "202425", "metric": "attainment8", "value": 50.0},
            {"urn": "200", "domain": "academics", "year": "202324", "metric": "attainment8", "value": 49.0},
            {"urn": "100", "domain": "academics", "year": "202324", "metric": "attainment8", "value": 45.0},
            {"urn": "100", "domain": "academics", "year": "202223", "metric": "attainment8", "value": 44.0},
        ]
    )

    result = resolve_school_history_lineage(schools, links, history)
    current = result[result["urn"].eq("300")]

    assert list(result.columns) == list(SCHOOL_HISTORY_COLUMNS)
    assert current[["year", "value", "source_urn", "source_kind", "source_link_depth"]].to_dict("records") == [
        {"year": "202223", "value": 44.0, "source_urn": "100", "source_kind": "predecessor", "source_link_depth": 2},
        {"year": "202324", "value": 49.0, "source_urn": "200", "source_kind": "predecessor", "source_link_depth": 1},
        {"year": "202425", "value": 55.0, "source_urn": "300", "source_kind": "current", "source_link_depth": 0},
    ]
    assert current.loc[current["year"].eq("202324"), "source_school_name"].iloc[0] == "Previous Academy"


def test_resolve_school_history_stops_on_ambiguous_or_cyclic_links_and_handles_empty():
    schools = pd.DataFrame([{"urn": "3", "school_name": "Current"}])
    ambiguous_links = pd.DataFrame(
        [
            {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Two"},
            {"successor_urn": "3", "predecessor_urn": "1", "predecessor_name": "One"},
        ]
    )
    history = pd.DataFrame(
        [
            {"urn": "3", "domain": "attendance", "year": "202425", "metric": "overall_absence_pct", "value": 6.0},
            {"urn": "2", "domain": "attendance", "year": "202324", "metric": "overall_absence_pct", "value": 7.0},
        ]
    )
    result = resolve_school_history_lineage(schools, ambiguous_links, history)
    assert result["source_urn"].tolist() == ["3"]

    cyclic_links = pd.DataFrame(
        [
            {"successor_urn": "3", "predecessor_urn": "2", "predecessor_name": "Two"},
            {"successor_urn": "2", "predecessor_urn": "3", "predecessor_name": "Current"},
        ]
    )
    result = resolve_school_history_lineage(schools, cyclic_links, history)
    assert set(result["source_urn"]) == {"3", "2"}

    assert resolve_school_history_lineage(schools, pd.DataFrame(), pd.DataFrame()).empty
    assert resolve_school_history_lineage(
        pd.DataFrame([{"urn": "9", "school_name": "No history"}]), pd.DataFrame(), history
    ).empty


def test_combine_benchmark_history_handles_empty_and_keeps_latest_duplicate():
    empty = combine_benchmark_history(pd.DataFrame(), pd.DataFrame())
    assert list(empty.columns) == list(BENCHMARK_HISTORY_COLUMNS)

    row = {
        "benchmark_level": "National",
        "benchmark_code": "E92000001",
        "benchmark_name": "England",
        "domain": "academics",
        "year": "202425",
        "metric": "attainment8",
        "value": 47.0,
    }
    first = pd.DataFrame([row])
    second = pd.DataFrame([{**row, "value": 48.0}])
    result = combine_benchmark_history(first, second)
    assert result.iloc[0]["value"] == 48.0


def test_resolve_school_history_lineage_allows_link_without_predecessor_name():
    schools = pd.DataFrame([{"urn": "2", "school_name": "Current"}])
    links = pd.DataFrame(
        [{"successor_urn": "2", "predecessor_urn": "1", "predecessor_name": ""}]
    )
    history = pd.DataFrame(
        [
            {
                "urn": "1",
                "domain": "academics",
                "year": "202324",
                "metric": "attainment8",
                "value": 45.0,
            }
        ]
    )

    result = resolve_school_history_lineage(schools, links, history).iloc[0]

    assert result["source_urn"] == "1"
    assert result["source_school_name"] == "Current"
