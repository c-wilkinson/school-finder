"""Admission-arrangement enrichment from official school/admission-authority sources."""

from __future__ import annotations

from html.parser import HTMLParser
from io import BytesIO
import re
from urllib.parse import urljoin, urlparse

from pypdf import PdfReader
from pypdf.errors import PdfReadError
import requests

from school_finder.errors import SchoolFinderError
from school_finder.models.admissions import (
    AdmissionArrangementSummary,
    AdmissionCriterion,
    AdmissionCriterionKind,
    AdmissionEntryPoint,
)
from school_finder.models.school import SchoolResult

HAMPSHIRE_SCHOOL_DETAILS_URL = (
    "https://www.hants.gov.uk/educationandlearning/findaschool/"
    "schooldetails?dfesno={establishment_number}"
)
HAMPSHIRE_SOURCE_NAME = "Hampshire County Council"
HAMPSHIRE_POLICY_URL = (
    "https://documents.hants.gov.uk/education/admissions/schoolpolicies/"
    "{entry_year}/{establishment_number}{entry_year}.pdf"
)
_REQUEST_HEADERS = {
    "User-Agent": "SchoolFinder/0.1 (+https://github.com/c-wilkinson/school-finder)",
    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
}


def _request(client: requests.Session, url: str) -> requests.Response:
    """Fetch an official admissions source using a normal application user agent."""
    return client.get(url, timeout=(10, 30), headers=_REQUEST_HEADERS)


def _entry_year_from_admissions_data(school: SchoolResult) -> int | None:
    """Return the September entry year represented by the latest admissions data."""
    value = str(school.admissions.data_year or "").strip()
    match = re.fullmatch(r"(?P<start>20\d{2})\s*/\s*(?P<end>\d{2}|20\d{2})", value)
    if match is None:
        return None
    end = match.group("end")
    if len(end) == 4:
        return int(end)
    return (int(match.group("start")) // 100) * 100 + int(end)


def _parse_policy_pan(text: str, entry_year: int) -> tuple[AdmissionEntryPoint, ...]:
    """Extract PANs from published policy text when the directory page is unavailable."""
    flattened = " ".join(str(text or "").replace("\x00", " ").split())
    pattern = re.compile(
        r"\bPAN\b.*?\bis\s+(?P<pan>\d{1,4})\s+in\s+Year\s+(?P<year_group>R|\d{1,2})\b",
        re.IGNORECASE,
    )
    found: list[AdmissionEntryPoint] = []
    seen: set[str] = set()
    for match in pattern.finditer(flattened):
        year_group = match.group("year_group").upper()
        if year_group in seen:
            continue
        seen.add(year_group)
        found.append(
            AdmissionEntryPoint(
                year_group=year_group,
                entry_year=entry_year,
                published_admission_number=int(match.group("pan")),
            )
        )
    return tuple(found)


def _arrangements_from_policy(
    text: str,
    *,
    base: AdmissionArrangementSummary,
    source_url: str,
    directory_url: str,
    entry_year: int,
) -> AdmissionArrangementSummary:
    """Build a Hampshire arrangement summary directly from the official policy."""
    return AdmissionArrangementSummary(
        admission_authority=base.admission_authority,
        selective=base.selective,
        policy=base.policy,
        entry_points=_parse_policy_pan(text, entry_year),
        arrangements_year=f"{entry_year}/{str(entry_year + 1)[-2:]}",
        criteria=_parse_oversubscription_criteria(text),
        source_name=HAMPSHIRE_SOURCE_NAME,
        source_url=source_url,
        directory_url=directory_url,
    )


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


def _criterion_kinds(description: str) -> tuple[AdmissionCriterionKind, ...]:
    """Classify one published criterion without discarding its original wording."""
    value = _normalise(description)
    found: list[AdmissionCriterionKind] = []

    checks: tuple[tuple[AdmissionCriterionKind, bool], ...] = (
        (AdmissionCriterionKind.LOOKED_AFTER, "looked after" in value),
        (AdmissionCriterionKind.SIBLING, "sibling" in value),
        (AdmissionCriterionKind.CATCHMENT, "catchment" in value),
        (
            AdmissionCriterionKind.DISTANCE,
            "distance" in value or "nearest" in value or "nearer" in value,
        ),
        (
            AdmissionCriterionKind.FEEDER,
            "feeder" in value
            or "linked school" in value
            or "linked junior" in value
            or "linked primary" in value,
        ),
        (
            AdmissionCriterionKind.FAITH,
            any(
                token in value
                for token in ("faith", "catholic", "church of england", "religious", "parish")
            ),
        ),
        (
            AdmissionCriterionKind.SELECTIVE,
            any(
                token in value
                for token in ("selective", "grammar", "aptitude", "ability test", "11+")
            ),
        ),
        (AdmissionCriterionKind.PUPIL_PREMIUM, "pupil premium" in value),
        (
            AdmissionCriterionKind.SERVICE_PREMIUM,
            "service premium" in value or "service child" in value,
        ),
        (
            AdmissionCriterionKind.STAFF_CHILD,
            "children of staff" in value or "child of staff" in value,
        ),
        (
            AdmissionCriterionKind.SOCIAL_MEDICAL,
            "medical" in value or "social need" in value,
        ),
    )
    for kind, matches in checks:
        if matches:
            found.append(kind)
    return tuple(found) or (AdmissionCriterionKind.OTHER,)


def _parse_oversubscription_criteria(text: str) -> tuple[AdmissionCriterion, ...]:
    """Extract numbered oversubscription criteria from a published policy's text."""
    flattened = " ".join(str(text or "").replace("\x00", " ").split())
    start = re.search(r"oversubscription\s+criteria", flattened, flags=re.IGNORECASE)
    if start is None:
        return ()

    section = flattened[start.end() :]
    end = re.search(
        r"\b(?:definitions|distance\s+measurement|tie[- ]?breaker|additional\s+information|"
        r"waiting\s+lists?|appeals?|admission\s+of\s+children\s+outside)\b",
        section,
        flags=re.IGNORECASE,
    )
    if end is not None:
        section = section[: end.start()]

    marker = re.compile(r"(?<!\S)(?P<priority>\d{1,2})\s*[.)]\s*")
    matches = list(marker.finditer(section))
    criteria: list[AdmissionCriterion] = []
    for index, match in enumerate(matches):
        end_index = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        description = section[match.end() : end_index].strip(" -;:")
        if not description:
            continue
        criteria.append(
            AdmissionCriterion(
                priority=int(match.group("priority")),
                kinds=_criterion_kinds(description),
                description=description,
            )
        )
    return tuple(criteria)


def _extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _policy_response_text(response: requests.Response, source_url: str) -> str:
    content_type = str(response.headers.get("Content-Type", "")).casefold()
    is_pdf = "application/pdf" in content_type or urlparse(source_url).path.casefold().endswith(".pdf")
    if is_pdf:
        return _extract_pdf_text(response.content)

    parser = _SchoolPageParser()
    parser.feed(response.text)
    return " ".join(parser.text)


def _load_published_criteria(
    client: requests.Session,
    source_url: str,
) -> tuple[AdmissionCriterion, ...]:
    response = _request(client, source_url)
    response.raise_for_status()
    return _parse_oversubscription_criteria(_policy_response_text(response, source_url))


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
    page_error: requests.RequestException | None = None
    try:
        response = _request(client, source_url)
        response.raise_for_status()
    except requests.RequestException as exc:
        page_error = exc
    else:
        arrangements = _parse_hampshire_school_page(response.text, source_url, base)
        if not arrangements.source_url or arrangements.source_url == source_url:
            return arrangements

        try:
            criteria = _load_published_criteria(client, arrangements.source_url)
        except (requests.RequestException, PdfReadError, OSError, ValueError):
            return arrangements

        return AdmissionArrangementSummary(
            admission_authority=arrangements.admission_authority,
            selective=arrangements.selective,
            policy=arrangements.policy,
            entry_points=arrangements.entry_points,
            arrangements_year=arrangements.arrangements_year,
            criteria=criteria,
            source_name=arrangements.source_name,
            source_url=arrangements.source_url,
            directory_url=arrangements.directory_url,
        )

    entry_year = _entry_year_from_admissions_data(school)
    if entry_year is not None:
        policy_url = HAMPSHIRE_POLICY_URL.format(
            entry_year=entry_year,
            establishment_number=school.identity.establishment_number,
        )
        try:
            response = _request(client, policy_url)
            response.raise_for_status()
            policy_text = _policy_response_text(response, policy_url)
        except (requests.RequestException, PdfReadError, OSError, ValueError):
            pass
        else:
            return _arrangements_from_policy(
                policy_text,
                base=base,
                source_url=policy_url,
                directory_url=source_url,
                entry_year=entry_year,
            )

    raise SchoolFinderError(
        f"Could not retrieve Hampshire admission arrangements: {page_error}"
    ) from page_error

