"""Project-wide configuration constants."""

from pathlib import Path

DEFAULT_DATA_DIR = Path("data")
MANIFEST_FILENAME = "manifest.json"
SCHOOLS_FILENAME = "schools.parquet"
POSTCODES_FILENAME = "postcodes.parquet"
MANIFEST_SCHEMA_VERSION = 3

METRES_PER_MILE = 1609.344
HTTP_CHUNK_SIZE = 1024 * 1024
PARQUET_ROW_GROUP_SIZE = 100_000

USER_AGENT = (
    "school-finder-prototype/0.4 "
    "(public DfE and ONS data; local dataset builder)"
)
