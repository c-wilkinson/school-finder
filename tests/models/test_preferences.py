import math

import pytest

from school_finder.models.preferences import (
    PreferenceMetric,
    PreferencePreset,
    SchoolPreferences,
)


def test_custom_preferences_accept_arbitrary_non_negative_scale_and_normalise():
    preferences = SchoolPreferences(distance=3, ofsted=2, attainment8=5)
    weights = preferences.weights()
    normalised = preferences.normalised_weights()

    assert weights[PreferenceMetric.DISTANCE] == 3
    assert weights[PreferenceMetric.OFSTED] == 2
    assert weights[PreferenceMetric.ATTAINMENT8] == 5
    assert sum(normalised.values()) == pytest.approx(100)
    assert normalised[PreferenceMetric.DISTANCE] == pytest.approx(30)
    assert normalised[PreferenceMetric.PROGRESS8] == 0


@pytest.mark.parametrize(
    "preset",
    [
        PreferencePreset.BALANCED,
        PreferencePreset.ACADEMIC,
        PreferencePreset.CLOSEST,
        PreferencePreset.OFSTED_FOCUSED,
    ],
)
def test_all_named_presets_produce_valid_weights(preset):
    preferences = SchoolPreferences.from_preset(preset)
    assert sum(preferences.weights().values()) == 100
    assert sum(preferences.normalised_weights().values()) == pytest.approx(100)


def test_preset_shapes_match_their_intent():
    balanced = SchoolPreferences.from_preset(PreferencePreset.BALANCED)
    academic = SchoolPreferences.from_preset(PreferencePreset.ACADEMIC)
    closest = SchoolPreferences.from_preset(PreferencePreset.CLOSEST)
    ofsted = SchoolPreferences.from_preset(PreferencePreset.OFSTED_FOCUSED)

    assert balanced.distance == balanced.ofsted == balanced.attainment8 == balanced.progress8 == 20
    assert academic.progress8 == max(academic.weights().values())
    assert closest.distance == max(closest.weights().values())
    assert ofsted.ofsted == max(ofsted.weights().values())


def test_custom_preset_requires_explicit_weights():
    with pytest.raises(ValueError, match="custom preset requires explicit"):
        SchoolPreferences.from_preset(PreferencePreset.CUSTOM)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "At least one preference weight"),
        ({"distance": -1}, "distance preference weight cannot be negative"),
        ({"ofsted": math.inf}, "ofsted preference weight must be finite"),
        ({"progress8": math.nan}, "progress8 preference weight must be finite"),
    ],
)
def test_preference_validation(kwargs, message):
    with pytest.raises(ValueError, match=message):
        SchoolPreferences(**kwargs)
