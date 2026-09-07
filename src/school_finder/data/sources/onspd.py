"""ONS Postcode Directory source adapter."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd
import requests

from school_finder.errors import SchoolFinderError
from school_finder.data.sources.common import fetch_json, stream_download
from school_finder.utils import format_postcode, log, normalise_postcode

ARCGIS_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"

ARCGIS_ITEM_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}"

ARCGIS_ITEM_DATA_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
)

ENGLAND_COUNTRY_CODE = "E92000001"

ONSPD_REQUIRED_FIELDS = {
    "postcode",
    "termination_date",
    "easting",
    "northing",
    "country_code",
}

ONSPD_OPTIONAL_FIELDS = {
    "introduction_date",
    "latitude",
    "longitude",
}

ONSPD_FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "postcode": (
        re.compile(r"^pcds$"),
        re.compile(r"^postcode$"),
        re.compile(r"^pcd8$"),
        re.compile(r"^pcd$"),
        re.compile(r"^pcd7$"),
    ),
    "termination_date": (
        re.compile(r"^doterm$"),
        re.compile(r"^terminationdate$"),
        re.compile(r"^dateoftermination$"),
    ),
    "easting": (
        re.compile(r"^oseast1m$"),
        re.compile(r"^east1m$"),
        re.compile(r"^easting$"),
        re.compile(r"^eastings$"),
    ),
    "northing": (
        re.compile(r"^osnrth1m$"),
        re.compile(r"^north1m$"),
        re.compile(r"^northing$"),
        re.compile(r"^northings$"),
    ),
    "country_code": (
        re.compile(r"^ctry$"),
        re.compile(r"^ctry\d{2}cd$"),
        re.compile(r"^countrycode$"),
        re.compile(r"^country$"),
    ),
    "introduction_date": (
        re.compile(r"^dointr$"),
        re.compile(r"^introductiondate$"),
        re.compile(r"^dateofintroduction$"),
    ),
    "latitude": (
        re.compile(r"^lat$"),
        re.compile(r"^latitude$"),
    ),
    "longitude": (
        re.compile(r"^long$"),
        re.compile(r"^lng$"),
        re.compile(r"^longitude$"),
    ),
}

ONSPD_RELEASE_PATTERN = re.compile(
    r"^ONS Postcode Directory \("
    r"(?P<month>February|May|August|November) "
    r"(?P<year>\d{4})"
    r"\)(?: for the (?:UK|United Kingdom))?(?: \(V\d+\))?$",
    flags=re.IGNORECASE,
)

MONTH_NUMBERS = {
    "february": 2,
    "may": 5,
    "august": 8,
    "november": 11,
}


@dataclass(frozen=True)
class OnspdSource:
    item_id: str
    title: str
    release_date: date
    modified_at: datetime
    item_url: str
    download_url: str


def parse_onspd_release_date(title: str) -> date | None:
    match = ONSPD_RELEASE_PATTERN.fullmatch(title.strip())
    if not match:
        return None
    return date(
        int(match.group("year")),
        MONTH_NUMBERS[match.group("month").casefold()],
        1,
    )


def discover_latest_onspd_source(
    session: requests.Session,
    *,
    item_id_override: str | None = None,
) -> OnspdSource:
    if item_id_override:
        candidate_ids = [item_id_override]
    else:
        candidate_ids: list[str] = []
        queries = (
            'title:"ONS Postcode Directory" AND type:"CSV Collection"',
            'tags:PRD_ONSPD AND type:"CSV Collection"',
            '"ONS Postcode Directory" AND type:"CSV Collection"',
        )
        for query in queries:
            payload = fetch_json(
                session,
                ARCGIS_SEARCH_URL,
                params={
                    "f": "json",
                    "num": 100,
                    "sortField": "modified",
                    "sortOrder": "desc",
                    "q": query,
                },
            )
            for item in payload.get("results", []):
                if isinstance(item, dict) and item.get("id"):
                    item_id = str(item["id"])
                    if item_id not in candidate_ids:
                        candidate_ids.append(item_id)
            if candidate_ids:
                break

    candidates: list[OnspdSource] = []
    for item_id in candidate_ids:
        metadata = fetch_json(
            session,
            ARCGIS_ITEM_URL.format(item_id=item_id),
            params={"f": "json"},
        )
        title = str(metadata.get("title", "")).strip()
        release_date = parse_onspd_release_date(title)
        item_type = str(metadata.get("type", "")).strip().casefold()
        modified_ms = metadata.get("modified")

        valid = (
            release_date is not None
            and item_type == "csv collection"
            and isinstance(modified_ms, (int, float))
        )
        if not valid:
            if item_id_override:
                raise SchoolFinderError(
                    "The supplied ArcGIS item is not a recognised ONSPD "
                    "CSV Collection."
                )
            continue

        candidates.append(
            OnspdSource(
                item_id=item_id,
                title=title,
                release_date=release_date,
                modified_at=datetime.fromtimestamp(
                    modified_ms / 1000,
                    tz=timezone.utc,
                ),
                item_url=ARCGIS_ITEM_URL.format(item_id=item_id),
                download_url=ARCGIS_ITEM_DATA_URL.format(item_id=item_id),
            )
        )

    if not candidates:
        raise SchoolFinderError(
            "Could not discover the latest ONSPD CSV Collection. "
            "Use --onspd-item-id to supply its ArcGIS item ID explicitly."
        )

    return max(candidates, key=lambda item: (item.release_date, item.modified_at))


def download_onspd_zip(
    session: requests.Session,
    source: OnspdSource,
    destination: Path,
) -> None:
    log(f"Downloading {source.title}...")
    stream_download(session, source.download_url, destination, minimum_size=1_000_000)
    if not zipfile.is_zipfile(destination):
        destination.unlink(missing_ok=True)
        raise SchoolFinderError(
            "The ONSPD item did not return a ZIP file. The upstream download "
            "format may have changed."
        )


def normalise_column_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().casefold())


def match_onspd_fields(header: list[str]) -> dict[str, str]:
    normalised = {
        normalise_column_name(column): column
        for column in header
        if column and column.strip()
    }
    matched: dict[str, str] = {}

    for canonical, patterns in ONSPD_FIELD_PATTERNS.items():
        for normalised_name, actual_name in normalised.items():
            if any(pattern.fullmatch(normalised_name) for pattern in patterns):
                matched[canonical] = actual_name
                break

    return matched


def detect_onspd_header(
    archive: zipfile.ZipFile,
    member: str,
) -> tuple[dict[str, str], int]:
    encodings = ("utf-8-sig", "cp1252", "utf-16")

    for encoding in encodings:
        try:
            with archive.open(member) as raw:
                text_stream = io.TextIOWrapper(
                    raw,
                    encoding=encoding,
                    errors="strict",
                    newline="",
                )
                reader = csv.reader(text_stream)
                for row_number, row in enumerate(reader):
                    if row_number >= 10:
                        break
                    fields = match_onspd_fields(row)
                    if ONSPD_REQUIRED_FIELDS.issubset(fields):
                        return fields, row_number
        except (UnicodeDecodeError, UnicodeError):
            continue

    return {}, 0


def select_onspd_members(
    archive: zipfile.ZipFile,
) -> list[tuple[str, dict[str, str], int]]:
    candidates: list[tuple[str, dict[str, str], int]] = []
    inspected: list[str] = []

    for member in archive.namelist():
        if member.endswith("/") or not member.casefold().endswith(".csv"):
            continue

        fields, header_row = detect_onspd_header(archive, member)
        if fields:
            candidates.append((member, fields, header_row))
        elif len(inspected) < 12:
            try:
                with archive.open(member) as raw:
                    sample = raw.read(4096)
                preview = sample.decode("utf-8-sig", errors="replace").splitlines()
                first_line = preview[0][:240] if preview else "<empty>"
            except OSError:
                first_line = "<could not read>"
            inspected.append(f"{member}: {first_line}")

    if not candidates:
        details = "\n".join(f"  - {line}" for line in inspected)
        suffix = f"\nFirst CSV samples:\n{details}" if details else ""
        raise SchoolFinderError(
            "No ONSPD data CSV with recognisable postcode, termination, "
            "coordinate and country columns was found in the ZIP."
            + suffix
        )

    multi = [
        candidate
        for candidate in candidates
        if "multi_csv" in candidate[0].casefold()
        or "multi csv" in candidate[0].casefold()
    ]
    if multi:
        return sorted(multi, key=lambda item: item[0].casefold())

    full_uk = [
        candidate
        for candidate in candidates
        if re.search(r"(?:^|[_\-/])UK(?:[_\-.]|$)", candidate[0], re.IGNORECASE)
    ]
    if full_uk:
        return [
            max(
                full_uk,
                key=lambda item: archive.getinfo(item[0]).file_size,
            )
        ]

    return sorted(candidates, key=lambda item: item[0].casefold())


def read_onspd_member(
    archive: zipfile.ZipFile,
    member: str,
    fields: dict[str, str],
    header_row: int,
    source: OnspdSource,
) -> Iterator[pd.DataFrame]:
    actual_columns = list(dict.fromkeys(fields.values()))
    rename_columns = {
        actual_name: canonical
        for canonical, actual_name in fields.items()
    }

    with archive.open(member) as raw:
        chunks = pd.read_csv(
            raw,
            usecols=actual_columns,
            dtype=str,
            encoding="utf-8-sig",
            encoding_errors="replace",
            skiprows=header_row,
            chunksize=250_000,
            low_memory=False,
        )

        for chunk in chunks:
            chunk = chunk.rename(columns=rename_columns)

            country = (
                chunk["country_code"]
                .fillna("")
                .astype("string")
                .str.strip()
            )
            england = (
                country.str.upper().eq(ENGLAND_COUNTRY_CODE)
                | country.str.casefold().eq("england")
            )

            chunk = chunk[england].copy()
            if chunk.empty:
                continue

            chunk["postcode"] = chunk["postcode"].fillna("").map(format_postcode)
            chunk["postcode_key"] = chunk["postcode"].map(normalise_postcode)
            chunk["easting"] = pd.to_numeric(chunk["easting"], errors="coerce")
            chunk["northing"] = pd.to_numeric(chunk["northing"], errors="coerce")
            chunk["latitude"] = pd.to_numeric(
                chunk["latitude"] if "latitude" in chunk else pd.NA,
                errors="coerce",
            )
            chunk["longitude"] = pd.to_numeric(
                chunk["longitude"] if "longitude" in chunk else pd.NA,
                errors="coerce",
            )
            chunk["introduction_date"] = (
                chunk["introduction_date"]
                .fillna("")
                .astype("string")
                .str.strip()
                if "introduction_date" in chunk
                else ""
            )
            chunk["termination_date"] = (
                chunk["termination_date"]
                .fillna("")
                .astype("string")
                .str.strip()
            )
            chunk["is_current"] = chunk["termination_date"].eq("")

            chunk = chunk.dropna(subset=["easting", "northing"])
            chunk = chunk[
                (chunk["easting"] > 0)
                & (chunk["northing"] > 0)
                & chunk["postcode_key"].ne("")
            ].copy()
            if chunk.empty:
                continue

            chunk["easting"] = chunk["easting"].round().astype("int32")
            chunk["northing"] = chunk["northing"].round().astype("int32")
            chunk["latitude"] = chunk["latitude"].astype("float64")
            chunk["longitude"] = chunk["longitude"].astype("float64")
            chunk["is_current"] = chunk["is_current"].astype("bool")
            chunk["country_code"] = ENGLAND_COUNTRY_CODE
            chunk["source_release"] = pd.Timestamp(source.release_date)

            yield chunk[
                [
                    "postcode",
                    "postcode_key",
                    "easting",
                    "northing",
                    "latitude",
                    "longitude",
                    "country_code",
                    "is_current",
                    "introduction_date",
                    "termination_date",
                    "source_release",
                ]
            ]


def clean_onspd_data(path: Path, source: OnspdSource) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    with zipfile.ZipFile(path) as archive:
        members = select_onspd_members(archive)
        log(f"Reading {len(members)} ONSPD CSV file(s)...")
        for index, (member, fields, header_row) in enumerate(members, start=1):
            log(f"Reading ONSPD CSV {index}/{len(members)}: {member}")
            frames.extend(
                read_onspd_member(
                    archive,
                    member,
                    fields,
                    header_row,
                    source,
                )
            )

    if not frames:
        raise SchoolFinderError("No English postcodes were found in ONSPD.")

    postcodes = pd.concat(frames, ignore_index=True)
    postcodes = postcodes.drop_duplicates(subset=["postcode_key"], keep="last")
    postcodes = postcodes.sort_values("postcode_key", kind="stable").reset_index(
        drop=True
    )

    if len(postcodes) < 1_000_000:
        raise SchoolFinderError(
            f"ONSPD produced only {len(postcodes):,} English postcodes; "
            "refusing to publish a probably incomplete dataset."
        )
    return postcodes
