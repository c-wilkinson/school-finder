"""Preference scoring for filtered school candidates."""

from __future__ import annotations

import pandas as pd

from school_finder.models.preferences import PreferenceMetric, SchoolPreferences


_METRIC_COLUMNS = {
    PreferenceMetric.DISTANCE: "distance_miles",
    PreferenceMetric.OFSTED: "ofsted_equivalent_rating",
    PreferenceMetric.ATTAINMENT8: "attainment8",
    PreferenceMetric.PROGRESS8: "progress8",
    PreferenceMetric.GRADE5_ENGLISH_MATHS: "english_maths_grade5_pct",
    PreferenceMetric.EBACC_APS: "ebacc_aps",
}

_OFSTED_COMPONENT_SCORES = {
    "inadequate": 0.0,
    "requires improvement": 100.0 / 3.0,
    "good": 200.0 / 3.0,
    "outstanding": 100.0,
}


def score_column(metric: PreferenceMetric) -> str:
    return f"preference_{metric.value.replace('-', '_')}_score"


def requested_weight_column(metric: PreferenceMetric) -> str:
    return f"preference_{metric.value.replace('-', '_')}_requested_weight_pct"


def effective_weight_column(metric: PreferenceMetric) -> str:
    return f"preference_{metric.value.replace('-', '_')}_effective_weight_pct"


SCORE_OUTPUT_COLUMNS = [
    "preference_score",
    "preference_score_coverage_pct",
    *[score_column(metric) for metric in PreferenceMetric],
    *[requested_weight_column(metric) for metric in PreferenceMetric],
    *[effective_weight_column(metric) for metric in PreferenceMetric],
]


def _normalise_numeric(series: pd.Series, *, lower_is_better: bool = False) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").astype("Float64")
    valid = values.dropna()
    result = pd.Series(pd.NA, index=series.index, dtype="Float64")
    if valid.empty:
        return result

    minimum = float(valid.min())
    maximum = float(valid.max())
    if minimum == maximum:
        result.loc[values.notna()] = 50.0
        return result

    normalised = (values - minimum) / (maximum - minimum) * 100.0
    if lower_is_better:
        normalised = 100.0 - normalised
    return normalised.astype("Float64")


def _normalise_ofsted(series: pd.Series) -> pd.Series:
    lowered = series.fillna("").astype("string").str.strip().str.casefold()
    return lowered.map(_OFSTED_COMPONENT_SCORES).astype("Float64")


def _component_scores(frame: pd.DataFrame) -> dict[PreferenceMetric, pd.Series]:
    return {
        PreferenceMetric.DISTANCE: _normalise_numeric(
            frame[_METRIC_COLUMNS[PreferenceMetric.DISTANCE]],
            lower_is_better=True,
        ),
        PreferenceMetric.OFSTED: _normalise_ofsted(
            frame[_METRIC_COLUMNS[PreferenceMetric.OFSTED]]
        ),
        PreferenceMetric.ATTAINMENT8: _normalise_numeric(
            frame[_METRIC_COLUMNS[PreferenceMetric.ATTAINMENT8]]
        ),
        PreferenceMetric.PROGRESS8: _normalise_numeric(
            frame[_METRIC_COLUMNS[PreferenceMetric.PROGRESS8]]
        ),
        PreferenceMetric.GRADE5_ENGLISH_MATHS: _normalise_numeric(
            frame[_METRIC_COLUMNS[PreferenceMetric.GRADE5_ENGLISH_MATHS]]
        ),
        PreferenceMetric.EBACC_APS: _normalise_numeric(
            frame[_METRIC_COLUMNS[PreferenceMetric.EBACC_APS]]
        ),
    }


def score_school_frame(
    frame: pd.DataFrame,
    preferences: SchoolPreferences,
) -> pd.DataFrame:
    scored = frame.copy()
    requested = preferences.normalised_weights()
    components = _component_scores(scored)

    coverage = pd.Series(0.0, index=scored.index, dtype="Float64")
    weighted_total = pd.Series(0.0, index=scored.index, dtype="Float64")

    for metric in PreferenceMetric:
        component = components[metric]
        weight = requested[metric]
        available = component.notna()
        coverage += available.astype(float) * weight
        weighted_total += component.fillna(0.0) * weight
        scored[score_column(metric)] = component.round(2)
        scored[requested_weight_column(metric)] = round(weight, 2)

    has_coverage = coverage.gt(0)
    overall = pd.Series(pd.NA, index=scored.index, dtype="Float64")
    overall.loc[has_coverage] = (
        weighted_total.loc[has_coverage] / coverage.loc[has_coverage]
    )
    scored["preference_score"] = overall.round(2)
    scored["preference_score_coverage_pct"] = coverage.round(2)

    for metric in PreferenceMetric:
        component = components[metric]
        weight = requested[metric]
        effective = pd.Series(0.0, index=scored.index, dtype="Float64")
        available = component.notna() & has_coverage & (weight > 0)
        effective.loc[available] = weight / coverage.loc[available] * 100.0
        scored[effective_weight_column(metric)] = effective.round(2)

    return scored


def rank_scored_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(
        by=["preference_score", "distance_miles", "school_name"],
        ascending=[False, True, True],
        na_position="last",
        kind="stable",
    )
