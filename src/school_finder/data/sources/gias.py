"""Get Information About Schools (GIAS) source adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from school_finder.errors import SchoolFinderError
from school_finder.data.sources.common import stream_download
from school_finder.utils import format_postcode, log, normalise_postcode, utc_now

GIAS_DOWNLOAD_URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/"
    "edubase/downloads/public/edubasealldata{date}.csv"
)

GIAS_LOOKBACK_DAYS = 21

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


@dataclass(frozen=True)
class GiasSource:
    source_date: date
    url: str


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


def download_gias_csv(
    session: requests.Session,
    source: GiasSource,
    destination: Path,
) -> None:
    log(f"Downloading GIAS {source.source_date.isoformat()}...")
    stream_download(session, source.url, destination, minimum_size=100_000)


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
