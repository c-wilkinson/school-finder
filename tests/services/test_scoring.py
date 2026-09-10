import pandas as pd
import pytest

from school_finder.models.preferences import PreferenceMetric, SchoolPreferences
from school_finder.services import scoring


def _frame(**overrides):
    rows = [
        {
            "school_name": "Near",
            "distance_miles": 1.0,
            "ofsted_equivalent_rating": "Good",
            "attainment8": 40.0,
            "progress8": -0.2,
            "english_maths_grade5_pct": 40.0,
            "ebacc_aps": 3.0,
            "pastoral_score": 62.0,
        },
        {
            "school_name": "Far",
            "distance_miles": 5.0,
            "ofsted_equivalent_rating": "Outstanding",
            "attainment8": 60.0,
            "progress8": 0.4,
            "english_maths_grade5_pct": 70.0,
            "ebacc_aps": 5.0,
            "pastoral_score": 88.0,
        },
    ]
    for row in rows:
        row.update(overrides)
    return pd.DataFrame(rows)


def test_numeric_normalisation_handles_empty_equal_and_direction():
    empty = scoring._normalise_numeric(pd.Series([None, "?"]))
    assert empty.isna().all()

    equal = scoring._normalise_numeric(pd.Series([4.0, 4.0, None]))
    assert equal.iloc[0] == 50
    assert equal.iloc[1] == 50
    assert pd.isna(equal.iloc[2])

    higher = scoring._normalise_numeric(pd.Series([1.0, 3.0]))
    lower = scoring._normalise_numeric(pd.Series([1.0, 3.0]), lower_is_better=True)
    assert higher.tolist() == [0.0, 100.0]
    assert lower.tolist() == [100.0, 0.0]


def test_ofsted_normalisation_uses_all_four_bands_and_leaves_unknown_missing():
    values = pd.Series(["Inadequate", "Requires Improvement", "Good", "Outstanding", None, "Other"])
    result = scoring._normalise_ofsted(values)
    assert result.iloc[:4].tolist() == pytest.approx([0, 100 / 3, 200 / 3, 100])
    assert pd.isna(result.iloc[4])
    assert pd.isna(result.iloc[5])


def test_score_school_frame_scores_all_metrics_and_ranks_relative_values():
    preferences = SchoolPreferences(distance=1, ofsted=1, attainment8=1, progress8=1, grade5_english_maths=1, ebacc_aps=1)
    result = scoring.score_school_frame(_frame(), preferences)

    near = result[result["school_name"] == "Near"].iloc[0]
    far = result[result["school_name"] == "Far"].iloc[0]
    assert near[scoring.score_column(PreferenceMetric.DISTANCE)] == 100
    assert far[scoring.score_column(PreferenceMetric.DISTANCE)] == 0
    assert near[scoring.score_column(PreferenceMetric.ATTAINMENT8)] == 0
    assert far[scoring.score_column(PreferenceMetric.ATTAINMENT8)] == 100
    assert near[scoring.score_column(PreferenceMetric.OFSTED)] == pytest.approx(66.67, abs=0.01)
    assert far[scoring.score_column(PreferenceMetric.OFSTED)] == 100
    assert near["preference_score_coverage_pct"] == 100
    assert far["preference_score_coverage_pct"] == 100
    assert 0 <= near["preference_score"] <= 100
    assert 0 <= far["preference_score"] <= 100


def test_missing_metric_redistributes_weight_instead_of_scoring_zero():
    frame = _frame()
    frame.loc[0, "attainment8"] = None
    preferences = SchoolPreferences(distance=50, attainment8=50)
    result = scoring.score_school_frame(frame, preferences)
    near = result.iloc[0]

    assert near["preference_score_coverage_pct"] == 50
    assert near["preference_score"] == 100
    assert near[scoring.effective_weight_column(PreferenceMetric.DISTANCE)] == 100
    assert near[scoring.effective_weight_column(PreferenceMetric.ATTAINMENT8)] == 0
    assert near[scoring.requested_weight_column(PreferenceMetric.DISTANCE)] == 50


def test_school_with_no_available_weighted_metrics_has_no_overall_score():
    frame = _frame()
    frame["ofsted_equivalent_rating"] = None
    result = scoring.score_school_frame(frame, SchoolPreferences(ofsted=1))
    assert result["preference_score"].isna().all()
    assert result["preference_score_coverage_pct"].tolist() == [0.0, 0.0]
    assert result[scoring.effective_weight_column(PreferenceMetric.OFSTED)].tolist() == [0.0, 0.0]


def test_zero_weight_metric_can_have_component_score_without_affecting_coverage():
    result = scoring.score_school_frame(_frame(), SchoolPreferences(distance=1))
    assert result[scoring.score_column(PreferenceMetric.ATTAINMENT8)].notna().all()
    assert result[scoring.requested_weight_column(PreferenceMetric.ATTAINMENT8)].tolist() == [0.0, 0.0]
    assert result[scoring.effective_weight_column(PreferenceMetric.ATTAINMENT8)].tolist() == [0.0, 0.0]
    assert result["preference_score_coverage_pct"].tolist() == [100.0, 100.0]


def test_rank_scored_frame_places_best_first_missing_last_and_breaks_ties_deterministically():
    frame = pd.DataFrame([
        {"school_name": "Zulu", "distance_miles": 1.0, "preference_score": 80.0},
        {"school_name": "Alpha", "distance_miles": 1.0, "preference_score": 80.0},
        {"school_name": "Closer", "distance_miles": 0.5, "preference_score": 80.0},
        {"school_name": "Best", "distance_miles": 5.0, "preference_score": 90.0},
        {"school_name": "Missing", "distance_miles": 0.1, "preference_score": None},
    ])
    assert scoring.rank_scored_frame(frame)["school_name"].tolist() == [
        "Best", "Closer", "Alpha", "Zulu", "Missing"
    ]


def test_pastoral_component_uses_absolute_0_to_100_score_not_candidate_minmax():
    result = scoring.score_school_frame(_frame(), SchoolPreferences(pastoral_care=1))
    assert result[scoring.score_column(PreferenceMetric.PASTORAL_CARE)].tolist() == [62.0, 88.0]
    assert result["preference_score"].tolist() == [62.0, 88.0]


def test_percentage_normalisation_rejects_out_of_range_values():
    result = scoring._normalise_percentage(pd.Series([-1, 0, 50, 100, 101, None]))
    assert pd.isna(result.iloc[0])
    assert result.iloc[1:4].tolist() == [0.0, 50.0, 100.0]
    assert pd.isna(result.iloc[4])
    assert pd.isna(result.iloc[5])


def test_optional_pastoral_metric_can_be_absent_from_older_candidate_frame():
    frame = _frame().drop(columns=["pastoral_score"])
    result = scoring.score_school_frame(frame, SchoolPreferences(pastoral_care=1))
    assert result["preference_score"].isna().all()
    assert result["preference_score_coverage_pct"].eq(0).all()
