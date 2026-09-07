"""Application-facing data contracts."""

from school_finder.models.school import (
    AcademicPerformance,
    AdmissionsInformation,
    AttendanceStatistics,
    BehaviourStatistics,
    InspectionSummary,
    SchoolBenchmarks,
    SchoolIdentity,
    SchoolLocation,
    SchoolResult,
    SchoolResultSet,
    TravelInformation,
    UserAssessment,
    WorkforceStatistics,
    school_result_from_flat_record,
)
from school_finder.models.search import (
    PostcodeLocation,
    SchoolSearchRequest,
    SchoolSearchResult,
)

__all__ = [
    "AcademicPerformance",
    "AdmissionsInformation",
    "AttendanceStatistics",
    "BehaviourStatistics",
    "InspectionSummary",
    "PostcodeLocation",
    "SchoolBenchmarks",
    "SchoolIdentity",
    "SchoolLocation",
    "SchoolResult",
    "SchoolResultSet",
    "SchoolSearchRequest",
    "SchoolSearchResult",
    "TravelInformation",
    "UserAssessment",
    "WorkforceStatistics",
    "school_result_from_flat_record",
]
