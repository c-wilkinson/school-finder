"""Reusable application services."""

from school_finder.services.admission_arrangements import get_admission_arrangements
from school_finder.services.benchmarks import benchmark_results_from_frame, find_relevant_benchmarks
from school_finder.services.scoring import rank_scored_frame, score_school_frame
from school_finder.services.search import get_schools_by_urn, search_schools
from school_finder.services.subjects import get_school_subject_results

__all__ = [
    "get_admission_arrangements",
    "benchmark_results_from_frame",
    "find_relevant_benchmarks",
    "get_school_subject_results",
    "get_schools_by_urn",
    "rank_scored_frame",
    "score_school_frame",
    "search_schools",
]
