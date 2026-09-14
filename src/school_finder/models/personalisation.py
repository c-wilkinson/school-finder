"""Parent-specific school personalisation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SchoolDisposition(StrEnum):
    """A parent's current decision about a school."""

    NEUTRAL = "neutral"
    SHORTLISTED = "shortlisted"
    NOT_FOR_US = "not-for-us"


@dataclass(frozen=True, slots=True)
class PersonalSchoolState:
    """Session-level parent-specific state for one school."""

    disposition: SchoolDisposition = SchoolDisposition.NEUTRAL
    rating: int | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, SchoolDisposition):
            raise TypeError("disposition must be a SchoolDisposition.")
        if self.rating is not None and (
            isinstance(self.rating, bool)
            or not isinstance(self.rating, int)
            or not 1 <= self.rating <= 5
        ):
            raise ValueError("rating must be an integer from 1 to 5, or None.")
        if self.notes is not None:
            notes = self.notes.strip()
            object.__setattr__(self, "notes", notes or None)

    @property
    def is_default(self) -> bool:
        """Return whether this state contains no parent-specific information."""
        return (
            self.disposition is SchoolDisposition.NEUTRAL
            and self.rating is None
            and self.notes is None
        )
