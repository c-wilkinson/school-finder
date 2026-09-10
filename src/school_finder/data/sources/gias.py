"""Get Information About Schools (GIAS) source adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re

import pandas as pd
import requests

from school_finder.errors import SchoolFinderError
from school_finder.data.sources.common import stream_download
from school_finder.utils import format_postcode, log, normalise_postcode, utc_now

GIAS_DOWNLOAD_URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/"
    "edubase/downloads/public/edubasealldata{date}.csv"
)
GIAS_LINKS_DOWNLOAD_URL = (
    "https://ea-edubase-api-prod.azurewebsites.net/"
    "edubase/downloads/public/links_edubasealldata{date}.csv"
)

GIAS_LOOKBACK_DAYS = 21

GIAS_REQUIRED_COLUMNS = [
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
GIAS_OPTIONAL_COLUMNS = ["ReligiousEthos (name)"]
GIAS_COLUMNS = GIAS_REQUIRED_COLUMNS + GIAS_OPTIONAL_COLUMNS

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
    "ReligiousEthos (name)": "religious_ethos",
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

NON_FAITH_CHARACTER_VALUES = {
    "does not apply",
    "none",
    "no religious character",
    "not applicable",
}
UNKNOWN_FAITH_CHARACTER_VALUES = {
    "",
    "not recorded",
    "not set",
    "unknown",
}


@dataclass(frozen=True)
class GiasSource:
    source_date: date
    url: str


@dataclass(frozen=True)
class GiasLinksSource:
    source_date: date
    url: str


def _discover_dated_source(
    session: requests.Session,
    *,
    url_template: str,
    today: date | None,
    label: str,
    source_type: type[GiasSource] | type[GiasLinksSource],
) -> GiasSource | GiasLinksSource:
    current_day = today or utc_now().date()

    for days_ago in range(GIAS_LOOKBACK_DAYS):
        source_date = current_day - timedelta(days=days_ago)
        url = url_template.format(date=source_date.strftime("%Y%m%d"))
        log(f"Checking {label} extract dated {source_date.isoformat()}...")

        try:
            response = session.get(url, stream=True, timeout=(15, 60))
        except requests.RequestException as exc:
            raise SchoolFinderError(
                f"Could not contact the GIAS download service: {exc}"
            ) from exc

        status_code = response.status_code
        response.close()
        if status_code == 200:
            return source_type(source_date=source_date, url=url)
        if status_code != 404:
            raise SchoolFinderError(
                f"GIAS returned HTTP {status_code} while checking {url}"
            )

    raise SchoolFinderError(
        f"No {label} extract was found in the last {GIAS_LOOKBACK_DAYS} days."
    )


def discover_latest_gias_source(
    session: requests.Session,
    *,
    today: date | None = None,
) -> GiasSource:
    return _discover_dated_source(
        session,
        url_template=GIAS_DOWNLOAD_URL,
        today=today,
        label="GIAS",
        source_type=GiasSource,
    )


def discover_latest_gias_links_source(
    session: requests.Session,
    *,
    today: date | None = None,
) -> GiasLinksSource:
    return _discover_dated_source(
        session,
        url_template=GIAS_LINKS_DOWNLOAD_URL,
        today=today,
        label="GIAS links",
        source_type=GiasLinksSource,
    )


def download_gias_csv(
    session: requests.Session,
    source: GiasSource,
    destination: Path,
) -> None:
    log(f"Downloading GIAS {source.source_date.isoformat()}...")
    stream_download(session, source.url, destination, minimum_size=100_000)


def download_gias_links_csv(
    session: requests.Session,
    source: GiasLinksSource,
    destination: Path,
) -> None:
    log(f"Downloading GIAS links {source.source_date.isoformat()}...")
    stream_download(session, source.url, destination, minimum_size=10_000)


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
                keep_default_na=False,
            )
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        missing = sorted(set(GIAS_REQUIRED_COLUMNS) - set(frame.columns))
        if missing:
            raise SchoolFinderError(
                "The GIAS schema has changed. Missing columns: "
                + ", ".join(missing)
            )
        return frame

    raise SchoolFinderError(f"Could not decode the GIAS CSV: {last_error}")


def _normalise_column_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())


def _find_link_column(frame: pd.DataFrame, *aliases: str) -> str | None:
    columns = {_normalise_column_name(column): column for column in frame.columns}
    for alias in aliases:
        match = columns.get(_normalise_column_name(alias))
        if match is not None:
            return match
    return None


def read_gias_links_csv(path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            frame = pd.read_csv(
                path,
                dtype=str,
                encoding=encoding,
                low_memory=False,
                keep_default_na=False,
            )
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        required = {
            "urn": _find_link_column(frame, "URN", "EstablishmentURN"),
            "link_urn": _find_link_column(frame, "LinkURN", "LinkedURN"),
            "link_type": _find_link_column(
                frame,
                "LinkType",
                "LinkType (name)",
                "Type of link",
            ),
        }
        missing = [name for name, column in required.items() if column is None]
        if missing:
            raise SchoolFinderError(
                "The GIAS links schema has changed. Missing fields: "
                + ", ".join(missing)
            )
        return frame

    raise SchoolFinderError(f"Could not decode the GIAS links CSV: {last_error}")


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_gias_links_data(
    raw_links: pd.DataFrame,
    raw_establishments: pd.DataFrame,
    source: GiasLinksSource,
) -> pd.DataFrame:
    urn_col = _find_link_column(raw_links, "URN", "EstablishmentURN")
    link_urn_col = _find_link_column(raw_links, "LinkURN", "LinkedURN")
    type_col = _find_link_column(raw_links, "LinkType", "LinkType (name)", "Type of link")
    name_col = _find_link_column(raw_links, "LinkName", "Linked establishment name")
    date_col = _find_link_column(raw_links, "LinkEstablishmentDate", "Date linked")
    if urn_col is None or link_urn_col is None or type_col is None:
        raise SchoolFinderError("GIAS links data is missing URN/link relationship fields.")

    establishment_urn_col = _find_link_column(raw_establishments, "URN")
    establishment_name_col = _find_link_column(raw_establishments, "EstablishmentName")
    names: dict[str, str] = {}
    if establishment_urn_col is not None and establishment_name_col is not None:
        names = {
            _clean_text(urn): _clean_text(name)
            for urn, name in zip(
                raw_establishments[establishment_urn_col],
                raw_establishments[establishment_name_col],
                strict=False,
            )
            if _clean_text(urn)
        }

    records: list[dict[str, object]] = []
    for _, row in raw_links.iterrows():
        urn = _clean_text(row.get(urn_col))
        linked_urn = _clean_text(row.get(link_urn_col))
        link_type = _clean_text(row.get(type_col)).casefold()
        linked_name = _clean_text(row.get(name_col)) if name_col else ""
        linked_date = row.get(date_col) if date_col else None
        if not urn or not linked_urn or urn == linked_urn:
            continue

        if "predecessor" in link_type:
            successor_urn = urn
            predecessor_urn = linked_urn
            predecessor_name = linked_name or names.get(predecessor_urn, "")
        elif "successor" in link_type:
            successor_urn = linked_urn
            predecessor_urn = urn
            predecessor_name = names.get(predecessor_urn, "")
        else:
            continue

        records.append(
            {
                "successor_urn": successor_urn,
                "predecessor_urn": predecessor_urn,
                "predecessor_name": predecessor_name,
                "link_date": linked_date,
                "source_date": pd.Timestamp(source.source_date),
            }
        )

    columns = [
        "successor_urn",
        "predecessor_urn",
        "predecessor_name",
        "link_date",
        "source_date",
    ]
    if not records:
        return pd.DataFrame(columns=columns)

    links = pd.DataFrame.from_records(records, columns=columns)
    links["successor_urn"] = links["successor_urn"].astype("string")
    links["predecessor_urn"] = links["predecessor_urn"].astype("string")
    links["predecessor_name"] = links["predecessor_name"].astype("string")
    links["link_date"] = pd.to_datetime(links["link_date"], errors="coerce", dayfirst=True)
    return (
        links.sort_values(
            ["successor_urn", "link_date", "predecessor_urn"],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates(["successor_urn", "predecessor_urn"], keep="last")
        .reset_index(drop=True)
    )


def _faith_status(religious_character: pd.Series) -> pd.Series:
    lowered = religious_character.fillna("").astype("string").str.strip().str.casefold()
    status = pd.Series("Faith", index=religious_character.index, dtype="string")
    status.loc[lowered.isin(NON_FAITH_CHARACTER_VALUES)] = "Non-faith"
    status.loc[lowered.isin(UNKNOWN_FAITH_CHARACTER_VALUES)] = "Unknown"
    return status


def clean_gias_data(raw: pd.DataFrame, source: GiasSource) -> pd.DataFrame:
    schools = raw.rename(columns=GIAS_RENAME).copy()
    if "religious_ethos" not in schools.columns:
        schools["religious_ethos"] = ""
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

    schools["faith_status"] = _faith_status(schools["religious_character"])
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
        "religious_ethos",
        "faith_status",
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
