"""Command-line presentation adapter for School Finder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from school_finder.config import (
    DEFAULT_DATA_DIR,
    MANIFEST_FILENAME,
    POSTCODES_FILENAME,
    SCHOOLS_FILENAME,
)
from school_finder.data.build import build_datasets
from school_finder.errors import SchoolFinderError
from school_finder.models.filters import (
    FaithFilter,
    OfstedRating,
    SchoolGender,
    SchoolPhase,
    SchoolSector,
    SchoolSort,
    SchoolSortField,
    SelectionFilter,
    SortDirection,
)
from school_finder.models.search import SchoolSearchRequest
from school_finder.services.search import search_schools
from school_finder.utils import log


def _enum_parser(enum_type):
    def parse(value: str):
        normalised = value.strip().casefold().replace("_", "-")
        for member in enum_type:
            candidates = {
                member.value.casefold(),
                member.name.casefold().replace("_", "-"),
            }
            if normalised in candidates:
                return member
        allowed = ", ".join(member.value for member in enum_type)
        raise argparse.ArgumentTypeError(
            f"invalid value '{value}'; choose from: {allowed}"
        )

    return parse


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and query Parquet data for an English school finder."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser(
        "build",
        help="Generate or refresh manifest.json and both Parquet datasets.",
    )
    build.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Output directory (default: {DEFAULT_DATA_DIR})",
    )
    build.add_argument(
        "--force",
        action="store_true",
        help="Rebuild both datasets even when source versions are unchanged.",
    )
    build.add_argument(
        "--onspd-item-id",
        help="Use a specific ArcGIS ONSPD CSV Collection item ID.",
    )
    build.add_argument(
        "--json",
        action="store_true",
        help="Print the resulting manifest as JSON.",
    )

    lookup = commands.add_parser(
        "lookup",
        help="Find nearby secondary schools using the generated data.",
    )
    lookup.add_argument("postcode", help="English postcode, e.g. RG22 4XX")
    lookup.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Dataset directory (default: {DEFAULT_DATA_DIR})",
    )
    lookup.add_argument("--limit", type=int, default=20)
    lookup.add_argument("--entry-age", type=int, default=11)
    lookup.add_argument("--minimum-exit-age", type=int, default=16)
    lookup.add_argument("--radius", dest="radius_miles", type=float)
    lookup.add_argument(
        "--phase",
        action="append",
        type=_enum_parser(SchoolPhase),
        default=[],
        help="Filter by phase; repeat to allow multiple phases.",
    )
    lookup.add_argument(
        "--sector",
        action="append",
        type=_enum_parser(SchoolSector),
        default=[],
        help="Filter by sector; repeat to allow multiple sectors.",
    )
    lookup.add_argument(
        "--gender",
        action="append",
        type=_enum_parser(SchoolGender),
        default=[],
        help="Filter by gender; repeat to allow multiple values.",
    )
    lookup.add_argument(
        "--faith",
        type=_enum_parser(FaithFilter),
        default=FaithFilter.ANY,
        help="Filter by religious character.",
    )
    lookup.add_argument(
        "--selection",
        type=_enum_parser(SelectionFilter),
        default=SelectionFilter.ANY,
        help="Filter by selective/non-selective admissions.",
    )
    lookup.add_argument("--include-special", action="store_true")
    lookup.add_argument(
        "--minimum-ofsted",
        dest="minimum_ofsted_rating",
        type=_enum_parser(OfstedRating),
        help=(
            "Minimum School Finder equivalent Ofsted rating. Official overall "
            "grades are used where available; otherwise an equivalent is derived "
            "from published inspection judgements."
        ),
    )
    lookup.add_argument("--minimum-attainment8", type=float)
    lookup.add_argument("--minimum-progress8", type=float)
    lookup.add_argument(
        "--minimum-grade5-english-maths",
        dest="minimum_grade5_english_maths_pct",
        type=float,
    )
    lookup.add_argument("--minimum-ebacc-aps", type=float)
    lookup.add_argument(
        "--sort",
        type=_enum_parser(SchoolSortField),
        default=SchoolSortField.DISTANCE,
    )
    lookup.add_argument(
        "--descending",
        action="store_true",
        help="Sort the selected field in descending order.",
    )
    output = lookup.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        help="Print the existing flat lookup rows as JSON.",
    )
    output.add_argument(
        "--structured-json",
        action="store_true",
        help="Print nested SchoolResult objects used by application layers.",
    )
    return parser


def _run_build(args: argparse.Namespace) -> int:
    result = build_datasets(
        args.data_dir,
        force=args.force,
        onspd_item_id=args.onspd_item_id,
    )
    if args.json:
        print(json.dumps(result.manifest, indent=2, ensure_ascii=False))
    elif result.manifest_updated:
        updated = []
        if result.schools_updated:
            updated.append(SCHOOLS_FILENAME)
        if result.postcodes_updated:
            updated.append(POSTCODES_FILENAME)
        print("Updated: " + ", ".join(updated))
        print(f"Published: {args.data_dir / MANIFEST_FILENAME}")
    else:
        print("Datasets are already current; no files were changed.")
    return 0


def _run_lookup(args: argparse.Namespace) -> int:
    result = search_schools(
        args.data_dir,
        SchoolSearchRequest(
            postcode=args.postcode,
            limit=args.limit,
            entry_age=args.entry_age,
            minimum_exit_age=args.minimum_exit_age,
            include_special=args.include_special,
            radius_miles=args.radius_miles,
            phases=tuple(args.phase),
            sectors=tuple(args.sector),
            genders=tuple(args.gender),
            faith=args.faith,
            selection=args.selection,
            minimum_ofsted_rating=args.minimum_ofsted_rating,
            minimum_attainment8=args.minimum_attainment8,
            minimum_progress8=args.minimum_progress8,
            minimum_grade5_english_maths_pct=args.minimum_grade5_english_maths_pct,
            minimum_ebacc_aps=args.minimum_ebacc_aps,
            sort=SchoolSort(
                field=args.sort,
                direction=(
                    SortDirection.DESC if args.descending else SortDirection.ASC
                ),
            ),
        ),
    )

    if not result.postcode.is_current:
        detail = (
            f" in {result.postcode.termination_date}"
            if result.postcode.termination_date
            else ""
        )
        log(
            f"Warning: {result.postcode.postcode} is marked as terminated"
            f"{detail}; using its last known ONSPD coordinates."
        )

    if args.structured_json:
        payload = [school.to_dict() for school in result.schools]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif args.json:
        print(json.dumps(list(result.flat_records), indent=2, ensure_ascii=False))
    else:
        if not result.schools:
            print(f"No schools matched the search around {result.postcode.postcode}.")
            return 0
        print(
            f"Found {len(result.schools)} schools matching search around "
            f"{result.postcode.postcode}:\n"
        )
        display = pd.DataFrame(result.flat_records)[
            [
                "school_name",
                "distance_miles",
                "sector",
                "establishment_type",
                "age_range",
                "faith_status",
                "ofsted_equivalent_rating",
                "ofsted_inspection_date",
                "ofsted_source_school_name",
                "attainment8",
                "progress8",
                "progress8_year",
                "town",
                "postcode",
                "urn",
            ]
        ].copy()
        display.index = range(1, len(display) + 1)
        display.index.name = "#"
        print(display.to_string())
    return 0


def main() -> int:
    args = create_parser().parse_args()
    try:
        if args.command == "build":
            return _run_build(args)
        return _run_lookup(args)
    except (SchoolFinderError, OSError, ImportError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
