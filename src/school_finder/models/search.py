"""Search request/response contracts shared by every presentation layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SchoolSort,
    SelectionFilter,
)
from school_finder.models.preferences import SchoolPreferences
from school_finder.models.school import SchoolBenchmarks, SchoolResult


@dataclass(frozen=True, slots=True)
class SchoolSearchRequest:
    postcode: str
    limit: int = 20
    entry_age: int = 11
    minimum_exit_age: int = 16
    include_special: bool = False
    radius_miles: float | None = None
    phases: tuple[SchoolPhase, ...] = ()
    sectors: tuple[SchoolSector, ...] = ()
    genders: tuple[SchoolGender, ...] = ()
    faith: FaithFilter = FaithFilter.ANY
    selection: SelectionFilter = SelectionFilter.ANY
    minimum_ofsted_rating: OfstedRating | None = None
    minimum_attainment8: float | None = None
    minimum_progress8: float | None = None
    minimum_grade5_english_maths_pct: float | None = None
    minimum_ebacc_aps: float | None = None
    minimum_pastoral_score: float | None = None
    sort: SchoolSort = field(default_factory=SchoolSort)
    preferences: SchoolPreferences | None = None

    def __post_init__(self) -> None:
        if not self.postcode.strip():
            raise ValueError("postcode is required.")
        if self.limit < 1:
            raise ValueError("limit must be at least 1.")
        if self.entry_age < 0:
            raise ValueError("entry_age cannot be negative.")
        if self.minimum_exit_age < self.entry_age:
            raise ValueError("minimum_exit_age must be at least entry_age.")
        if self.radius_miles is not None and self.radius_miles <= 0:
            raise ValueError("radius_miles must be greater than 0.")
        if self.minimum_attainment8 is not None and self.minimum_attainment8 < 0:
            raise ValueError("minimum_attainment8 cannot be negative.")
        if self.minimum_grade5_english_maths_pct is not None and not (
            0 <= self.minimum_grade5_english_maths_pct <= 100
        ):
            raise ValueError(
                "minimum_grade5_english_maths_pct must be between 0 and 100."
            )
        if self.minimum_ebacc_aps is not None and not (0 <= self.minimum_ebacc_aps <= 10):
            raise ValueError("minimum_ebacc_aps must be between 0 and 10.")
        if self.minimum_pastoral_score is not None and not (
            0 <= self.minimum_pastoral_score <= 100
        ):
            raise ValueError("minimum_pastoral_score must be between 0 and 100.")


@dataclass(frozen=True, slots=True)
class PostcodeLocation:
    postcode: str
    easting: int
    northing: int
    is_current: bool
    termination_date: str | None = None


@dataclass(frozen=True, slots=True)
class SchoolSearchResult:
    request: SchoolSearchRequest
    postcode: PostcodeLocation
    schools: tuple[SchoolResult, ...]
    flat_records: tuple[Mapping[str, Any], ...] = field(
        default=(), repr=False, compare=False
    )
    benchmarks: tuple[SchoolBenchmarks, ...] = ()
