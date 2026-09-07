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
    discover_latest_gias_source,
    download_gias_csv,
    read_gias_csv,
)
from school_finder.data.sources.ks4 import discover_ks4_source, read_ks4_quality
from school_finder.data.sources.ofsted import (
    discover_latest_independent_ofsted_source,
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


def enrich_school_quality(
    schools: pd.DataFrame,
    ofsted: pd.DataFrame,
    performance: pd.DataFrame,
) -> pd.DataFrame:
    enriched = schools.merge(ofsted, on="urn", how="left", validate="one_to_one")
    enriched = enriched.merge(performance, on="urn", how="left", validate="one_to_one")
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
    onspd_source = discover_latest_onspd_source(
        session,
        item_id_override=onspd_item_id,
    )
    ofsted_source = discover_latest_ofsted_source(session)
    independent_ofsted_source = discover_latest_independent_ofsted_source(session)
    ks4_source = discover_ks4_source(session)
    gias_source_manifest = gias_manifest(gias_source)
    onspd_source_manifest = onspd_manifest(onspd_source)
    ofsted_source_manifest = csv_source_manifest(ofsted_source)
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
            "ofsted",
            ofsted_source_manifest,
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
            download_gias_csv(session, gias_source, gias_csv)
            log("Cleaning GIAS establishments...")
            schools = clean_gias_data(read_gias_csv(gias_csv), gias_source)

            ofsted_csv = temp_dir / "ofsted.csv"
            independent_ofsted_csv = temp_dir / "ofsted_independent.csv"
            ks4_csv = temp_dir / "ks4_performance.csv"
            download_csv(session, ofsted_source, ofsted_csv)
            download_csv(session, independent_ofsted_source, independent_ofsted_csv)
            download_csv(session, ks4_source, ks4_csv)
            log("Enriching schools with Ofsted and DfE performance data...")
            ofsted = pd.concat(
                [
                    read_ofsted_quality(ofsted_csv),
                    read_ofsted_quality(independent_ofsted_csv),
                ],
                ignore_index=True,
            ).sort_values(
                ["urn", "ofsted_publication_date", "ofsted_inspection_date"],
                kind="stable",
                na_position="first",
            ).drop_duplicates("urn", keep="last")
            schools = enrich_school_quality(
                schools,
                ofsted,
                read_ks4_quality(ks4_csv),
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
            "onspd": onspd_source_manifest,
            "ofsted": ofsted_source_manifest,
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
