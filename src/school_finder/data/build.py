"""Dataset build orchestration."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from school_finder.config import (
    MANIFEST_FILENAME,
    MANIFEST_SCHEMA_VERSION,
    POSTCODES_FILENAME,
    SCHOOLS_FILENAME,
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
    "attainment8",
    "english_maths_grade5_pct",
    "english_maths_grade4_pct",
    "ebacc_entry_pct",
    "ebacc_aps",
    "progress8",
    "progress8_year",
)

PROGRESS8_SOURCE_COLUMNS = (
    "progress8_source_urn",
    "progress8_source_school_name",
    "progress8_source_kind",
    "progress8_source_link_depth",
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
                    record["progress8"] = candidate_row.get("progress8")
                    record["progress8_year"] = candidate_row.get("progress8_year", pd.NA)
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
    gias_source_manifest = gias_manifest(gias_source)
    gias_links_source_manifest = gias_links_manifest(gias_links_source)
    onspd_source_manifest = onspd_manifest(onspd_source)
    ofsted_source_manifest = csv_source_manifest(ofsted_source)
    legacy_ofsted_source_manifest = csv_source_manifest(legacy_ofsted_source)
    independent_ofsted_source_manifest = csv_source_manifest(independent_ofsted_source)
    ks4_source_manifest = csv_source_manifest(ks4_source)

    schools_current = (
        not force
        and schools_path.exists()
        and existing_manifest is not None
        and existing_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION
        and source_matches(
            existing_manifest,
            "gias",
            gias_source_manifest,
            ("source_date", "download_url"),
        )
        and source_matches(
            existing_manifest,
            "gias_links",
            gias_links_source_manifest,
            ("source_date", "download_url"),
        )
        and source_matches(
            existing_manifest,
            "ofsted",
            ofsted_source_manifest,
            ("release_label", "download_url"),
        )
        and source_matches(
            existing_manifest,
            "ofsted_legacy",
            legacy_ofsted_source_manifest,
            ("release_label", "download_url"),
        )
        and source_matches(
            existing_manifest,
            "ofsted_independent",
            independent_ofsted_source_manifest,
            ("release_label", "download_url"),
        )
        and source_matches(
            existing_manifest,
            "ks4_performance",
            ks4_source_manifest,
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

    if schools_current and postcodes_current and existing_manifest is not None:
        log("Datasets are current; leaving all files unchanged.")
        return BuildResult(False, False, False, existing_manifest)

    with tempfile.TemporaryDirectory(
        prefix=".school-finder-build-",
        dir=data_dir,
    ) as temp_name:
        temp_dir = Path(temp_name)
        staged_schools: Path | None = None
        staged_postcodes: Path | None = None

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
            download_csv(session, ofsted_source, ofsted_csv)
            download_csv(session, legacy_ofsted_source, legacy_ofsted_csv)
            download_csv(session, independent_ofsted_source, independent_ofsted_csv)
            download_csv(session, ks4_source, ks4_csv)
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
            if len(schools) < 10_000:
                raise SchoolFinderError(
                    f"GIAS produced only {len(schools):,} open establishments; "
                    "refusing to publish a probably incomplete dataset."
                )
            staged_schools = temp_dir / SCHOOLS_FILENAME
            log(f"Staging {SCHOOLS_FILENAME} ({len(schools):,} rows)...")
            write_parquet_file(schools, staged_schools)

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

        if staged_schools is not None:
            os.replace(staged_schools, schools_path)
        if staged_postcodes is not None:
            os.replace(staged_postcodes, postcodes_path)

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
        },
        "sources": {
            "gias": gias_source_manifest,
            "gias_links": gias_links_source_manifest,
            "onspd": onspd_source_manifest,
            "ofsted": ofsted_source_manifest,
            "ofsted_legacy": legacy_ofsted_source_manifest,
            "ofsted_independent": independent_ofsted_source_manifest,
            "ks4_performance": ks4_source_manifest,
        },
    }
    log(f"Writing {manifest_path}...")
    write_json_atomic(manifest, manifest_path)

    return BuildResult(
        schools_updated=not schools_current,
        postcodes_updated=not postcodes_current,
        manifest_updated=True,
        manifest=manifest,
    )
