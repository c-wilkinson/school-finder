"""Parent preference contracts used by the school scoring engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class PreferenceMetric(StrEnum):
    DISTANCE = "distance"
    OFSTED = "ofsted"
    ATTAINMENT8 = "attainment8"
    PROGRESS8 = "progress8"
    GRADE5_ENGLISH_MATHS = "grade5-english-maths"
    EBACC_APS = "ebacc-aps"


class PreferencePreset(StrEnum):
    BALANCED = "balanced"
    ACADEMIC = "academic"
    CLOSEST = "closest"
    OFSTED_FOCUSED = "ofsted-focused"
    CUSTOM = "custom"


_PRESET_WEIGHTS: dict[PreferencePreset, dict[PreferenceMetric, float]] = {
    PreferencePreset.BALANCED: {
        PreferenceMetric.DISTANCE: 20,
        PreferenceMetric.OFSTED: 20,
        PreferenceMetric.ATTAINMENT8: 20,
        PreferenceMetric.PROGRESS8: 20,
        PreferenceMetric.GRADE5_ENGLISH_MATHS: 15,
        PreferenceMetric.EBACC_APS: 5,
    },
    PreferencePreset.ACADEMIC: {
        PreferenceMetric.DISTANCE: 5,
        PreferenceMetric.OFSTED: 10,
        PreferenceMetric.ATTAINMENT8: 25,
        PreferenceMetric.PROGRESS8: 30,
        PreferenceMetric.GRADE5_ENGLISH_MATHS: 20,
        PreferenceMetric.EBACC_APS: 10,
    },
    PreferencePreset.CLOSEST: {
        PreferenceMetric.DISTANCE: 70,
        PreferenceMetric.OFSTED: 10,
        PreferenceMetric.ATTAINMENT8: 5,
        PreferenceMetric.PROGRESS8: 5,
        PreferenceMetric.GRADE5_ENGLISH_MATHS: 5,
        PreferenceMetric.EBACC_APS: 5,
    },
    PreferencePreset.OFSTED_FOCUSED: {
        PreferenceMetric.DISTANCE: 10,
        PreferenceMetric.OFSTED: 60,
        PreferenceMetric.ATTAINMENT8: 10,
        PreferenceMetric.PROGRESS8: 10,
        PreferenceMetric.GRADE5_ENGLISH_MATHS: 5,
        PreferenceMetric.EBACC_APS: 5,
    },
}


@dataclass(frozen=True, slots=True)
class SchoolPreferences:
    distance: float = 0
    ofsted: float = 0
    attainment8: float = 0
    progress8: float = 0
    grade5_english_maths: float = 0
    ebacc_aps: float = 0

    def __post_init__(self) -> None:
        weights = self.weights()
        for metric, weight in weights.items():
            if not isfinite(weight):
                raise ValueError(f"{metric.value} preference weight must be finite.")
            if weight < 0:
                raise ValueError(f"{metric.value} preference weight cannot be negative.")
        if sum(weights.values()) <= 0:
            raise ValueError("At least one preference weight must be greater than 0.")

    @classmethod
    def from_preset(cls, preset: PreferencePreset) -> SchoolPreferences:
        if preset is PreferencePreset.CUSTOM:
            raise ValueError("The custom preset requires explicit preference weights.")
        weights = _PRESET_WEIGHTS[preset]
        return cls(
            distance=weights[PreferenceMetric.DISTANCE],
            ofsted=weights[PreferenceMetric.OFSTED],
            attainment8=weights[PreferenceMetric.ATTAINMENT8],
            progress8=weights[PreferenceMetric.PROGRESS8],
            grade5_english_maths=weights[PreferenceMetric.GRADE5_ENGLISH_MATHS],
            ebacc_aps=weights[PreferenceMetric.EBACC_APS],
        )

    def weights(self) -> dict[PreferenceMetric, float]:
        return {
            PreferenceMetric.DISTANCE: float(self.distance),
            PreferenceMetric.OFSTED: float(self.ofsted),
            PreferenceMetric.ATTAINMENT8: float(self.attainment8),
            PreferenceMetric.PROGRESS8: float(self.progress8),
            PreferenceMetric.GRADE5_ENGLISH_MATHS: float(self.grade5_english_maths),
            PreferenceMetric.EBACC_APS: float(self.ebacc_aps),
        }

    def normalised_weights(self) -> dict[PreferenceMetric, float]:
        weights = self.weights()
        total = sum(weights.values())
        return {metric: weight / total * 100 for metric, weight in weights.items()}
