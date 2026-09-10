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
from school_finder.models.school import (
    DestinationStatistics,
    PastoralCareStatistics,
    SchoolBenchmarks,
    SchoolResult,
    SchoolResultSet,
    SubjectResult,
)
from school_finder.models.scoring import ScoreComponent, SchoolScore
from school_finder.models.search import SchoolSearchRequest, SchoolSearchResult

__all__ = [
    "DestinationStatistics",
    "PastoralCareStatistics",
    "FaithFilter",
    "OfstedEquivalent",
    "OfstedEquivalentBasis",
    "OfstedRating",
    "PreferenceMetric",
    "PreferencePreset",
    "SchoolBenchmarks",
    "SchoolGender",
    "SchoolPhase",
    "SchoolPreferences",
    "SchoolResult",
    "SchoolResultSet",
    "SchoolScore",
    "SchoolSearchRequest",
    "SchoolSearchResult",
    "SchoolSector",
    "SchoolSort",
    "SchoolSortField",
    "ScoreComponent",
    "SelectionFilter",
    "SortDirection",
    "SubjectResult",
    "derive_equivalent_ofsted_rating",
]
