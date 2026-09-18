"""Admission-arrangement enrichment from official school/admission-authority sources."""

from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urljoin

import requests

from school_finder.errors import SchoolFinderError
from school_finder.models.admissions import AdmissionArrangementSummary, AdmissionEntryPoint
from school_finder.models.school import SchoolResult

HAMPSHIRE_SCHOOL_DETAILS_URL = (
    "https://www.hants.gov.uk/educationandlearning/findaschool/"
    "schooldetails?dfesno={establishment_number}"
)
HAMPSHIRE_SOURCE_NAME = "Hampshire County Council"


def _normalise(value: str | None) -> str:
    return " ".join(str(value or "").strip().casefold().replace("-", " ").split())


def _selective_from_policy(policy: str | None) -> bool | None:
    value = _normalise(policy)
    if value == "non selective":
        return False
    if value == "selective" or value.startswith("selective "):
        return True
    return None


def admission_authority_for_school(school: SchoolResult) -> str | None:
    """Return the legal admission-authority category from the school type."""
    establishment_type = _normalise(school.identity.establishment_type)
    local_authority = school.location.local_authority_name

    if "community" in establishment_type or "voluntary controlled" in establishment_type:
        return local_authority or "Local authority"
    if any(
        token in establishment_type
        for token in (
            "academy",
            "free school",
            "studio school",
            "university technical college",
            "city technology college",
        )
    ):
        return "Academy trust"
    if "voluntary aided" in establishment_type or "foundation" in establishment_type:
        return "Governing body"
    return None


def base_admission_arrangements(school: SchoolResult) -> AdmissionArrangementSummary:
    """Build the nationally available admissions-arrangement context from GIAS."""
    selective = school.admissions.selective
    if selective is None:
        selective = _selective_from_policy(school.admissions.policy)
    return AdmissionArrangementSummary(
        admission_authority=admission_authority_for_school(school),
        selective=selective,
        policy=school.admissions.policy,
    )


class _SchoolPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        self._href = next((value for name, value in attrs if name.casefold() == "href"), None)
        self._link_text = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if not value:
            return
        self.text.append(value)
        if self._href is not None:
            self._link_text.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        label = " ".join(self._link_text).strip()
        if label:
            self.links.append((label, self._href))
        self._href = None
        self._link_text = []


def _parse_entry_points(text: str) -> tuple[AdmissionEntryPoint, ...]:
    found: list[AdmissionEntryPoint] = []
    seen: set[tuple[str, int]] = set()
    pattern = re.compile(
        r"(?P<pan>\d{1,4})\s+Year\s+(?P<year_group>R|\d{1,2})\s+places\s+"
        r"for\s+September\s+(?P<entry_year>20\d{2})",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        year_group = match.group("year_group").upper()
        entry_year = int(match.group("entry_year"))
        key = (year_group, entry_year)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            AdmissionEntryPoint(
                year_group=year_group,
                entry_year=entry_year,
                published_admission_number=int(match.group("pan")),
            )
        )
    return tuple(sorted(found, key=lambda item: (item.entry_year, item.year_group)))


def _main_admission_policy_link(
    links: list[tuple[str, str]],
    base_url: str,
) -> tuple[str | None, str | None]:
    candidates: list[tuple[int, int, str]] = []
    pattern = re.compile(r"^admission policy\s+(20\d{2})\s*[-/]\s*(20\d{2})$", re.IGNORECASE)
    for label, href in links:
        match = pattern.match(" ".join(label.split()))
        if match is None:
            continue
        start_year = int(match.group(1))
        end_year = int(match.group(2))
        candidates.append((start_year, end_year, urljoin(base_url, href)))
    if not candidates:
        return None, None
    start_year, end_year, href = max(candidates)
    return f"{start_year}/{str(end_year)[-2:]}", href


def _parse_hampshire_school_page(
    html: str,
    source_url: str,
    base: AdmissionArrangementSummary,
) -> AdmissionArrangementSummary:
    parser = _SchoolPageParser()
    parser.feed(html)
    page_text = " ".join(parser.text)
    entry_points = _parse_entry_points(page_text)
    arrangements_year, policy_url = _main_admission_policy_link(parser.links, source_url)
    return AdmissionArrangementSummary(
        admission_authority=base.admission_authority,
        selective=base.selective,
        policy=base.policy,
        entry_points=entry_points,
        arrangements_year=arrangements_year,
        source_name=HAMPSHIRE_SOURCE_NAME,
        source_url=policy_url or source_url,
        directory_url=source_url,
    )


def _is_hampshire(school: SchoolResult) -> bool:
    name = _normalise(school.location.local_authority_name)
    code = str(school.location.local_authority_code or "").strip().upper()
    return name == "hampshire" or code in {"850", "E10000014"}


def get_admission_arrangements(
    school: SchoolResult,
    *,
    session: requests.Session | None = None,
) -> AdmissionArrangementSummary:
    """Return admissions arrangements, enriching from supported official local sources."""
    base = base_admission_arrangements(school)
    if not _is_hampshire(school) or not school.identity.establishment_number:
        return base

    source_url = HAMPSHIRE_SCHOOL_DETAILS_URL.format(
        establishment_number=school.identity.establishment_number
    )
    client = session or requests.Session()
    try:
        response = client.get(source_url, timeout=(10, 30))
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SchoolFinderError(
            f"Could not retrieve Hampshire admission arrangements: {exc}"
        ) from exc

    return _parse_hampshire_school_page(response.text, source_url, base)
