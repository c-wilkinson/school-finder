"""Dataset build orchestration."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from school_finder.config import (
    BENCHMARKS_FILENAME,
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    POSTCODES_FILENAME,
    SCHOOLS_FILENAME,
    SUBJECTS_FILENAME,
)
from school_finder.errors import SchoolFinderError
from school_finder.data.manifest import (
    csv_source_manifest,
    gias_links_manifest,
    gias_manifest,
    onspd_manifest,
    read_manifest,
    source_matches,
    write_json_atomic,
)
from school_finder.data.parquet import parquet_metadata, require_pyarrow, write_parquet_file
from school_finder.data.sources.common import create_session, download_csv
from school_finder.data.sources.attendance import (
    discover_attendance_benchmark_source,
    discover_attendance_school_source,
    read_attendance_benchmarks,
    read_attendance_school,
)
from school_finder.data.sources.behaviour import (
    discover_behaviour_benchmark_source,
    discover_behaviour_school_source,
    read_behaviour_benchmarks,
    read_behaviour_school,
)
from school_finder.data.sources.destinations import (
    discover_destination_la_source,
    discover_destination_national_source,
    discover_destination_school_source,
    read_destination_benchmarks,
    read_destination_school,
)
from school_finder.data.sources.gias import (
    clean_gias_data,
    clean_gias_links_data,
    discover_latest_gias_links_source,
    discover_latest_gias_source,
    download_gias_csv,
    download_gias_links_csv,
    read_gias_csv,
    read_gias_links_csv,
)
from school_finder.data.sources.ks4 import discover_ks4_source, read_ks4_quality
from school_finder.data.sources.ks4_subjects import (
    discover_ks4_subject_source,
    read_ks4_subjects,
)
from school_finder.data.sources.ks4_benchmarks import (
    discover_ks4_benchmark_source,
    read_ks4_benchmarks,
)
from school_finder.data.sources.workforce import (
    discover_workforce_benchmark_source,
    discover_workforce_ratio_benchmark_source,
    discover_workforce_ratio_school_source,
    discover_workforce_school_source,
    read_workforce_benchmarks,
    read_workforce_school,
)
from school_finder.data.sources.parent_view import (
    discover_parent_view_source,
    read_parent_view_school,
)
from school_finder.data.sources.ofsted import (
    discover_latest_independent_ofsted_source,
    discover_latest_legacy_ofsted_source,
    discover_latest_ofsted_source,
    read_ofsted_quality,
)
from school_finder.data.sources.onspd import (
    clean_onspd_data,
    discover_latest_onspd_source,
    download_onspd_zip,
)
from school_finder.utils import iso_utc, log, utc_now


@dataclass(frozen=True)
class BuildResult:
    schools_updated: bool
    postcodes_updated: bool
    manifest_updated: bool
    manifest: dict[str, Any]
    benchmarks_updated: bool = False
    subjects_updated: bool = False


def combine_ofsted_quality(*frames: pd.DataFrame) -> pd.DataFrame:
    """Keep the newest actual Ofsted inspection for each current-school URN."""
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(
            ["urn", "ofsted_publication_date", "ofsted_inspection_date"],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates("urn", keep="last")
        .reset_index(drop=True)
    )


OFSTED_QUALITY_COLUMNS = (
    "ofsted_rating",
    "ofsted_inspection_date",
    "ofsted_publication_date",
    "ofsted_safeguarding",
    "ofsted_inclusion",
    "ofsted_curriculum_teaching",
    "ofsted_achievement",
    "ofsted_attendance_behaviour",
    "ofsted_personal_development",
    "ofsted_leadership",
)

KS4_PERFORMANCE_COLUMNS = (
    "performance_year",
    "local_authority_code",
    "local_authority_name",
    "pupil_count",
    "attainment8",
    "attainment8_english",
    "attainment8_maths",
    "attainment8_ebacc",
    "attainment8_open",
    "english_maths_grade5_pct",
    "english_maths_grade4_pct",
    "ebacc_entry_pct",
    "ebacc_grade5_pct",
    "ebacc_grade4_pct",
    "ebacc_aps",
    "triple_science_entry_pct",
    "multiple_languages_entry_pct",
    "gcse_entries_per_pupil",
    "qualification_entries_per_pupil",
    "progress8_pupil_count",
    "progress8",
    "progress8_english",
    "progress8_maths",
    "progress8_ebacc",
    "progress8_open",
    "progress8_year",
)

PROGRESS8_METRIC_COLUMNS = (
    "progress8_pupil_count",
    "progress8",
    "progress8_english",
    "progress8_maths",
    "progress8_ebacc",
    "progress8_open",
    "progress8_year",
)

PROGRESS8_SOURCE_COLUMNS = (
    "progress8_source_urn",
    "progress8_source_school_name",
    "progress8_source_kind",
    "progress8_source_link_depth",
)

ATTENDANCE_COLUMNS = (
    "attendance_year",
    "attendance_enrolments",
    "overall_absence_pct",
    "authorised_absence_pct",
    "unauthorised_absence_pct",
    "persistent_absence_pct",
    "severe_absence_pct",
    "attendance_source",
    "attendance_source_dataset_id",
)

BEHAVIOUR_COLUMNS = (
    "behaviour_year",
    "behaviour_pupil_headcount",
    "suspension_count",
    "suspension_rate",
    "pupils_with_one_or_more_suspension",
    "pupils_with_one_or_more_suspension_rate",
    "permanent_exclusion_count",
    "permanent_exclusion_rate",
    "behaviour_source",
    "behaviour_source_dataset_id",
)

WORKFORCE_COLUMNS = (
    "workforce_year",
    "workforce_ratio_year",
    "pupil_fte",
    "teacher_fte",
    "qualified_teacher_fte",
    "classroom_teacher_fte",
    "teaching_assistant_fte",
    "support_staff_fte",
    "teachers_without_qts_fte",
    "part_time_teacher_pct",
    "pupil_qualified_teacher_ratio",
    "pupil_teacher_ratio",
    "pupil_adult_ratio",
    "workforce_source",
    "workforce_source_dataset_id",
    "workforce_ratio_source",
    "workforce_ratio_source_dataset_id",
)

PASTORAL_COLUMNS = (
    "parent_view_as_at_date",
    "parent_view_survey_year",
    "parent_view_questionnaire_version",
    "pastoral_response_count",
    "happy_pct",
    "safe_pct",
    "behaviour_positive_pct",
    "bullying_dealt_with_pct",
    "send_support_pct",
    "communication_pct",
    "concerns_dealt_with_pct",
    "best_interests_pct",
    "learning_support_pct",
    "personal_development_pct",
    "recommend_pct",
    "pastoral_score",
    "pastoral_score_coverage_pct",
    "pastoral_source",
    "pastoral_source_url",
)

DESTINATION_COLUMNS = (
    "destination_leaver_year",
    "destination_year",
    "destination_pupil_count",
    "sustained_destination_pct",
    "education_destination_pct",
    "apprenticeship_destination_pct",
    "employment_destination_pct",
    "not_sustained_destination_pct",
    "unknown_destination_pct",
    "destination_source",
    "destination_source_dataset_id",
)


def _lineage_graph(
    schools: pd.DataFrame,
    links: pd.DataFrame,
) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str]]:
    predecessors: dict[str, list[str]] = {}
    predecessor_names: dict[str, str] = {}
    if not links.empty:
        for _, row in links.iterrows():
            successor = str(row.get("successor_urn", "")).strip()
            predecessor = str(row.get("predecessor_urn", "")).strip()
            if not successor or not predecessor:
                continue
            predecessors.setdefault(successor, [])
            if predecessor not in predecessors[successor]:
                predecessors[successor].append(predecessor)
            name = str(row.get("predecessor_name", "")).strip()
            if name:
                predecessor_names[predecessor] = name

    current_names = {
        str(row["urn"]).strip(): str(row.get("school_name", "")).strip()
        for _, row in schools.iterrows()
    }
    return predecessors, predecessor_names, current_names


def _has_domain_quality(row: pd.Series | None, columns: tuple[str, ...]) -> bool:
    if row is None:
        return False
    return any(
        pd.notna(row.get(column)) and str(row.get(column)).strip()
        for column in columns
    )


def resolve_domain_lineage(
    schools: pd.DataFrame,
    links: pd.DataFrame,
    data: pd.DataFrame,
    *,
    data_columns: tuple[str, ...],
    quality_columns: tuple[str, ...],
    source_prefix: str,
) -> pd.DataFrame:
    data_rows = {
        str(row["urn"]).strip(): row
        for _, row in data.iterrows()
        if str(row.get("urn", "")).strip()
    }
    predecessors, predecessor_names, current_names = _lineage_graph(schools, links)
    names = {**predecessor_names, **current_names}

    resolved: list[dict[str, Any]] = []
    for current_urn, current_name in current_names.items():
        source_urn = current_urn
        source_row = data_rows.get(current_urn)
        source_kind: str | None = "current"
        depth: int | None = 0

        if not _has_domain_quality(source_row, quality_columns):
            source_row = None
            source_urn = current_urn
            source_kind = None
            depth = None
            cursor = current_urn
            visited = {current_urn}
            link_depth = 0
            while True:
                candidates = predecessors.get(cursor, [])
                if len(candidates) != 1:
                    break
                predecessor_urn = candidates[0]
                if predecessor_urn in visited:
                    break
                visited.add(predecessor_urn)
                link_depth += 1
                candidate_row = data_rows.get(predecessor_urn)
                if _has_domain_quality(candidate_row, quality_columns):
                    source_urn = predecessor_urn
                    source_row = candidate_row
                    source_kind = "predecessor"
                    depth = link_depth
                    break
                cursor = predecessor_urn

        record = {
            column: (source_row.get(column, pd.NA) if source_row is not None else pd.NA)
            for column in data_columns
        }
        record["urn"] = current_urn
        record.update(
            {
                f"{source_prefix}_source_urn": source_urn if source_row is not None else None,
                f"{source_prefix}_source_school_name": (
                    (names.get(source_urn) or current_name) if source_row is not None else None
                ),
                f"{source_prefix}_source_kind": source_kind,
                f"{source_prefix}_source_link_depth": depth,
            }
        )
        resolved.append(record)

    columns = [
        "urn",
        *data_columns,
        f"{source_prefix}_source_urn",
        f"{source_prefix}_source_school_name",
        f"{source_prefix}_source_kind",
        f"{source_prefix}_source_link_depth",
    ]
    return pd.DataFrame.from_records(resolved, columns=columns)


def combine_benchmarks(*frames: pd.DataFrame) -> pd.DataFrame:
    """Combine domain benchmark frames into one row per geography."""
    identity = ["benchmark_level", "benchmark_code"]
    result: pd.DataFrame | None = None
    for index, frame in enumerate(frames):
        if frame.empty:
            continue
        work = frame.copy()
        name_column = f"_benchmark_name_{index}"
        work = work.rename(columns={"benchmark_name": name_column})
        if result is None:
            result = work
        else:
            result = result.merge(work, on=identity, how="outer", validate="one_to_one")

    if result is None:
        return pd.DataFrame(columns=[*identity, "benchmark_name"])

    name_columns = [column for column in result.columns if column.startswith("_benchmark_name_")]
    result["benchmark_name"] = result[name_columns].bfill(axis=1).iloc[:, 0]
    result = result.drop(columns=name_columns)
    order = result["benchmark_level"].fillna("").astype("string").str.casefold().map(
        {"national": 0, "local authority": 1}
    )
    return (
        result.assign(_level_order=order.fillna(2))
        .sort_values(["_level_order", "benchmark_name"], kind="stable")
        .drop(columns="_level_order")
        .reset_index(drop=True)
    )


def _has_ofsted_quality(row: pd.Series | None) -> bool:
    if row is None:
        return False
    return any(pd.notna(row.get(column)) and str(row.get(column)).strip() for column in OFSTED_QUALITY_COLUMNS)


def resolve_ofsted_lineage(
    schools: pd.DataFrame,
    links: pd.DataFrame,
    ofsted: pd.DataFrame,
) -> pd.DataFrame:
    """Resolve Ofsted data to current schools using unambiguous predecessor chains."""
    if ofsted.empty:
        columns = ["urn", *OFSTED_QUALITY_COLUMNS, "ofsted_source_urn",
                   "ofsted_source_school_name", "ofsted_source_kind",
                   "ofsted_source_link_depth"]
        return pd.DataFrame(columns=columns)

    ofsted_rows = {
        str(row["urn"]).strip(): row
        for _, row in ofsted.iterrows()
        if str(row.get("urn", "")).strip()
    }

    predecessors: dict[str, list[str]] = {}
    predecessor_names: dict[str, str] = {}
    if not links.empty:
        for _, row in links.iterrows():
            successor = str(row.get("successor_urn", "")).strip()
            predecessor = str(row.get("predecessor_urn", "")).strip()
            if not successor or not predecessor:
                continue
            predecessors.setdefault(successor, [])
            if predecessor not in predecessors[successor]:
                predecessors[successor].append(predecessor)
            name = str(row.get("predecessor_name", "")).strip()
            if name:
                predecessor_names[predecessor] = name

    current_names = {
        str(row["urn"]).strip(): str(row.get("school_name", "")).strip()
        for _, row in schools.iterrows()
    }
    names = {**predecessor_names, **current_names}

    resolved: list[dict[str, Any]] = []
    for current_urn, current_name in current_names.items():
        source_urn = current_urn
        source_row = ofsted_rows.get(current_urn)
        source_kind = "current"
        depth = 0

        if not _has_ofsted_quality(source_row):
            source_row = None
            source_kind = "predecessor"
            cursor = current_urn
            visited = {current_urn}
            while True:
                candidates = predecessors.get(cursor, [])
                if len(candidates) != 1:
                    break
                predecessor_urn = candidates[0]
                if predecessor_urn in visited:
                    break
                visited.add(predecessor_urn)
                depth += 1
                candidate_row = ofsted_rows.get(predecessor_urn)
                if _has_ofsted_quality(candidate_row):
                    source_urn = predecessor_urn
                    source_row = candidate_row
                    break
                cursor = predecessor_urn

        if source_row is None:
            continue

        record = {column: source_row.get(column, pd.NA) for column in OFSTED_QUALITY_COLUMNS}
        record.update(
            {
                "urn": current_urn,
                "ofsted_source_urn": source_urn,
                "ofsted_source_school_name": names.get(source_urn) or current_name,
                "ofsted_source_kind": source_kind,
                "ofsted_source_link_depth": depth,
            }
        )
        resolved.append(record)

    columns = [
        "urn",
        *OFSTED_QUALITY_COLUMNS,
        "ofsted_source_urn",
        "ofsted_source_school_name",
        "ofsted_source_kind",
        "ofsted_source_link_depth",
    ]
    return pd.DataFrame.from_records(resolved, columns=columns)


def resolve_progress8_lineage(
    schools: pd.DataFrame,
    links: pd.DataFrame,
    performance: pd.DataFrame,
) -> pd.DataFrame:

    performance_rows = {
        str(row["urn"]).strip(): row
        for _, row in performance.iterrows()
        if str(row.get("urn", "")).strip()
    }

    predecessors: dict[str, list[str]] = {}
    predecessor_names: dict[str, str] = {}
    if not links.empty:
        for _, row in links.iterrows():
            successor = str(row.get("successor_urn", "")).strip()
            predecessor = str(row.get("predecessor_urn", "")).strip()
            if not successor or not predecessor:
                continue
            predecessors.setdefault(successor, [])
            if predecessor not in predecessors[successor]:
                predecessors[successor].append(predecessor)
            name = str(row.get("predecessor_name", "")).strip()
            if name:
                predecessor_names[predecessor] = name

    current_names = {
        str(row["urn"]).strip(): str(row.get("school_name", "")).strip()
        for _, row in schools.iterrows()
    }
    names = {**predecessor_names, **current_names}

    resolved: list[dict[str, Any]] = []
    for current_urn, current_name in current_names.items():
        current_row = performance_rows.get(current_urn)
        record = {
            column: (
                current_row.get(column, pd.NA)
                if current_row is not None
                else pd.NA
            )
            for column in KS4_PERFORMANCE_COLUMNS
        }
        record["urn"] = current_urn

        progress8 = record["progress8"]
        source_urn: str | None = None
        source_kind: str | None = None
        depth: int | None = None

        if pd.notna(progress8):
            source_urn = current_urn
            source_kind = "current"
            depth = 0
        else:
            cursor = current_urn
            visited = {current_urn}
            link_depth = 0
            while True:
                candidates = predecessors.get(cursor, [])
                if len(candidates) != 1:
                    break
                predecessor_urn = candidates[0]
                if predecessor_urn in visited:
                    break
                visited.add(predecessor_urn)
                link_depth += 1
                candidate_row = performance_rows.get(predecessor_urn)
                if candidate_row is not None and pd.notna(candidate_row.get("progress8")):
                    for column in PROGRESS8_METRIC_COLUMNS:
                        record[column] = candidate_row.get(column, pd.NA)
                    source_urn = predecessor_urn
                    source_kind = "predecessor"
                    depth = link_depth
                    break
                cursor = predecessor_urn

        record.update(
            {
                "progress8_source_urn": source_urn,
                "progress8_source_school_name": (
                    names.get(source_urn) if source_urn is not None else None
                ) or (current_name if source_urn == current_urn else None),
                "progress8_source_kind": source_kind,
                "progress8_source_link_depth": depth,
            }
        )
        resolved.append(record)

    columns = ["urn", *KS4_PERFORMANCE_COLUMNS, *PROGRESS8_SOURCE_COLUMNS]
    return pd.DataFrame.from_records(resolved, columns=columns)


def enrich_school_quality(
    schools: pd.DataFrame,
    ofsted: pd.DataFrame,
    performance: pd.DataFrame,
    links: pd.DataFrame | None = None,
) -> pd.DataFrame:
    resolved_ofsted = (
        resolve_ofsted_lineage(schools, links, ofsted)
        if links is not None
        else ofsted
    )
    resolved_performance = (
        resolve_progress8_lineage(schools, links, performance)
        if links is not None
        else performance
    )
    enriched = schools.merge(resolved_ofsted, on="urn", how="left", validate="one_to_one")
    enriched = enriched.merge(
        resolved_performance, on="urn", how="left", validate="one_to_one"
    )
    return enriched


def enrich_school_context(
    schools: pd.DataFrame,
    attendance: pd.DataFrame,
    behaviour: pd.DataFrame,
    workforce: pd.DataFrame,
    destinations: pd.DataFrame | None = None,
    *,
    links: pd.DataFrame | None = None,
) -> pd.DataFrame:
    domains = [
        (
            attendance,
            ATTENDANCE_COLUMNS,
            ("attendance_enrolments", "overall_absence_pct", "persistent_absence_pct"),
            "attendance",
        ),
        (
            behaviour,
            BEHAVIOUR_COLUMNS,
            ("behaviour_pupil_headcount", "suspension_count", "permanent_exclusion_count"),
            "behaviour",
        ),
        (
            workforce,
            WORKFORCE_COLUMNS,
            ("pupil_fte", "teacher_fte", "support_staff_fte"),
            "workforce",
        ),
    ]
    if destinations is not None:
        domains.append(
            (
                destinations,
                DESTINATION_COLUMNS,
                ("destination_pupil_count", "sustained_destination_pct"),
                "destination",
            )
        )
    enriched = schools
    for frame, columns, quality_columns, prefix in domains:
        resolved = (
            resolve_domain_lineage(
                schools,
                links,
                frame,
                data_columns=columns,
                quality_columns=quality_columns,
                source_prefix=prefix,
            )
            if links is not None
            else frame
        )
        enriched = enriched.merge(resolved, on="urn", how="left", validate="one_to_one")
    return enriched


def enrich_school_pastoral(
    schools: pd.DataFrame,
    pastoral: pd.DataFrame,
) -> pd.DataFrame:
    """Attach current-URN Parent View data without inheriting predecessor opinions."""
    return schools.merge(pastoral, on="urn", how="left", validate="one_to_one")


def build_datasets(
    data_dir: Path,
    *,
    force: bool = False,
    onspd_item_id: str | None = None,
) -> BuildResult:
    require_pyarrow()
    data_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = data_dir / MANIFEST_FILENAME
    schools_path = data_dir / SCHOOLS_FILENAME
    postcodes_path = data_dir / POSTCODES_FILENAME
    benchmarks_path = data_dir / BENCHMARKS_FILENAME
    subjects_path = data_dir / SUBJECTS_FILENAME
    existing_manifest = read_manifest(manifest_path)

    session = create_session()
    gias_source = discover_latest_gias_source(session)
    gias_links_source = discover_latest_gias_links_source(
        session, today=gias_source.source_date
    )
    onspd_source = discover_latest_onspd_source(
        session,
        item_id_override=onspd_item_id,
    )
    ofsted_source = discover_latest_ofsted_source(session)
    legacy_ofsted_source = discover_latest_legacy_ofsted_source(session)
    independent_ofsted_source = discover_latest_independent_ofsted_source(session)
    ks4_source = discover_ks4_source(session)
    ks4_subject_source = discover_ks4_subject_source(session)
    destination_source = discover_destination_school_source(session)
    attendance_source = discover_attendance_school_source(session)
    behaviour_source = discover_behaviour_school_source(session)
    workforce_source = discover_workforce_school_source(session)
    workforce_ratio_source = discover_workforce_ratio_school_source(session)
    parent_view_source = discover_parent_view_source(session)

    ks4_benchmark_source = discover_ks4_benchmark_source(session)
    destination_national_source = discover_destination_national_source(session)
    destination_la_source = discover_destination_la_source(session)
    attendance_benchmark_source = discover_attendance_benchmark_source(session)
    behaviour_benchmark_source = discover_behaviour_benchmark_source(session)
    workforce_benchmark_source = discover_workforce_benchmark_source(session)
    workforce_ratio_benchmark_source = discover_workforce_ratio_benchmark_source(session)

    gias_source_manifest = gias_manifest(gias_source)
    gias_links_source_manifest = gias_links_manifest(gias_links_source)
    onspd_source_manifest = onspd_manifest(onspd_source)
    ofsted_source_manifest = csv_source_manifest(ofsted_source)
    legacy_ofsted_source_manifest = csv_source_manifest(legacy_ofsted_source)
    independent_ofsted_source_manifest = csv_source_manifest(independent_ofsted_source)
    ks4_source_manifest = csv_source_manifest(ks4_source)
    ks4_subject_source_manifest = csv_source_manifest(ks4_subject_source)
    destination_source_manifest = csv_source_manifest(destination_source)
    attendance_source_manifest = csv_source_manifest(attendance_source)
    behaviour_source_manifest = csv_source_manifest(behaviour_source)
    workforce_source_manifest = csv_source_manifest(workforce_source)
    workforce_ratio_source_manifest = csv_source_manifest(workforce_ratio_source)
    parent_view_source_manifest = csv_source_manifest(parent_view_source)
    ks4_benchmark_source_manifest = csv_source_manifest(ks4_benchmark_source)
    destination_national_source_manifest = csv_source_manifest(destination_national_source)
    destination_la_source_manifest = csv_source_manifest(destination_la_source)
    attendance_benchmark_source_manifest = csv_source_manifest(attendance_benchmark_source)
    behaviour_benchmark_source_manifest = csv_source_manifest(behaviour_benchmark_source)
    workforce_benchmark_source_manifest = csv_source_manifest(workforce_benchmark_source)
    workforce_ratio_benchmark_source_manifest = csv_source_manifest(
        workforce_ratio_benchmark_source
    )

    schools_current = (
        not force
        and schools_path.exists()
        and existing_manifest is not None
        and existing_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and source_matches(existing_manifest, "gias", gias_source_manifest, ("source_date", "download_url"))
        and source_matches(existing_manifest, "gias_links", gias_links_source_manifest, ("source_date", "download_url"))
        and source_matches(existing_manifest, "ofsted", ofsted_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "ofsted_legacy", legacy_ofsted_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "ofsted_independent", independent_ofsted_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "ks4_performance", ks4_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "destinations_school", destination_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "attendance_school", attendance_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "behaviour_school", behaviour_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "workforce_school", workforce_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "workforce_ratio_school", workforce_ratio_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "parent_view_school", parent_view_source_manifest, ("release_label", "download_url"))
    )
    subjects_current = (
        not force
        and subjects_path.exists()
        and existing_manifest is not None
        and existing_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and source_matches(
            existing_manifest,
            "ks4_subjects",
            ks4_subject_source_manifest,
            ("release_label", "download_url"),
        )
    )
    postcodes_current = (
        not force
        and postcodes_path.exists()
        and existing_manifest is not None
        and existing_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and source_matches(
            existing_manifest,
            "onspd",
            onspd_source_manifest,
            ("arcgis_item_id", "modified_at"),
        )
    )
    benchmarks_current = (
        not force
        and benchmarks_path.exists()
        and existing_manifest is not None
        and existing_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and source_matches(existing_manifest, "ks4_benchmarks", ks4_benchmark_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "destinations_national", destination_national_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "destinations_local_authority", destination_la_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "attendance_benchmarks", attendance_benchmark_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "behaviour_benchmarks", behaviour_benchmark_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "workforce_benchmarks", workforce_benchmark_source_manifest, ("release_label", "download_url"))
        and source_matches(existing_manifest, "workforce_ratio_benchmarks", workforce_ratio_benchmark_source_manifest, ("release_label", "download_url"))
    )

    if (
        schools_current
        and postcodes_current
        and benchmarks_current
        and subjects_current
        and existing_manifest is not None
    ):
        log("Datasets are current; leaving all files unchanged.")
        return BuildResult(False, False, False, existing_manifest, False, False)

    with tempfile.TemporaryDirectory(
        prefix=".school-finder-build-",
        dir=data_dir,
    ) as temp_name:
        temp_dir = Path(temp_name)
        staged_schools: Path | None = None
        staged_postcodes: Path | None = None
        staged_benchmarks: Path | None = None
        staged_subjects: Path | None = None

        if schools_current:
            log(f"GIAS source unchanged; keeping {schools_path}.")
        else:
            gias_csv = temp_dir / "gias.csv"
            gias_links_csv = temp_dir / "gias_links.csv"
            download_gias_csv(session, gias_source, gias_csv)
            download_gias_links_csv(session, gias_links_source, gias_links_csv)
            log("Cleaning GIAS establishments and predecessor links...")
            raw_gias = read_gias_csv(gias_csv)
            schools = clean_gias_data(raw_gias, gias_source)
            gias_links = clean_gias_links_data(
                read_gias_links_csv(gias_links_csv),
                raw_gias,
                gias_links_source,
            )

            ofsted_csv = temp_dir / "ofsted.csv"
            legacy_ofsted_csv = temp_dir / "ofsted_legacy.csv"
            independent_ofsted_csv = temp_dir / "ofsted_independent.csv"
            ks4_csv = temp_dir / "ks4_performance.csv"
            attendance_csv = temp_dir / "attendance.csv"
            behaviour_csv = temp_dir / "behaviour.csv"
            workforce_csv = temp_dir / "workforce.csv"
            workforce_ratio_csv = temp_dir / "workforce_ratios.csv"
            destination_csv = temp_dir / "destinations.csv"
            parent_view_ods = temp_dir / "parent_view.ods"
            download_csv(session, ofsted_source, ofsted_csv)
            download_csv(session, legacy_ofsted_source, legacy_ofsted_csv)
            download_csv(session, independent_ofsted_source, independent_ofsted_csv)
            download_csv(session, ks4_source, ks4_csv)
            download_csv(session, attendance_source, attendance_csv)
            download_csv(session, behaviour_source, behaviour_csv)
            download_csv(session, workforce_source, workforce_csv)
            download_csv(session, workforce_ratio_source, workforce_ratio_csv)
            download_csv(session, destination_source, destination_csv)
            download_csv(session, parent_view_source, parent_view_ods, minimum_size=100_000)
            log("Enriching schools with Ofsted and DfE performance data...")
            ofsted = combine_ofsted_quality(
                read_ofsted_quality(legacy_ofsted_csv),
                read_ofsted_quality(ofsted_csv),
                read_ofsted_quality(independent_ofsted_csv),
            )
            schools = enrich_school_quality(
                schools,
                ofsted,
                read_ks4_quality(ks4_csv),
                links=gias_links,
            )
            log("Enriching schools with attendance, behaviour, workforce and destination data...")
            schools = enrich_school_context(
                schools,
                read_attendance_school(attendance_csv),
                read_behaviour_school(behaviour_csv),
                read_workforce_school(workforce_csv, workforce_ratio_csv),
                read_destination_school(destination_csv),
                links=gias_links,
            )
            log("Enriching schools with Ofsted Parent View pastoral-care data...")
            schools = enrich_school_pastoral(schools, read_parent_view_school(parent_view_ods))
            if len(schools) < 10_000:
                raise SchoolFinderError(
                    f"GIAS produced only {len(schools):,} open establishments; "
                    "refusing to publish a probably incomplete dataset."
                )
            staged_schools = temp_dir / SCHOOLS_FILENAME
            log(f"Staging {SCHOOLS_FILENAME} ({len(schools):,} rows)...")
            write_parquet_file(schools, staged_schools)

        if subjects_current:
            log(f"DfE subject source unchanged; keeping {subjects_path}.")
        else:
            subject_csv = temp_dir / "ks4_subjects.csv"
            download_csv(session, ks4_subject_source, subject_csv)
            log("Cleaning school-level KS4 subject results...")
            subjects = read_ks4_subjects(subject_csv)
            if subjects.empty:
                raise SchoolFinderError("DfE KS4 subject data produced no usable rows.")
            staged_subjects = temp_dir / SUBJECTS_FILENAME
            log(f"Staging {SUBJECTS_FILENAME} ({len(subjects):,} rows)...")
            write_parquet_file(subjects, staged_subjects)

        if postcodes_current:
            log(f"ONSPD source unchanged; keeping {postcodes_path}.")
        else:
            onspd_zip = temp_dir / "onspd.zip"
            download_onspd_zip(session, onspd_source, onspd_zip)
            log("Cleaning current and terminated English postcodes...")
            postcodes = clean_onspd_data(onspd_zip, onspd_source)
            staged_postcodes = temp_dir / POSTCODES_FILENAME
            log(f"Staging {POSTCODES_FILENAME} ({len(postcodes):,} rows)...")
            write_parquet_file(postcodes, staged_postcodes)

        if benchmarks_current:
            log(f"DfE benchmark source unchanged; keeping {benchmarks_path}.")
        else:
            benchmark_csv = temp_dir / "ks4_benchmarks.csv"
            destination_national_csv = temp_dir / "destination_national.csv"
            destination_la_csv = temp_dir / "destination_local_authority.csv"
            attendance_benchmark_csv = temp_dir / "attendance_benchmarks.csv"
            behaviour_benchmark_csv = temp_dir / "behaviour_benchmarks.csv"
            workforce_benchmark_csv = temp_dir / "workforce_benchmarks.csv"
            workforce_ratio_benchmark_csv = temp_dir / "workforce_ratio_benchmarks.csv"
            download_csv(session, ks4_benchmark_source, benchmark_csv)
            download_csv(session, destination_national_source, destination_national_csv)
            download_csv(session, destination_la_source, destination_la_csv)
            download_csv(session, attendance_benchmark_source, attendance_benchmark_csv)
            download_csv(session, behaviour_benchmark_source, behaviour_benchmark_csv)
            download_csv(session, workforce_benchmark_source, workforce_benchmark_csv)
            download_csv(
                session,
                workforce_ratio_benchmark_source,
                workforce_ratio_benchmark_csv,
            )
            log("Cleaning national and local-authority benchmark data...")
            benchmarks = combine_benchmarks(
                read_ks4_benchmarks(benchmark_csv),
                read_destination_benchmarks(destination_national_csv, destination_la_csv),
                read_attendance_benchmarks(attendance_benchmark_csv),
                read_behaviour_benchmarks(behaviour_benchmark_csv),
                read_workforce_benchmarks(
                    workforce_benchmark_csv, workforce_ratio_benchmark_csv
                ),
            )
            if benchmarks.empty:
                raise SchoolFinderError(
                    "DfE benchmark data produced no usable benchmark rows."
                )
            staged_benchmarks = temp_dir / BENCHMARKS_FILENAME
            log(f"Staging {BENCHMARKS_FILENAME} ({len(benchmarks):,} rows)...")
            write_parquet_file(benchmarks, staged_benchmarks)

        if staged_schools is not None:
            os.replace(staged_schools, schools_path)
        if staged_postcodes is not None:
            os.replace(staged_postcodes, postcodes_path)
        if staged_benchmarks is not None:
            os.replace(staged_benchmarks, benchmarks_path)
        if staged_subjects is not None:
            os.replace(staged_subjects, subjects_path)

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_version": (
            f"gias-{gias_source.source_date.isoformat()}__"
            f"onspd-{onspd_source.release_date.strftime('%Y-%m')}"
        ),
        "generated_at": iso_utc(utc_now()),
        "coverage": "England",
        "files": {
            SCHOOLS_FILENAME: parquet_metadata(schools_path),
            POSTCODES_FILENAME: parquet_metadata(postcodes_path),
            BENCHMARKS_FILENAME: parquet_metadata(benchmarks_path),
            SUBJECTS_FILENAME: parquet_metadata(subjects_path),
        },
        "sources": {
            "gias": gias_source_manifest,
            "gias_links": gias_links_source_manifest,
            "onspd": onspd_source_manifest,
            "ofsted": ofsted_source_manifest,
            "ofsted_legacy": legacy_ofsted_source_manifest,
            "ofsted_independent": independent_ofsted_source_manifest,
            "ks4_performance": ks4_source_manifest,
            "ks4_subjects": ks4_subject_source_manifest,
            "destinations_school": destination_source_manifest,
            "attendance_school": attendance_source_manifest,
            "behaviour_school": behaviour_source_manifest,
            "workforce_school": workforce_source_manifest,
            "workforce_ratio_school": workforce_ratio_source_manifest,
            "parent_view_school": parent_view_source_manifest,
            "ks4_benchmarks": ks4_benchmark_source_manifest,
            "destinations_national": destination_national_source_manifest,
            "destinations_local_authority": destination_la_source_manifest,
            "attendance_benchmarks": attendance_benchmark_source_manifest,
            "behaviour_benchmarks": behaviour_benchmark_source_manifest,
            "workforce_benchmarks": workforce_benchmark_source_manifest,
            "workforce_ratio_benchmarks": workforce_ratio_benchmark_source_manifest,
        },
    }
    log(f"Writing {manifest_path}...")
    write_json_atomic(manifest, manifest_path)

    return BuildResult(
        schools_updated=not schools_current,
        postcodes_updated=not postcodes_current,
        manifest_updated=True,
        manifest=manifest,
        benchmarks_updated=not benchmarks_current,
        subjects_updated=not subjects_current,
    )
