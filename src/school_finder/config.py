"""Project-wide configuration constants."""

from pathlib import Path

DEFAULT_DATA_DIR = Path("data")
MANIFEST_FILENAME = "manifest.json"
SCHOOLS_FILENAME = "schools.parquet"
POSTCODES_FILENAME = "postcodes.parquet"
BENCHMARKS_FILENAME = "benchmarks.parquet"
SUBJECTS_FILENAME = "subjects.parquet"
HISTORY_FILENAME = "history.parquet"
BENCHMARK_HISTORY_FILENAME = "benchmark_history.parquet"
MANIFEST_SCHEMA_VERSION = 9

METRES_PER_MILE = 1609.344
HTTP_CHUNK_SIZE = 1024 * 1024
PARQUET_ROW_GROUP_SIZE = 100_000

USER_AGENT = (
    "school-finder-prototype/0.9 "
    "(public DfE and ONS data; local dataset builder)"
)
