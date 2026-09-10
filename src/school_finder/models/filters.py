"""Filter and sort contracts shared by every School Finder presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from school_finder.models.ofsted import OfstedRating


class SchoolPhase(StrEnum):
    PRIMARY = "Primary"
    SECONDARY = "Secondary"
    ALL_THROUGH = "All-through"
    SIXTEEN_PLUS = "16 plus"
    NOT_APPLICABLE = "Not applicable"


class SchoolSector(StrEnum):
    STATE_FUNDED = "State-funded"
    INDEPENDENT = "Independent"


class SchoolGender(StrEnum):
    MIXED = "Mixed"
    BOYS = "Boys"
    GIRLS = "Girls"


class FaithFilter(StrEnum):
    ANY = "any"
    FAITH = "faith"
    NON_FAITH = "non-faith"


class SelectionFilter(StrEnum):
    ANY = "any"
    SELECTIVE = "selective"
    NON_SELECTIVE = "non-selective"


class SchoolSortField(StrEnum):
    DISTANCE = "distance"
    NAME = "name"
    OFSTED = "ofsted"
    ATTAINMENT8 = "attainment8"
    PROGRESS8 = "progress8"
    GRADE5_ENGLISH_MATHS = "grade5-english-maths"
    EBACC_APS = "ebacc-aps"
    PASTORAL_CARE = "pastoral-care"


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


@dataclass(frozen=True, slots=True)
class SchoolSort:
    field: SchoolSortField = SchoolSortField.DISTANCE
    direction: SortDirection = SortDirection.ASC
