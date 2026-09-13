from school_finder.models.preferences import PreferenceMetric, PreferencePreset, SchoolPreferences
from school_finder.models.school import SchoolIdentity, SchoolResult
from school_finder.models.scoring import SchoolScore, ScoreComponent
from school_finder.ui.match import (
    comparison_match_rows,
    component_contribution,
    match_breakdown_rows,
    metric_label,
    preference_profile,
    priorities_summary,
)


def _component(
    metric: PreferenceMetric,
    raw,
    score: float | None,
    requested: float = 20.0,
    effective: float = 25.0,
) -> ScoreComponent:
    return ScoreComponent(metric, raw, score, requested, effective)


def _school(name: str, urn: str, components: tuple[ScoreComponent, ...] | None) -> SchoolResult:
    score = None if components is None else SchoolScore(80.0, 80.0, components)
    return SchoolResult(identity=SchoolIdentity(urn, name), preference_score=score)


def test_metric_labels_cover_every_preference_metric():
    assert {metric_label(metric) for metric in PreferenceMetric} == {
        "Distance",
        "Ofsted",
        "Attainment 8",
        "Progress 8",
        "English & Maths Grade 5+",
        "EBacc APS",
        "Pastoral care",
    }


def test_match_breakdown_formats_each_metric_and_skips_zero_weight():
    score = SchoolScore(
        80.0,
        75.0,
        (
            _component(PreferenceMetric.DISTANCE, 1.25, 90.0, 20.0, 25.0),
            _component(PreferenceMetric.OFSTED, "Good", 66.67, 20.0, 25.0),
            _component(PreferenceMetric.ATTAINMENT8, 52.3, 80.0, 20.0, 25.0),
            _component(PreferenceMetric.PROGRESS8, 0.31, 95.0, 20.0, 25.0),
            _component(PreferenceMetric.GRADE5_ENGLISH_MATHS, 68.2, 88.0, 15.0, 18.75),
            _component(PreferenceMetric.EBACC_APS, 4.6, 60.0, 5.0, 6.25),
            _component(PreferenceMetric.PASTORAL_CARE, 82.0, 82.0, 0.0, 0.0),
        ),
    )

    rows = match_breakdown_rows(score)

    assert len(rows) == 6
    assert rows[0]["School result"] == "1.2 mi"
    assert rows[1]["School result"] == "Good"
    assert rows[2]["School result"] == "52.3"
    assert rows[3]["School result"] == "+0.31"
    assert rows[4]["School result"] == "68.2%"
    assert rows[5]["School result"] == "4.6"
    assert rows[0]["Requested weight"] == "20%"
    assert rows[4]["Effective weight"] == "18.8%"
    assert rows[0]["Contribution"] == "22.5"


def test_match_breakdown_handles_missing_unusual_raw_values_and_no_score():
    assert match_breakdown_rows(None) == []
    score = SchoolScore(
        None,
        20.0,
        (
            _component(PreferenceMetric.OFSTED, "   ", None, 10.0, 0.0),
            _component(PreferenceMetric.ATTAINMENT8, "suppressed", None, 10.0, 0.0),
            _component(PreferenceMetric.PROGRESS8, None, None, 10.0, 0.0),
        ),
    )
    rows = match_breakdown_rows(score)
    assert rows[0]["School result"] == "—"
    assert rows[1]["School result"] == "suppressed"
    assert rows[2]["School result"] == "—"
    assert all(row["Component score"] == "—" for row in rows)
    assert all(row["Contribution"] == "—" for row in rows)
    assert component_contribution(score.components[0]) is None


def test_preference_profile_recognises_presets_custom_and_none():
    assert preference_profile(None) == "No preference scoring"
    for preset, expected in (
        (PreferencePreset.BALANCED, "Balanced"),
        (PreferencePreset.ACADEMIC, "Academic"),
        (PreferencePreset.CLOSEST, "Closest"),
        (PreferencePreset.OFSTED_FOCUSED, "Ofsted focused"),
        (PreferencePreset.PASTORAL_FOCUSED, "Pastoral focused"),
    ):
        assert preference_profile(SchoolPreferences.from_preset(preset)) == expected

    custom = SchoolPreferences(distance=1, ofsted=2, attainment8=3, progress8=4, grade5_english_maths=5, ebacc_aps=6, pastoral_care=7)
    assert preference_profile(custom) == "Custom"


def test_priorities_summary_omits_zero_weights_and_formats_fractional_percentages():
    assert priorities_summary(None) == ""
    preferences = SchoolPreferences(distance=1, ofsted=2, attainment8=0, progress8=0, grade5_english_maths=0, ebacc_aps=0, pastoral_care=0)
    assert priorities_summary(preferences) == "Distance 33.3% · Ofsted 66.7%"


def test_comparison_match_rows_marks_best_and_handles_missing_components_and_scores():
    distance_a = _component(PreferenceMetric.DISTANCE, 1.0, 90.0)
    distance_b = _component(PreferenceMetric.DISTANCE, 2.0, 75.0)
    progress_missing = _component(PreferenceMetric.PROGRESS8, None, None)
    a = _school("A", "1", (distance_a, progress_missing))
    b = _school("B", "2", (distance_b,))
    c = _school("C", "3", None)

    rows = comparison_match_rows((a, b, c))

    assert rows == [
        {"Priority": "Distance", "A": "★ 90.0", "B": "75.0", "C": "—"},
        {"Priority": "Progress 8", "A": "—", "B": "—", "C": "—"},
    ]


def test_comparison_match_rows_marks_joint_best_and_returns_empty_without_requested_metrics():
    a = _school("A", "1", (_component(PreferenceMetric.DISTANCE, 1.0, 80.0),))
    b = _school("B", "2", (_component(PreferenceMetric.DISTANCE, 2.0, 80.0),))
    rows = comparison_match_rows((a, b))
    assert rows[0]["A"].startswith("★ ")
    assert rows[0]["B"].startswith("★ ")

    zero = _component(PreferenceMetric.DISTANCE, 1.0, 80.0, requested=0.0, effective=0.0)
    assert comparison_match_rows((_school("Z", "9", (zero,)),)) == []
