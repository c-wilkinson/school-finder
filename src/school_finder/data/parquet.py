"""Parquet read/write support shared by dataset builders and services."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from school_finder.config import HTTP_CHUNK_SIZE, PARQUET_ROW_GROUP_SIZE
from school_finder.errors import SchoolFinderError

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # Keeps CLI --help usable before dependencies are installed.
    pa = None
    pq = None


def require_pyarrow() -> None:
    if pa is None or pq is None:
        raise SchoolFinderError(
            "PyArrow is required. Install the project with: "
            "python -m pip install -e ."
        )


def write_parquet_file(frame: pd.DataFrame, destination: Path) -> None:
    require_pyarrow()
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(
        table,
        destination,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
        row_group_size=PARQUET_ROW_GROUP_SIZE,
    )


def parquet_columns(path: Path) -> set[str]:
    require_pyarrow()
    return set(pq.ParquetFile(path).schema_arrow.names)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(HTTP_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def parquet_metadata(path: Path) -> dict[str, Any]:
    require_pyarrow()
    parquet = pq.ParquetFile(path)
    return {
        "rows": parquet.metadata.num_rows,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "columns": parquet.schema_arrow.names,
    }
