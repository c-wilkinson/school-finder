"""School Finder core package."""

from school_finder.data.build import BuildResult, build_datasets
from school_finder.models.school import SchoolResult
from school_finder.models.search import SchoolSearchRequest, SchoolSearchResult
from school_finder.services.search import search_schools

__all__ = [
    "BuildResult",
    "SchoolResult",
    "SchoolSearchRequest",
    "SchoolSearchResult",
    "build_datasets",
    "search_schools",
]
