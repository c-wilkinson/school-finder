"""School-level subject result lookup service."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from school_finder.config import SUBJECTS_FILENAME
from school_finder.data.parquet import require_pyarrow
from school_finder.errors import SchoolFinderError
from school_finder.models.school import SubjectResult, subject_result_from_flat_record

_REQUIRED_COLUMNS = {
    "urn",
    "data_year",
    "subject",
    "qualification",
    "grade_structure",
    "entries",
    "grade4_plus",
    "grade4_plus_pct",
    "grade5_plus",
    "grade5_plus_pct",
    "grade7_plus",
    "grade7_plus_pct",
    "source",
    "source_dataset_id",
}


def get_school_subject_results(data_dir: Path, urn: str) -> tuple[SubjectResult, ...]:
    """Return subject-level results for one school URN."""

    path = data_dir / SUBJECTS_FILENAME
    if not path.exists():
        raise SchoolFinderError(f"{SUBJECTS_FILENAME} is missing from {data_dir}. Run 'school-finder build' first.")

    require_pyarrow()
    try:
        frame = pd.read_parquet(path, engine="pyarrow", filters=[("urn", "==", str(urn).strip())])
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {path}: {exc}") from exc

    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise SchoolFinderError(
            f"{path} uses an older subject schema. Run 'school-finder build' to rebuild it. "
            "Missing columns: " + ", ".join(missing)
        )

    if frame.empty:
        return ()
    records = frame.astype(object).where(pd.notna(frame), None).to_dict(orient="records")
    return tuple(subject_result_from_flat_record(record) for record in records)
