"""Postcode resolution against the locally built ONSPD dataset."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from school_finder.data.parquet import parquet_columns, require_pyarrow
from school_finder.errors import SchoolFinderError
from school_finder.models.search import PostcodeLocation
from school_finder.utils import normalise_postcode


def lookup_postcode(path: Path, postcode: str) -> PostcodeLocation:
    require_pyarrow()
    key = normalise_postcode(postcode)
    if not key:
        raise SchoolFinderError("A postcode is required.")

    required_columns = [
        "postcode",
        "postcode_key",
        "easting",
        "northing",
        "is_current",
        "termination_date",
    ]

    try:
        available_columns = parquet_columns(path)
        missing = sorted(set(required_columns) - available_columns)
        if missing:
            raise SchoolFinderError(
                f"{path} uses an older postcode schema. "
                "Run 'school-finder build' to rebuild it. "
                f"Missing columns: {', '.join(missing)}"
            )

        matches = pd.read_parquet(
            path,
            engine="pyarrow",
            columns=required_columns,
            filters=[("postcode_key", "==", key)],
        )
    except SchoolFinderError:
        raise
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {path}: {exc}") from exc

    if matches.empty:
        raise SchoolFinderError(
            f"English postcode not found in the dataset: {postcode}"
        )

    matches = matches.sort_values("is_current", ascending=False, kind="stable")
    match = matches.iloc[0]
    termination = str(match.get("termination_date", "")).strip() or None
    return PostcodeLocation(
        postcode=str(match["postcode"]),
        easting=int(match["easting"]),
        northing=int(match["northing"]),
        is_current=bool(match["is_current"]),
        termination_date=termination,
    )
