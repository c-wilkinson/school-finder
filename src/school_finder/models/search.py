"""Search request/response contracts shared by every presentation layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from school_finder.models.school import SchoolResult


@dataclass(frozen=True, slots=True)
class SchoolSearchRequest:
    postcode: str
    limit: int = 20
    entry_age: int = 11
    minimum_exit_age: int = 16
    include_special: bool = False


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
