"""Admissions-arrangement contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AdmissionCriterionKind(StrEnum):
    """Structured categories used to describe published oversubscription criteria."""

    LOOKED_AFTER = "looked_after"
    SIBLING = "sibling"
    CATCHMENT = "catchment"
    DISTANCE = "distance"
    FEEDER = "feeder"
    FAITH = "faith"
    SELECTIVE = "selective"
    PUPIL_PREMIUM = "pupil_premium"
    SERVICE_PREMIUM = "service_premium"
    STAFF_CHILD = "staff_child"
    SOCIAL_MEDICAL = "social_medical"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class AdmissionCriterion:
    """One published oversubscription criterion and School Finder's structured tags."""

    priority: int
    kinds: tuple[AdmissionCriterionKind, ...]
    description: str


@dataclass(frozen=True, slots=True)
class AdmissionEntryPoint:
    """Published admission number for one normal entry point."""

    year_group: str
    entry_year: int
    published_admission_number: int


@dataclass(frozen=True, slots=True)
class AdmissionArrangementSummary:
    """Current factual admissions-arrangement context for one school."""

    admission_authority: str | None = None
    selective: bool | None = None
    policy: str | None = None
    entry_points: tuple[AdmissionEntryPoint, ...] = ()
    arrangements_year: str | None = None
    criteria: tuple[AdmissionCriterion, ...] = ()
    source_name: str | None = None
    source_url: str | None = None
    directory_url: str | None = None
