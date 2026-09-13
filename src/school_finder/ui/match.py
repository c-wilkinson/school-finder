"""Pure helpers for explaining School Finder preference scores."""

from __future__ import annotations

from math import isclose

from school_finder.models.preferences import PreferenceMetric, PreferencePreset, SchoolPreferences
from school_finder.models.scoring import SchoolScore, ScoreComponent
from school_finder.models.school import SchoolResult
from school_finder.ui.formatting import (
    MISSING,
    format_distance,
    format_number,
    format_percent,
    format_progress8,
)


_METRIC_LABELS: dict[PreferenceMetric, str] = {
    PreferenceMetric.DISTANCE: "Distance",
    PreferenceMetric.OFSTED: "Ofsted",
    PreferenceMetric.ATTAINMENT8: "Attainment 8",
    PreferenceMetric.PROGRESS8: "Progress 8",
    PreferenceMetric.GRADE5_ENGLISH_MATHS: "English & Maths Grade 5+",
    PreferenceMetric.EBACC_APS: "EBacc APS",
    PreferenceMetric.PASTORAL_CARE: "Pastoral care",
}

_PRESET_LABELS: dict[PreferencePreset, str] = {
    PreferencePreset.BALANCED: "Balanced",
    PreferencePreset.ACADEMIC: "Academic",
    PreferencePreset.CLOSEST: "Closest",
    PreferencePreset.OFSTED_FOCUSED: "Ofsted focused",
    PreferencePreset.PASTORAL_FOCUSED: "Pastoral focused",
}


def metric_label(metric: PreferenceMetric) -> str:
    """Return a parent-facing label for a preference metric."""
    return _METRIC_LABELS[metric]


def _format_weight(value: float) -> str:
    return f"{value:.0f}%" if isclose(value, round(value), abs_tol=0.005) else f"{value:.1f}%"


def _format_raw_value(component: ScoreComponent) -> str:
    value = component.raw_value
    if value is None:
        return MISSING
    if component.metric is PreferenceMetric.OFSTED:
        text = str(value).strip()
        return text or MISSING
    if not isinstance(value, (int, float)):
        return str(value)
    if component.metric is PreferenceMetric.DISTANCE:
        return format_distance(float(value))
    if component.metric is PreferenceMetric.PROGRESS8:
        return format_progress8(float(value))
    if component.metric is PreferenceMetric.GRADE5_ENGLISH_MATHS:
        return format_percent(float(value))
    return format_number(float(value))


def component_contribution(component: ScoreComponent) -> float | None:
    """Return this component's weighted contribution to the overall score."""
    if component.score is None:
        return None
    return component.score * component.effective_weight_pct / 100.0


def match_breakdown_rows(score: SchoolScore | None) -> list[dict[str, str]]:
    """Build display-ready rows for all preferences requested by the user."""
    if score is None:
        return []
    rows: list[dict[str, str]] = []
    for component in score.components:
        if component.requested_weight_pct <= 0:
            continue
        contribution = component_contribution(component)
        rows.append(
            {
                "Priority": metric_label(component.metric),
                "School result": _format_raw_value(component),
                "Component score": (
                    MISSING if component.score is None else format_number(component.score)
                ),
                "Requested weight": _format_weight(component.requested_weight_pct),
                "Effective weight": _format_weight(component.effective_weight_pct),
                "Contribution": (
                    MISSING if contribution is None else format_number(contribution)
                ),
            }
        )
    return rows


def _normalised_equal(left: dict[PreferenceMetric, float], right: dict[PreferenceMetric, float]) -> bool:
    return all(isclose(left[metric], right[metric], abs_tol=0.01) for metric in PreferenceMetric)


def preference_profile(preferences: SchoolPreferences | None) -> str:
    """Infer the named preset represented by the current weights, else Custom."""
    if preferences is None:
        return "No preference scoring"
    actual = preferences.normalised_weights()
    for preset, label in _PRESET_LABELS.items():
        expected = SchoolPreferences.from_preset(preset).normalised_weights()
        if _normalised_equal(actual, expected):
            return label
    return "Custom"


def priorities_summary(preferences: SchoolPreferences | None) -> str:
    """Return a compact list of non-zero normalised preference weights."""
    if preferences is None:
        return ""
    weights = preferences.normalised_weights()
    return " · ".join(
        f"{metric_label(metric)} {_format_weight(weight)}"
        for metric, weight in weights.items()
        if weight > 0
    )


def _component(score: SchoolScore | None, metric: PreferenceMetric) -> ScoreComponent | None:
    if score is None:
        return None
    return next((component for component in score.components if component.metric is metric), None)


def comparison_match_rows(schools: tuple[SchoolResult, ...]) -> list[dict[str, str]]:
    """Build side-by-side component-score rows for selected schools."""
    metrics = tuple(
        metric
        for metric in PreferenceMetric
        if any(
            (component := _component(school.preference_score, metric)) is not None
            and component.requested_weight_pct > 0
            for school in schools
        )
    )
    rows: list[dict[str, str]] = []
    for metric in metrics:
        components = [_component(school.preference_score, metric) for school in schools]
        available_scores = [
            component.score
            for component in components
            if component is not None and component.score is not None
        ]
        best = max(available_scores) if available_scores else None
        row = {"Priority": metric_label(metric)}
        for school, component in zip(schools, components, strict=True):
            if component is None or component.score is None:
                rendered = MISSING
            else:
                rendered = format_number(component.score)
                if best is not None and isclose(component.score, best, abs_tol=0.005):
                    rendered = f"★ {rendered}"
            row[school.identity.name] = rendered
        rows.append(row)
    return rows
