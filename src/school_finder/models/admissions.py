"""Admissions-arrangement contracts."""

from __future__ import annotations

from dataclasses import dataclass


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
    source_name: str | None = None
    source_url: str | None = None
    directory_url: str | None = None
