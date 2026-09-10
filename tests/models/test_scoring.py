import pytest

from school_finder.models.preferences import PreferenceMetric
from school_finder.models.scoring import ScoreComponent, SchoolScore


def _component(metric=PreferenceMetric.DISTANCE, score=80.0):
    return ScoreComponent(metric, 1.2, score, 50.0, 50.0)


def test_score_component_available_reflects_score_presence():
    assert _component().available is True
    assert _component(score=None).available is False


def test_school_score_finds_component_and_rejects_missing_metric():
    score = SchoolScore(80.0, 100.0, (_component(),))
    assert score.component(PreferenceMetric.DISTANCE).score == 80.0
    with pytest.raises(KeyError):
        score.component(PreferenceMetric.OFSTED)


def test_school_score_serialises_to_plain_nested_data():
    score = SchoolScore(80.0, 75.0, (_component(),))
    payload = score.to_dict()
    assert payload["overall"] == 80.0
    assert payload["components"][0]["metric"] == "distance"
    assert payload["components"][0]["raw_value"] == 1.2
