"""Application-facing scoring results."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from school_finder.models.preferences import PreferenceMetric


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    metric: PreferenceMetric
    raw_value: float | str | None
    score: float | None
    requested_weight_pct: float
    effective_weight_pct: float

    @property
    def available(self) -> bool:
        return self.score is not None


@dataclass(frozen=True, slots=True)
class SchoolScore:
    overall: float | None
    coverage_pct: float
    components: tuple[ScoreComponent, ...]

    def component(self, metric: PreferenceMetric) -> ScoreComponent:
        for component in self.components:
            if component.metric is metric:
                return component
        raise KeyError(metric)

    def to_dict(self) -> dict[str, Any]:
        return _serialise(self)


def _serialise(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serialise(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_serialise(item) for item in value]
    return value
