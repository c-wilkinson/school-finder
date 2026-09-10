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
from school_finder.models.school import SchoolResult
from school_finder.models.search import SchoolSearchRequest, SchoolSearchResult
from school_finder.services.search import search_schools

__all__ = [
    "BuildResult",
    "FaithFilter",
    "OfstedEquivalent",
    "OfstedEquivalentBasis",
    "OfstedRating",
    "SchoolGender",
    "SchoolPhase",
    "SchoolResult",
    "SchoolSearchRequest",
    "SchoolSearchResult",
    "SchoolSector",
    "SchoolSort",
    "SchoolSortField",
    "SelectionFilter",
    "SortDirection",
    "build_datasets",
    "derive_equivalent_ofsted_rating",
    "search_schools",
]
