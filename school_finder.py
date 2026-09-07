#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
import re
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin

import pandas as pd
import requests

from school_models import SchoolResult, school_result_from_flat_record

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # Keeps --help usable before dependencies are installed.
    pa = None
    pq = None


GIAS_DOWNLOAD_URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/"
    "edubase/downloads/public/edubasealldata{date}.csv"
)
ARCGIS_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
ARCGIS_ITEM_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}"
ARCGIS_ITEM_DATA_URL = (
    "https://www.arcgis.com/sharing/rest/content/items/{item_id}/data"
)

DEFAULT_DATA_DIR = Path("data")
MANIFEST_FILENAME = "manifest.json"
SCHOOLS_FILENAME = "schools.parquet"
POSTCODES_FILENAME = "postcodes.parquet"
MANIFEST_SCHEMA_VERSION = 3
GIAS_LOOKBACK_DAYS = 21
ENGLAND_COUNTRY_CODE = "E92000001"
METRES_PER_MILE = 1609.344
HTTP_CHUNK_SIZE = 1024 * 1024
PARQUET_ROW_GROUP_SIZE = 100_000

OFSTED_MANAGEMENT_URL = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "monthly-management-information-ofsteds-school-inspections-outcomes"
)
OFSTED_INDEPENDENT_URL = (
    "https://www.gov.uk/government/statistical-data-sets/"
    "non-association-independent-schools-inspections-and-outcomes-management-information"
)
EES_KS4_DATASET_ID = "19e39901-a96c-be76-b9c2-6af54ae076d2"
EES_KS4_CSV_URL = (
    "https://api.education.gov.uk/statistics/v1/data-sets/"
    f"{EES_KS4_DATASET_ID}/csv"
)
QUALITY_MISSING_MARKERS = {"", "z", "x", "c", "na", "n/a", "null", "none"}

USER_AGENT = (
    "school-finder-prototype/0.5"
    "(public DfE and ONS data; local dataset builder)"
)

GIAS_COLUMNS = [
    "URN",
    "EstablishmentName",
    "TypeOfEstablishment (name)",
    "EstablishmentTypeGroup (name)",
    "EstablishmentStatus (name)",
    "PhaseOfEducation (name)",
    "StatutoryLowAge",
    "StatutoryHighAge",
    "Gender (name)",
    "ReligiousCharacter (name)",
    "AdmissionsPolicy (name)",
    "Street",
    "Locality",
    "Address3",
    "Town",
    "County (name)",
    "Postcode",
    "SchoolWebsite",
    "TelephoneNum",
    "Easting",
    "Northing",
]

GIAS_RENAME = {
    "URN": "urn",
    "EstablishmentName": "school_name",
    "TypeOfEstablishment (name)": "establishment_type",
    "EstablishmentTypeGroup (name)": "establishment_type_group",
    "EstablishmentStatus (name)": "status",
    "PhaseOfEducation (name)": "phase",
    "StatutoryLowAge": "low_age",
    "StatutoryHighAge": "high_age",
    "Gender (name)": "gender",
    "ReligiousCharacter (name)": "religious_character",
    "AdmissionsPolicy (name)": "admissions_policy",
    "Street": "street",
    "Locality": "locality",
    "Address3": "address_3",
    "Town": "town",
    "County (name)": "county",
    "Postcode": "postcode",
    "SchoolWebsite": "website",
    "TelephoneNum": "telephone",
    "Easting": "easting",
    "Northing": "northing",
}

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

NON_MAINSTREAM_TYPE_TERMS = (
    "special",
    "pupil referral",
    "alternative provision",
    "secure unit",
    "hospital school",
)

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


class SchoolFinderError(RuntimeError):
    """An expected, user-facing failure."""


@dataclass(frozen=True)
class GiasSource:
    source_date: date
    url: str


@dataclass(frozen=True)
class OnspdSource:
    item_id: str
    title: str
    release_date: date
    modified_at: datetime
    item_url: str
    download_url: str




@dataclass(frozen=True)
class CsvSource:
    name: str
    url: str
    release_label: str

@dataclass(frozen=True)
class BuildResult:
    schools_updated: bool
    postcodes_updated: bool
    manifest_updated: bool
    manifest: dict[str, Any]


def log(message: str) -> None:
    print(message, file=sys.stderr)


def require_pyarrow() -> None:
    if pa is None or pq is None:
        raise SchoolFinderError(
            "PyArrow is required. Install dependencies with: "
            "python -m pip install pandas pyarrow requests"
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalise_postcode(postcode: str) -> str:
    return re.sub(r"\s+", "", postcode.strip().upper())


def format_postcode(postcode: str) -> str:
    compact = normalise_postcode(postcode)
    return compact if len(compact) <= 3 else f"{compact[:-3]} {compact[-3:]}"


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = session.get(url, params=params, timeout=(15, 60))
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve {url}: {exc}") from exc
    except requests.JSONDecodeError as exc:
        raise SchoolFinderError(f"Service returned invalid JSON: {url}") from exc

    if not isinstance(payload, dict):
        raise SchoolFinderError(f"Service returned unexpected data: {url}")
    if payload.get("error"):
        raise SchoolFinderError(f"Service error for {url}: {payload['error']}")
    return payload


def stream_download(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    minimum_size: int,
) -> None:
    try:
        with session.get(url, stream=True, timeout=(20, 600)) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=HTTP_CHUNK_SIZE):
                    if chunk:
                        output.write(chunk)
    except requests.RequestException as exc:
        destination.unlink(missing_ok=True)
        raise SchoolFinderError(f"Could not download {url}: {exc}") from exc

    if destination.stat().st_size < minimum_size:
        destination.unlink(missing_ok=True)
        raise SchoolFinderError(f"Downloaded file from {url} was unexpectedly small.")


def discover_latest_gias_source(
    session: requests.Session,
    *,
    today: date | None = None,
) -> GiasSource:
    current_day = today or utc_now().date()

    for days_ago in range(GIAS_LOOKBACK_DAYS):
        source_date = current_day - timedelta(days=days_ago)
        url = GIAS_DOWNLOAD_URL.format(date=source_date.strftime("%Y%m%d"))
        log(f"Checking GIAS extract dated {source_date.isoformat()}...")

        try:
            response = session.get(url, stream=True, timeout=(15, 60))
        except requests.RequestException as exc:
            raise SchoolFinderError(
                f"Could not contact the GIAS download service: {exc}"
            ) from exc

        status_code = response.status_code
        response.close()
        if status_code == 200:
            return GiasSource(source_date=source_date, url=url)
        if status_code != 404:
            raise SchoolFinderError(
                f"GIAS returned HTTP {status_code} while checking {url}"
            )

    raise SchoolFinderError(
        f"No GIAS extract was found in the last {GIAS_LOOKBACK_DAYS} days."
    )


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


def discover_ofsted_csv(
    session: requests.Session,
    page_url: str,
    *,
    required_phrases: tuple[str, ...],
    source_name: str,
) -> CsvSource:
    try:
        response = session.get(page_url, timeout=(15, 60))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve {source_name}: {exc}") from exc

    anchors = re.findall(
        r'<a[^>]+href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
        response.text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for href, raw_label in anchors:
        label = html.unescape(re.sub(r"<[^>]+>", " ", raw_label))
        label = re.sub(r"\s+", " ", label).strip()
        lowered = label.casefold()
        if not all(phrase.casefold() in lowered for phrase in required_phrases):
            continue
        if not href.casefold().endswith(".csv"):
            continue
        return CsvSource(
            name=source_name,
            url=urljoin(page_url, href),
            release_label=label,
        )

    raise SchoolFinderError(f"Could not discover the latest CSV for {source_name}.")


def discover_latest_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_MANAGEMENT_URL,
        required_phrases=("state-funded schools", "latest inspections as at"),
        source_name="Ofsted state-funded school inspections",
    )


def discover_latest_independent_ofsted_source(session: requests.Session) -> CsvSource:
    return discover_ofsted_csv(
        session,
        OFSTED_INDEPENDENT_URL,
        required_phrases=("most recent inspections data as at",),
        source_name="Ofsted non-association independent school inspections",
    )

def discover_ks4_source(session: requests.Session) -> CsvSource:
    try:
        response = session.get(EES_KS4_CSV_URL, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve DfE KS4 performance data: {exc}") from exc
    return CsvSource(
        name="DfE Key stage 4 performance",
        url=EES_KS4_CSV_URL,
        release_label=f"EES dataset {EES_KS4_DATASET_ID} (latest)",
    )


def download_quality_csv(session: requests.Session, source: CsvSource, destination: Path) -> None:
    log(f"Downloading {source.name}...")
    stream_download(session, source.url, destination, minimum_size=10_000)


def _normalised_columns(frame: pd.DataFrame) -> dict[str, str]:
    return {normalise_column_name(str(column)): str(column) for column in frame.columns}


def _column(frame: pd.DataFrame, *names: str) -> str | None:
    columns = _normalised_columns(frame)
    for name in names:
        found = columns.get(normalise_column_name(name))
        if found:
            return found
    return None


def _clean_text_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype("string").str.strip()


def _numeric_quality(series: pd.Series) -> pd.Series:
    cleaned = _clean_text_series(series)
    cleaned = cleaned.mask(cleaned.str.casefold().isin(QUALITY_MISSING_MARKERS))
    return pd.to_numeric(cleaned, errors="coerce")


def read_quality_csv(path: Path, source_name: str) -> pd.DataFrame:
    """Read a public-data CSV whose publisher may use UTF-8 or Windows encodings."""
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(
                path,
                dtype=str,
                encoding=encoding,
                low_memory=False,
            )
        except UnicodeDecodeError as exc:
            last_error = exc

    raise SchoolFinderError(
        f"Could not decode {source_name} CSV using UTF-8, Windows-1252 or Latin-1: "
        f"{last_error}"
    )


def read_ofsted_quality(path: Path) -> pd.DataFrame:
    frame = read_quality_csv(path, "Ofsted")
    urn_col = _column(frame, "URN")
    if urn_col is None:
        raise SchoolFinderError("Ofsted CSV does not contain a URN column.")

    result = pd.DataFrame({"urn": _clean_text_series(frame[urn_col])})
    mappings = {
        "ofsted_rating": ("Overall effectiveness", "Overall effectiveness grade"),
        "ofsted_inspection_date": ("Inspection start date", "Inspection date"),
        "ofsted_publication_date": ("Publication date",),
        "ofsted_safeguarding": ("Safeguarding standards", "Safeguarding is effective?"),
        "ofsted_inclusion": ("Inclusion",),
        "ofsted_curriculum_teaching": ("Curriculum and teaching", "Quality of education"),
        "ofsted_achievement": ("Achievement",),
        "ofsted_attendance_behaviour": ("Attendance and behaviour", "Behaviour and attitudes"),
        "ofsted_personal_development": ("Personal development and wellbeing", "Personal development"),
        "ofsted_leadership": ("Leadership and governance", "Effectiveness of leadership and management"),
    }
    for output, aliases in mappings.items():
        source_col = _column(frame, *aliases)
        result[output] = _clean_text_series(frame[source_col]) if source_col else pd.NA

    for date_col in ("ofsted_inspection_date", "ofsted_publication_date"):
        result[date_col] = pd.to_datetime(result[date_col], errors="coerce", dayfirst=True)

    result = result[result["urn"].ne("")].copy()
    result = result.sort_values(
        ["urn", "ofsted_publication_date", "ofsted_inspection_date"],
        kind="stable",
        na_position="first",
    ).drop_duplicates("urn", keep="last")
    return result.reset_index(drop=True)


def read_ks4_quality(path: Path) -> pd.DataFrame:
    frame = read_quality_csv(path, "DfE KS4")
    urn_col = _column(frame, "school_urn", "URN")
    time_col = _column(frame, "time_period")
    if urn_col is None or time_col is None:
        raise SchoolFinderError("DfE KS4 CSV is missing school_urn or time_period.")

    total = pd.Series(True, index=frame.index)
    for dimension in (
        "breakdown_topic", "breakdown", "sex", "disadvantage_status",
        "first_language", "prior_attainment", "mobility",
    ):
        col = _column(frame, dimension)
        if col is not None:
            total &= _clean_text_series(frame[col]).str.casefold().eq("total")
    headline = frame[total].copy()
    if headline.empty:
        raise SchoolFinderError("DfE KS4 CSV contained no all-pupils headline rows.")

    headline["_time_num"] = pd.to_numeric(headline[time_col], errors="coerce")
    headline = headline.dropna(subset=["_time_num"])
    latest_time = int(headline["_time_num"].max())
    current = headline[headline["_time_num"] == latest_time].copy()

    result = pd.DataFrame({
        "urn": _clean_text_series(current[urn_col]),
        "performance_year": _clean_text_series(current[time_col]),
    })
    metrics = {
        "attainment8": "attainment8_average",
        "english_maths_grade5_pct": "engmath_95_percent",
        "english_maths_grade4_pct": "engmath_94_percent",
        "ebacc_entry_pct": "ebacc_entering_percent",
        "ebacc_aps": "ebacc_aps_average",
    }
    for output, source_name in metrics.items():
        col = _column(current, source_name)
        result[output] = _numeric_quality(current[col]) if col else pd.NA

    progress_col = _column(headline, "progress8_average")
    progress = pd.DataFrame(columns=["urn", "progress8", "progress8_year"])
    if progress_col is not None:
        p8 = headline[[urn_col, time_col, "_time_num", progress_col]].copy()
        p8["progress8"] = _numeric_quality(p8[progress_col])
        p8 = p8.dropna(subset=["progress8"]).sort_values(
            [urn_col, "_time_num"], kind="stable"
        ).drop_duplicates(urn_col, keep="last")
        progress = pd.DataFrame({
            "urn": _clean_text_series(p8[urn_col]),
            "progress8": p8["progress8"].astype("float64"),
            "progress8_year": _clean_text_series(p8[time_col]),
        })

    result = result[result["urn"].ne("")].drop_duplicates("urn", keep="last")
    result = result.merge(progress, on="urn", how="left")
    return result.reset_index(drop=True)


def enrich_school_quality(
    schools: pd.DataFrame,
    ofsted: pd.DataFrame,
    performance: pd.DataFrame,
) -> pd.DataFrame:
    enriched = schools.merge(ofsted, on="urn", how="left", validate="one_to_one")
    enriched = enriched.merge(performance, on="urn", how="left", validate="one_to_one")
    return enriched


def download_gias_csv(
    session: requests.Session,
    source: GiasSource,
    destination: Path,
) -> None:
    log(f"Downloading GIAS {source.source_date.isoformat()}...")
    stream_download(session, source.url, destination, minimum_size=100_000)


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


def read_gias_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            frame = pd.read_csv(
                path,
                usecols=lambda column: column in GIAS_COLUMNS,
                dtype=str,
                encoding=encoding,
                low_memory=False,
            )
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        missing = sorted(set(GIAS_COLUMNS) - set(frame.columns))
        if missing:
            raise SchoolFinderError(
                "The GIAS schema has changed. Missing columns: "
                + ", ".join(missing)
            )
        return frame

    raise SchoolFinderError(f"Could not decode the GIAS CSV: {last_error}")


def clean_gias_data(raw: pd.DataFrame, source: GiasSource) -> pd.DataFrame:
    schools = raw.rename(columns=GIAS_RENAME).copy()
    numeric_columns = {"low_age", "high_age", "easting", "northing"}

    for column in schools.columns:
        if column in numeric_columns:
            schools[column] = pd.to_numeric(schools[column], errors="coerce")
        else:
            schools[column] = (
                schools[column].fillna("").astype("string").str.strip()
            )

    schools = schools[
        schools["status"].str.casefold().str.startswith("open", na=False)
    ].copy()
    schools = schools.dropna(subset=["easting", "northing"])
    schools = schools[(schools["easting"] > 0) & (schools["northing"] > 0)].copy()

    group_name = schools["establishment_type_group"].str.casefold()
    type_name = schools["establishment_type"].str.casefold()
    schools["sector"] = "State-funded"
    schools.loc[
        group_name.str.contains("independent", na=False)
        | type_name.str.contains("independent", na=False),
        "sector",
    ] = "Independent"

    schools["postcode"] = schools["postcode"].map(format_postcode)
    schools["postcode_key"] = schools["postcode"].map(normalise_postcode)
    schools["source_date"] = pd.Timestamp(source.source_date)
    schools["urn"] = schools["urn"].astype("string")
    schools["low_age"] = schools["low_age"].round().astype("Int64")
    schools["high_age"] = schools["high_age"].round().astype("Int64")
    schools["easting"] = schools["easting"].round().astype("int32")
    schools["northing"] = schools["northing"].round().astype("int32")

    columns = [
        "urn",
        "school_name",
        "sector",
        "establishment_type",
        "establishment_type_group",
        "status",
        "phase",
        "low_age",
        "high_age",
        "gender",
        "religious_character",
        "admissions_policy",
        "street",
        "locality",
        "address_3",
        "town",
        "county",
        "postcode",
        "postcode_key",
        "website",
        "telephone",
        "easting",
        "northing",
        "source_date",
    ]
    schools = schools[columns].drop_duplicates(subset=["urn"], keep="last")
    return schools.sort_values("urn", kind="stable").reset_index(drop=True)


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


def read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_json_atomic(payload: dict[str, Any], destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def gias_manifest(source: GiasSource) -> dict[str, Any]:
    return {
        "name": "Get Information About Schools",
        "source_date": source.source_date.isoformat(),
        "download_url": source.url,
    }


def csv_source_manifest(source: CsvSource) -> dict[str, Any]:
    return {
        "name": source.name,
        "release_label": source.release_label,
        "download_url": source.url,
    }


def onspd_manifest(source: OnspdSource) -> dict[str, Any]:
    return {
        "name": "ONS Postcode Directory",
        "title": source.title,
        "release_date": source.release_date.isoformat(),
        "modified_at": iso_utc(source.modified_at),
        "arcgis_item_id": source.item_id,
        "item_url": source.item_url,
        "download_url": source.download_url,
        "coverage": "Current and terminated postcodes in England",
    }


def source_matches(
    manifest: dict[str, Any] | None,
    source_name: str,
    expected: dict[str, Any],
    keys: tuple[str, ...],
) -> bool:
    if manifest is None:
        return False
    actual = manifest.get("sources", {}).get(source_name, {})
    return all(actual.get(key) == expected.get(key) for key in keys)


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
            download_quality_csv(session, ofsted_source, ofsted_csv)
            download_quality_csv(session, independent_ofsted_source, independent_ofsted_csv)
            download_quality_csv(session, ks4_source, ks4_csv)
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


def is_mainstream(establishment_type: pd.Series) -> pd.Series:
    lowered = establishment_type.fillna("").str.casefold()
    mask = pd.Series(True, index=establishment_type.index)
    for term in NON_MAINSTREAM_TYPE_TERMS:
        mask &= ~lowered.str.contains(term, regex=False)
    return mask


def build_address(row: pd.Series) -> str:
    parts = [
        row.get("street", ""),
        row.get("locality", ""),
        row.get("address_3", ""),
        row.get("town", ""),
        row.get("county", ""),
        row.get("postcode", ""),
    ]
    return ", ".join(
        str(part).strip()
        for part in parts
        if pd.notna(part) and str(part).strip()
    )


def lookup_postcode(path: Path, postcode: str) -> pd.Series:
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
        available_columns = set(pq.ParquetFile(path).schema_arrow.names)
        missing = sorted(set(required_columns) - available_columns)
        if missing:
            raise SchoolFinderError(
                f"{path} uses an older postcode schema. "
                "Run 'python school_finder.py build' to rebuild it. "
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
    return matches.iloc[0]


def find_nearest_schools(
    schools_path: Path,
    postcode: pd.Series,
    *,
    limit: int,
    entry_age: int,
    minimum_exit_age: int,
    include_special: bool,
) -> pd.DataFrame:
    require_pyarrow()
    try:
        schools = pd.read_parquet(schools_path, engine="pyarrow")
    except Exception as exc:
        raise SchoolFinderError(f"Could not read {schools_path}: {exc}") from exc

    eligible = schools[
        schools["low_age"].notna()
        & schools["high_age"].notna()
        & (schools["low_age"] <= entry_age)
        & (schools["high_age"] >= minimum_exit_age)
    ].copy()
    if not include_special:
        eligible = eligible[is_mainstream(eligible["establishment_type"])].copy()

    delta_easting = eligible["easting"] - float(postcode["easting"])
    delta_northing = eligible["northing"] - float(postcode["northing"])
    eligible["distance_metres"] = (
        delta_easting.pow(2) + delta_northing.pow(2)
    ).pow(0.5)
    eligible["distance_miles"] = (
        eligible["distance_metres"] / METRES_PER_MILE
    ).round(2)

    nearest = eligible.nsmallest(limit, "distance_metres").copy()
    nearest["address"] = nearest.apply(build_address, axis=1)
    nearest["age_range"] = (
        nearest["low_age"].astype("Int64").astype("string")
        + "–"
        + nearest["high_age"].astype("Int64").astype("string")
    )
    return nearest[
        [
            "school_name",
            "distance_miles",
            "sector",
            "establishment_type",
            "phase",
            "age_range",
            "gender",
            "religious_character",
            "admissions_policy",
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
            "performance_year",
            "attainment8",
            "english_maths_grade5_pct",
            "english_maths_grade4_pct",
            "ebacc_entry_pct",
            "ebacc_aps",
            "progress8",
            "progress8_year",
            "address",
            "town",
            "postcode",
            "easting",
            "northing",
            "urn",
            "website",
            "telephone",
            "source_date",
        ]
    ].reset_index(drop=True)


def serialisable_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = frame.copy()
    for column in records.columns:
        if pd.api.types.is_datetime64_any_dtype(records[column]):
            records[column] = records[column].dt.strftime("%Y-%m-%d")
    records = records.astype(object).where(pd.notna(records), None)
    return records.to_dict(orient="records")


def school_results_from_frame(frame: pd.DataFrame) -> list[SchoolResult]:
    """Convert flat lookup rows into the application-facing data contract."""
    return [
        school_result_from_flat_record(record)
        for record in serialisable_records(frame)
    ]


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
    lookup.add_argument("--include-special", action="store_true")
    output = lookup.add_mutually_exclusive_group()
    output.add_argument(
        "--json",
        action="store_true",
        help="Print the existing flat lookup rows as JSON.",
    )
    output.add_argument(
        "--structured-json",
        action="store_true",
        help="Print nested SchoolResult objects used by the application layer.",
    )
    return parser


def main() -> int:
    args = create_parser().parse_args()
    try:
        if args.command == "build":
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

        if args.limit < 1:
            raise SchoolFinderError("--limit must be at least 1.")

        postcodes_path = args.data_dir / POSTCODES_FILENAME
        schools_path = args.data_dir / SCHOOLS_FILENAME
        if not postcodes_path.exists() or not schools_path.exists():
            raise SchoolFinderError(
                f"Datasets are missing from {args.data_dir}. Run build first."
            )

        postcode = lookup_postcode(postcodes_path, args.postcode)
        if not bool(postcode["is_current"]):
            ended = str(postcode.get("termination_date", "")).strip()
            detail = f" in {ended}" if ended else ""
            log(
                f"Warning: {postcode['postcode']} is marked as terminated"
                f"{detail}; using its last known ONSPD coordinates."
            )

        results = find_nearest_schools(
            schools_path,
            postcode,
            limit=args.limit,
            entry_age=args.entry_age,
            minimum_exit_age=args.minimum_exit_age,
            include_special=args.include_special,
        )

        if args.structured_json:
            payload = [result.to_dict() for result in school_results_from_frame(results)]
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.json:
            print(json.dumps(serialisable_records(results), indent=2, ensure_ascii=False))
        else:
            print(
                f"Nearest {len(results)} schools to {postcode['postcode']} "
                "(straight-line distance):\n"
            )
            display = results[
                [
                    "school_name",
                    "distance_miles",
                    "sector",
                    "establishment_type",
                    "age_range",
                    "ofsted_rating",
                    "ofsted_inspection_date",
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

    except (SchoolFinderError, OSError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
