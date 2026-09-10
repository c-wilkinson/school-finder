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
from school_finder.services.scoring import score_school_frame
from school_finder.services.search import search_schools
from school_finder.services.subjects import get_school_subject_results

__all__ = [
    "BuildResult",
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
    "build_datasets",
    "derive_equivalent_ofsted_rating",
    "get_school_subject_results",
    "score_school_frame",
    "search_schools",
]
