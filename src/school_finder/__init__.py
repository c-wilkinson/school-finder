"""School Finder core package."""

from school_finder.data.build import BuildResult, build_datasets
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
from school_finder.models.school import SchoolBenchmarks, SchoolResult, SchoolResultSet
from school_finder.models.scoring import ScoreComponent, SchoolScore
from school_finder.models.search import SchoolSearchRequest, SchoolSearchResult
from school_finder.services.scoring import score_school_frame
from school_finder.services.search import search_schools

__all__ = [
    "BuildResult",
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
    "build_datasets",
    "derive_equivalent_ofsted_rating",
    "score_school_frame",
    "search_schools",
]
