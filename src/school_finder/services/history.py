"""Historical metric lookup for the school detail experience."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from school_finder.config import BENCHMARK_HISTORY_FILENAME, HISTORY_FILENAME
from school_finder.data.history import BENCHMARK_HISTORY_COLUMNS, SCHOOL_HISTORY_COLUMNS
from school_finder.data.parquet import require_pyarrow
from school_finder.errors import SchoolFinderError

_OUTPUT_COLUMNS = (
    "domain",
    "year",
    "metric",
    "series",
    "value",
    "source_urn",
    "source_school_name",
    "source_kind",
    "source_link_depth",
)


def _read_parquet(path: Path, *, filters=None) -> pd.DataFrame:
    require_pyarrow()
    try:
        return pd.read_parquet(path, engine="pyarrow", filters=filters)
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {path}: {exc}") from exc


def _require_columns(path: Path, frame: pd.DataFrame, required: set[str]) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SchoolFinderError(
            f"{path} uses an older history schema. Run 'school-finder build' to rebuild it. "
            "Missing columns: " + ", ".join(missing)
        )


def get_school_history(
    data_dir: Path,
    urn: str,
    local_authority_code: str | None = None,
) -> pd.DataFrame:
    """Return school, local-authority and England historical metric series."""
    history_path = data_dir / HISTORY_FILENAME
    benchmark_path = data_dir / BENCHMARK_HISTORY_FILENAME
    if not history_path.exists() or not benchmark_path.exists():
        missing = [
            name
            for name, path in (
                (HISTORY_FILENAME, history_path),
                (BENCHMARK_HISTORY_FILENAME, benchmark_path),
            )
            if not path.exists()
        ]
        raise SchoolFinderError(
            f"{', '.join(missing)} is missing from {data_dir}. "
            "Run 'school-finder build' to create trend data."
        )

    school = _read_parquet(
        history_path,
        filters=[("urn", "==", str(urn).strip())],
    )
    _require_columns(history_path, school, set(SCHOOL_HISTORY_COLUMNS))

    frames: list[pd.DataFrame] = []
    if not school.empty:
        school = school.copy()
        school["series"] = "School"
        frames.append(school)

    national = _read_parquet(
        benchmark_path,
        filters=[("benchmark_level", "==", "National")],
    )
    _require_columns(benchmark_path, national, set(BENCHMARK_HISTORY_COLUMNS))
    if not national.empty:
        national = national.copy()
        national["series"] = national["benchmark_name"].fillna("England")
        national["source_urn"] = None
        national["source_school_name"] = None
        national["source_kind"] = None
        national["source_link_depth"] = None
        frames.append(national)

    local_code = str(local_authority_code or "").strip()
    if local_code:
        local = _read_parquet(
            benchmark_path,
            filters=[("benchmark_code", "==", local_code)],
        )
        _require_columns(benchmark_path, local, set(BENCHMARK_HISTORY_COLUMNS))
        if not local.empty:
            local = local.copy()
            local["series"] = local["benchmark_name"].fillna("Local authority")
            local["source_urn"] = None
            local["source_school_name"] = None
            local["source_kind"] = None
            local["source_link_depth"] = None
            frames.append(local)

    if not frames:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)

    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined[list(_OUTPUT_COLUMNS)].reset_index(drop=True)
