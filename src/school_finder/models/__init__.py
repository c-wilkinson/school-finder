"""Application data contracts."""

from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SchoolSort,
    SchoolSortField,
    SelectionFilter,
    SortDirection,
)
from school_finder.models.ofsted import (
    OfstedEquivalent,
    OfstedEquivalentBasis,
    derive_equivalent_ofsted_rating,
)
from school_finder.models.preferences import (
    PreferenceMetric,
    PreferencePreset,
    SchoolPreferences,
)
from school_finder.models.school import SchoolResult
from school_finder.models.scoring import ScoreComponent, SchoolScore
from school_finder.models.search import SchoolSearchRequest, SchoolSearchResult

__all__ = [
    "FaithFilter",
    "OfstedEquivalent",
    "OfstedEquivalentBasis",
    "OfstedRating",
    "PreferenceMetric",
    "PreferencePreset",
    "SchoolGender",
    "SchoolPhase",
    "SchoolPreferences",
    "SchoolResult",
    "SchoolScore",
    "SchoolSearchRequest",
    "SchoolSearchResult",
    "SchoolSector",
    "SchoolSort",
    "SchoolSortField",
    "ScoreComponent",
    "SelectionFilter",
    "SortDirection",
    "derive_equivalent_ofsted_rating",
]
