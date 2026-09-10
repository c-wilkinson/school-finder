"""Ofsted Parent View pastoral-care source adapters."""

from __future__ import annotations

from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Iterable
from urllib.parse import urljoin
from zipfile import BadZipFile

import pandas as pd
import requests

from school_finder.data.sources.common import (
    CsvSource,
    clean_text_series,
    create_session,
    normalise_column_name,
)
from school_finder.errors import SchoolFinderError

PARENT_VIEW_SOURCE_NAME = "Ofsted Parent View management information"
PARENT_VIEW_LIVE_SOURCE_NAME = "Ofsted Parent View live results"
PARENT_VIEW_RELEASE_DATE = date(2026, 4, 6)
PARENT_VIEW_ODS_URL = (
    "https://assets.publishing.service.gov.uk/media/"
    "6a2a8c0415f2a70fac7e5d74/"
    "Parent_View_Management_Information_as_at_6_April_2026.ods"
)
PARENT_VIEW_RELEASE_LABEL = "Parent View management information as at 6 April 2026"
PARENT_VIEW_URN_URL = "https://parentview.ofsted.gov.uk/parent-view-results/urn/{urn}"
PARENT_VIEW_MIN_SUBMISSIONS = 10
PARENT_VIEW_MIN_SCORE_COVERAGE = 50.0
PARENT_VIEW_LIVE_REFRESH_LIMIT = 100
PARENT_VIEW_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
_SURVEY_RESULT_RE = re.compile(
    r"/parent-view-results/survey/result(?:-print)?/(?P<school_id>\d+)/(?P<tab>\d+|current)",
    flags=re.IGNORECASE,
)
_SURVEY_TAB_PROBE_BACK = 8
_SURVEY_TAB_PROBE_FORWARD = 2

# These weights intentionally emphasise the questions most directly related to
# pupils feeling safe, supported and cared for. Recommendation is shown but is
# not part of the pastoral score because it is a broader judgement of a school.
PASTORAL_COMPONENT_WEIGHTS: dict[str, float] = {
    "happy_pct": 15.0,
    "safe_pct": 20.0,
    "behaviour_positive_pct": 5.0,
    "bullying_dealt_with_pct": 15.0,
    "send_support_pct": 10.0,
    "communication_pct": 5.0,
    "concerns_dealt_with_pct": 5.0,
    "best_interests_pct": 15.0,
    "learning_support_pct": 10.0,
}

QUESTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "happy_pct": ("child is happy", "children are happy"),
    "safe_pct": ("child feels safe", "children feel safe"),
    "behaviour_positive_pct": ("pupils are well behaved",),
    "bullying_dealt_with_pct": (
        "bullying took place the school dealt with it quickly and effectively",
        "dealt with the bullying quickly and effectively",
        "school dealt with the bullying quickly and effectively",
    ),
    "send_support_pct": (
        "support they need to succeed",
        "school gives them the support they need to succeed",
    ),
    "communication_pct": (
        "communicates well with me",
        "lets me know how my child is doing",
    ),
    "concerns_dealt_with_pct": ("raised concerns", "dealt with properly"),
    "best_interests_pct": ("best interests at heart",),
    "learning_support_pct": ("right support to enable them to learn well",),
    "recommend_pct": ("recommend this school",),
    "personal_development_pct": ("supports my child s wider personal development",),
}

PASTORAL_OUTPUT_COLUMNS = [
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
]


def discover_parent_view_source(session: requests.Session) -> CsvSource:
    """Return the latest supported bulk Parent View release."""
    try:
        response = session.get(PARENT_VIEW_ODS_URL, stream=True, timeout=(15, 60))
        response.raise_for_status()
        response.close()
    except requests.RequestException as exc:
        raise SchoolFinderError(f"Could not retrieve Ofsted Parent View data: {exc}") from exc
    return CsvSource(
        name=PARENT_VIEW_SOURCE_NAME,
        url=PARENT_VIEW_ODS_URL,
        release_label=PARENT_VIEW_RELEASE_LABEL,
    )


def _cell_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _normalised_text(value: object) -> str:
    return normalise_column_name(_cell_text(value))


def _find_header_row(raw: pd.DataFrame) -> int | None:
    for index in range(min(len(raw), 120)):
        values = [_normalised_text(value) for value in raw.iloc[index].tolist()]
        if "urn" in values and any(value in {"submissions", "responsesforyear"} for value in values):
            return index
    return None


def _flatten_headers(raw: pd.DataFrame, header_row: int) -> list[str]:
    current = [_cell_text(value) for value in raw.iloc[header_row].tolist()]
    previous = (
        [_cell_text(value) for value in raw.iloc[header_row - 1].tolist()]
        if header_row > 0
        else [""] * len(current)
    )

    # ODS exports sometimes use merged cells for a question followed by a row of
    # response labels. Carry the question text across those response columns.
    question = ""
    previous_filled: list[str] = []
    for value in previous:
        if value:
            question = value
        previous_filled.append(question)

    headers: list[str] = []
    for prev, value in zip(previous_filled, current, strict=True):
        normalised = _normalised_text(value)
        if normalised in {
            "stronglyagree",
            "agree",
            "neitheragreenordisagree",
            "disagree",
            "stronglydisagree",
            "dontknow",
            "yes",
            "no",
            "ihavenotraisedanyconcerns",
            "mychildhasnotbeenbullied",
        } and prev:
            headers.append(f"{prev} {value}".strip())
        else:
            headers.append(value or prev)
    return headers


def _school_level_frame(path: Path) -> pd.DataFrame:
    """Return every school-level table in a Parent View workbook."""
    try:
        workbook = pd.ExcelFile(path, engine="odf")
    except (ImportError, ValueError, OSError, BadZipFile) as exc:
        raise SchoolFinderError(f"Could not read Ofsted Parent View spreadsheet: {exc}") from exc

    frames: list[pd.DataFrame] = []
    for sheet in workbook.sheet_names:
        try:
            raw = pd.read_excel(workbook, sheet_name=sheet, header=None, dtype=object)
        except (ValueError, OSError) as exc:
            raise SchoolFinderError(f"Could not read Ofsted Parent View sheet '{sheet}': {exc}") from exc
        header_row = _find_header_row(raw)
        if header_row is None:
            continue
        headers = _flatten_headers(raw, header_row)
        frame = raw.iloc[header_row + 1 :].copy()
        frame.columns = headers
        frame = frame.dropna(how="all")
        if not frame.empty:
            frames.append(frame.reset_index(drop=True))

    if not frames:
        raise SchoolFinderError(
            "Ofsted Parent View spreadsheet did not contain a school-level table with URN and submissions."
        )

    # Current releases can contain more than one school-level table. Joining
    # them here avoids silently returning only the first table/school type.
    return pd.concat(frames, ignore_index=True, sort=False)


def _find_identity_column(frame: pd.DataFrame, *names: str) -> str | None:
    wanted = {normalise_column_name(name) for name in names}
    for column in frame.columns:
        if normalise_column_name(str(column)) in wanted:
            return str(column)
    return None


def _parse_percentage(series: pd.Series) -> pd.Series:
    text = series.astype("string").fillna("").str.strip()
    had_percent = text.str.endswith("%")
    numeric = pd.to_numeric(text.str.rstrip("%").str.replace(",", "", regex=False), errors="coerce")
    fractional = numeric.notna() & ~had_percent & numeric.between(0, 1, inclusive="both")
    numeric.loc[fractional] = numeric.loc[fractional] * 100.0
    return numeric.astype("Float64")


def _question_columns(frame: pd.DataFrame, patterns: Iterable[str]) -> list[str]:
    normalised_patterns = [normalise_column_name(pattern) for pattern in patterns]
    matches: list[str] = []
    for column in frame.columns:
        normalised = normalise_column_name(str(column))
        if all(pattern in normalised for pattern in normalised_patterns):
            matches.append(str(column))
    if matches:
        return matches

    # Some questions have multiple alternative phrasings. Fall back to matching
    # any single pattern when no column contains every supplied phrase.
    for column in frame.columns:
        normalised = normalise_column_name(str(column))
        if any(pattern in normalised for pattern in normalised_patterns):
            matches.append(str(column))
    return matches


def _positive_percentage(frame: pd.DataFrame, patterns: Iterable[str], *, yes_no: bool = False) -> pd.Series:
    columns = _question_columns(frame, patterns)
    result = pd.Series(pd.NA, index=frame.index, dtype="Float64")
    if not columns:
        return result

    positive_columns: list[str] = []
    for column in columns:
        normalised = normalise_column_name(column)
        if yes_no:
            if normalised.endswith("yes") or "recommendthisschoolyes" in normalised:
                positive_columns.append(column)
        elif normalised.endswith("stronglyagree") or (
            normalised.endswith("agree") and not normalised.endswith("disagree")
        ):
            positive_columns.append(column)

    # Some exports contain one already-aggregated positive percentage column.
    if not positive_columns and len(columns) == 1:
        positive_columns = columns
    if not positive_columns:
        return result

    values = [_parse_percentage(frame[column]) for column in positive_columns]
    combined = pd.concat(values, axis=1).sum(axis=1, min_count=1)
    return combined.clip(lower=0, upper=100).astype("Float64")


def derive_pastoral_score(frame: pd.DataFrame) -> pd.DataFrame:
    """Add the School Finder pastoral score and evidence coverage."""
    result = frame.copy()
    weighted = pd.Series(0.0, index=result.index, dtype="Float64")
    coverage = pd.Series(0.0, index=result.index, dtype="Float64")
    for column, weight in PASTORAL_COMPONENT_WEIGHTS.items():
        values = pd.to_numeric(result[column], errors="coerce").astype("Float64")
        available = values.notna()
        weighted += values.fillna(0.0) * weight
        coverage += available.astype(float) * weight

    score = pd.Series(pd.NA, index=result.index, dtype="Float64")
    enough = coverage.ge(PARENT_VIEW_MIN_SCORE_COVERAGE)
    score.loc[enough] = weighted.loc[enough] / coverage.loc[enough]
    result["pastoral_score"] = score.round(2)
    result["pastoral_score_coverage_pct"] = coverage.round(2)
    return result


def read_parent_view_school(path: Path) -> pd.DataFrame:
    """Return Parent View indicators from the latest bulk management release."""
    frame = _school_level_frame(path)
    urn_col = _find_identity_column(frame, "URN")
    submissions_col = _find_identity_column(frame, "Submissions", "Responses for year")
    if urn_col is None or submissions_col is None:
        raise SchoolFinderError("Ofsted Parent View school table is missing URN or submissions.")

    result = pd.DataFrame(
        {
            "urn": frame[urn_col].astype("string").fillna("").str.strip(),
            "pastoral_response_count": pd.to_numeric(
                frame[submissions_col].astype("string").fillna("").str.strip().str.replace(",", "", regex=False),
                errors="coerce",
            ).astype("Int64"),
        }
    )
    for output, patterns in QUESTION_PATTERNS.items():
        result[output] = _positive_percentage(
            frame,
            patterns,
            yes_no=output == "recommend_pct",
        )

    result = derive_pastoral_score(result)
    result["parent_view_as_at_date"] = pd.Timestamp(PARENT_VIEW_RELEASE_DATE)
    result["parent_view_survey_year"] = "2025/26"
    result["parent_view_questionnaire_version"] = "2025-11"
    result["pastoral_source"] = PARENT_VIEW_SOURCE_NAME
    result["pastoral_source_url"] = PARENT_VIEW_ODS_URL

    enough_submissions = result["pastoral_response_count"].fillna(0).ge(PARENT_VIEW_MIN_SUBMISSIONS)
    result.loc[~enough_submissions, "pastoral_score"] = pd.NA
    return (
        result[result["urn"].ne("")]
        .sort_values(
            ["urn", "pastoral_response_count"],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates("urn", keep="last")
        .reset_index(drop=True)
    )


class _ParentViewHtmlParser(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "br",
        "dd",
        "div",
        "dt",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            label = " ".join(part.strip() for part in self._link_text if part.strip()).strip()
            self.links.append((self._href, label))
            self._href = None
            self._link_text = []
        if tag in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)
        self._chunks.append(" ")
        if self._href is not None:
            self._link_text.append(data)

    def lines(self) -> list[str]:
        text = "".join(self._chunks).replace("\xa0", " ")
        return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _value_after_label(lines: list[str], label: str) -> str | None:
    wanted = label.casefold()
    for index, line in enumerate(lines):
        lower = line.casefold()
        if lower.startswith(wanted):
            same_line = line[len(label) :].lstrip(" :")
            if same_line:
                return same_line
            if index + 1 < len(lines):
                return lines[index + 1]
    return None


def _question_segments(lines: list[str]) -> list[str]:
    starts = [
        index
        for index, line in enumerate(lines)
        if re.search(r"(?:^|\s)\d{1,2}\.\s+", line)
    ]
    segments: list[str] = []
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        segments.append(" ".join(lines[start:end]))
    return segments


def _percentage_from_segment(segment: str, label: str) -> float | None:
    prefix = r"(?<!Strongly )(?<!Dis)" if label.casefold() == "agree" else r"(?<![A-Za-z])"
    pattern = re.compile(
        rf"(?i){prefix}{re.escape(label)}\s*:?[\s]*([0-9]+(?:\.[0-9]+)?)\s*%"
    )
    match = pattern.search(segment)
    return float(match.group(1)) if match else None


def _positive_from_segment(segment: str, *, yes_no: bool = False) -> float | None:
    if yes_no:
        return _percentage_from_segment(segment, "Yes")
    strongly = _percentage_from_segment(segment, "Strongly agree")
    agree = _percentage_from_segment(segment, "Agree")
    if strongly is None and agree is None:
        return None
    return min(100.0, (strongly or 0.0) + (agree or 0.0))


def _segment_for_patterns(segments: list[str], patterns: Iterable[str]) -> str | None:
    normalised_patterns = [normalise_column_name(pattern) for pattern in patterns]
    for segment in segments:
        heading = segment.split(" Strongly agree", 1)[0]
        normalised = normalise_column_name(heading)
        if any(pattern in normalised for pattern in normalised_patterns):
            return segment
    return None


def _questionnaire_version(text: str) -> str:
    if "best interests at heart" in text.casefold() or "10 november 2025" in text.casefold():
        return "2025-11"
    return "2019-09"


def _latest_figures_date(text: str) -> date | None:
    dates: list[date] = []
    for value in re.findall(
        r"Figures based on \d[\d,]* responses up to\s+(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        text,
        flags=re.IGNORECASE,
    ):
        for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
            try:
                dates.append(datetime.strptime(value, fmt).date())
                break
            except ValueError:
                continue
    return max(dates) if dates else None


def _response_count_from_figures(text: str) -> int | None:
    """Return the largest published question response count on a survey page.

    Parent View pages are not consistent about the summary labels they render.
    The per-question "Figures based on ... responses" text is the most reliable
    indicator that the results page contains a publishable survey.
    """
    counts = [
        int(value.replace(",", ""))
        for value in re.findall(
            r"Figures based on\s+(\d[\d,]*)\s+responses",
            text,
            flags=re.IGNORECASE,
        )
    ]
    return max(counts) if counts else None


def _looks_like_survey_year(value: str | None) -> bool:
    return bool(value and re.fullmatch(r"\d{4}(?:/\d{2})?", value.strip()))


def read_parent_view_live_html(
    html: str,
    *,
    urn: str,
    source_url: str,
    survey_year_hint: str | None = None,
) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """Parse one Parent View survey page and return its survey links."""
    parser = _ParentViewHtmlParser()
    parser.feed(html)
    lines = parser.lines()
    text = "\n".join(lines)

    # Prefer the per-question figures because Parent View uses different summary
    # labels on landing/result pages. On current result pages, for example,
    # "Responses for year" can contain the response count rather than the year.
    response_count = _response_count_from_figures(text)
    responses_for_school = _value_after_label(lines, "Responses for this school")
    responses_for_year = _value_after_label(lines, "Responses for year")
    if response_count is None:
        for candidate in (responses_for_school, responses_for_year):
            if _looks_like_survey_year(candidate):
                continue
            response_match = re.search(r"\d[\d,]*", candidate or "")
            if response_match:
                response_count = int(response_match.group(0).replace(",", ""))
                break

    survey_links = [
        (urljoin(source_url, href), label.strip())
        for href, label in parser.links
        if _SURVEY_RESULT_RE.search(href)
    ]
    survey_links = list(dict.fromkeys(survey_links))

    survey_year = survey_year_hint
    if survey_year is None and _looks_like_survey_year(responses_for_year):
        survey_year = responses_for_year.strip()
    if survey_year is None:
        current_url = source_url.rstrip("/")
        for link, label in survey_links:
            if link.rstrip("/") == current_url:
                survey_year = label
                break

    segments = _question_segments(lines)
    row: dict[str, object] = {
        "urn": str(urn).strip(),
        "pastoral_response_count": response_count,
    }
    for output, patterns in QUESTION_PATTERNS.items():
        segment = _segment_for_patterns(segments, patterns)
        row[output] = (
            _positive_from_segment(segment, yes_no=output == "recommend_pct")
            if segment is not None
            else None
        )

    result = derive_pastoral_score(pd.DataFrame([row]))
    if response_count is None or response_count < PARENT_VIEW_MIN_SUBMISSIONS:
        result.loc[:, "pastoral_score"] = pd.NA

    figures_date = _latest_figures_date(text)
    result["parent_view_as_at_date"] = pd.Timestamp(figures_date) if figures_date else pd.NaT
    result["parent_view_survey_year"] = survey_year
    result["parent_view_questionnaire_version"] = _questionnaire_version(text)
    result["pastoral_source"] = PARENT_VIEW_LIVE_SOURCE_NAME
    result["pastoral_source_url"] = source_url

    # Preserve the site's newest-to-oldest tab order while removing duplicates.
    return result, survey_links


def _survey_targets_from_html(
    html: str,
    source_url: str,
    links: Iterable[tuple[str, str]],
) -> list[tuple[int, int, str | None]]:
    """Return survey targets discovered from links, raw HTML and redirects.

    Parent View's URN route can occasionally land on the short-lived
    September-to-November 2025 tab rather than the newer 2025/26 survey.
    The page still contains the internal school id and survey tabs, so collect
    those directly rather than trusting whichever tab the URN route selected.
    """
    labels: dict[tuple[int, int], str] = {}
    targets: set[tuple[int, int]] = set()

    for link, label in links:
        match = _SURVEY_RESULT_RE.search(link)
        if match is None or not match.group("tab").isdigit():
            continue
        key = (int(match.group("school_id")), int(match.group("tab")))
        targets.add(key)
        if _looks_like_survey_year(label):
            labels[key] = label.strip()

    for value in (source_url, html):
        for match in _SURVEY_RESULT_RE.finditer(value):
            tab = match.group("tab")
            if not tab.isdigit():
                continue
            targets.add((int(match.group("school_id")), int(tab)))

    # If the page visibly has a year-tab navigation but only one result URL was
    # discoverable, probe a small range around that tab. This is deliberately
    # conservative: a genuinely single-survey school should not trigger a run
    # of speculative requests.
    year_tabs = re.findall(r">\s*20\d{2}(?:/\d{2})?\s*<", html)
    if len(targets) == 1 and len(year_tabs) >= 2:
        school_id, newest = next(iter(targets))
        lower = max(1, newest - _SURVEY_TAB_PROBE_BACK)
        upper = newest + _SURVEY_TAB_PROBE_FORWARD
        for tab in range(lower, upper + 1):
            targets.add((school_id, tab))

    return [
        (school_id, tab, labels.get((school_id, tab)))
        for school_id, tab in sorted(targets, key=lambda item: (item[1], item[0]), reverse=True)
    ]


def _survey_result_url(source_url: str, school_id: int, tab: int, *, print_view: bool) -> str:
    route = "result-print" if print_view else "result"
    return urljoin(
        source_url,
        f"/parent-view-results/survey/{route}/{school_id}/{tab}",
    )


def _fetch_live_page(
    session: requests.Session,
    url: str,
) -> requests.Response | None:
    try:
        response = session.get(
            url,
            timeout=(10, 20),
            headers=PARENT_VIEW_BROWSER_HEADERS,
        )
        response.raise_for_status()
        return response
    except requests.RequestException:
        return None


def fetch_latest_parent_view_school(
    session: requests.Session,
    urn: str,
) -> pd.DataFrame:
    """Return the newest usable Parent View survey for the same current URN.

    The URN landing route is useful for resolving Parent View's internal school
    id, but it is not treated as authoritative for the selected survey tab.
    Once that id is known, survey tabs are checked newest-first and the simpler
    print view is preferred for parsing. Parent opinions are never followed
    across predecessor URNs.
    """
    url = PARENT_VIEW_URN_URL.format(urn=str(urn).strip())
    try:
        response = session.get(
            url,
            timeout=(10, 20),
            headers=PARENT_VIEW_BROWSER_HEADERS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SchoolFinderError(
            f"Could not retrieve live Parent View data for URN {urn}: {exc}"
        ) from exc

    source_url = getattr(response, "url", None) or url
    current, links = read_parent_view_live_html(
        response.text,
        urn=urn,
        source_url=source_url,
    )

    targets = _survey_targets_from_html(response.text, source_url, links)
    current_match = _SURVEY_RESULT_RE.search(source_url)
    current_target: tuple[int, int] | None = None
    if current_match is not None and current_match.group("tab").isdigit():
        current_target = (
            int(current_match.group("school_id")),
            int(current_match.group("tab")),
        )

    if pd.notna(current.iloc[0]["pastoral_score"]):
        if current_target is None or not any(
            school_id == current_target[0] and tab > current_target[1]
            for school_id, tab, _ in targets
        ):
            return current

    best_insufficient = current
    visited: set[str] = {source_url.rstrip("/")}

    for school_id, tab, survey_year in targets:
        if current_target == (school_id, tab):
            continue
        # The print route contains the same results with substantially simpler
        # markup and has proved more stable than the interactive result page.
        candidate = _survey_result_url(
            source_url, school_id, tab, print_view=True
        )
        key = candidate.rstrip("/")
        if key in visited:
            continue
        visited.add(key)
        historical = _fetch_live_page(session, candidate)
        if historical is None:
            continue
        parsed, _ = read_parent_view_live_html(
            historical.text,
            urn=urn,
            source_url=getattr(historical, "url", None) or candidate,
            survey_year_hint=survey_year,
        )
        row = parsed.iloc[0]
        if pd.notna(row["pastoral_score"]):
            return parsed
        current_count = pd.to_numeric(
            best_insufficient.iloc[0].get("pastoral_response_count"), errors="coerce"
        )
        candidate_count = pd.to_numeric(
            row.get("pastoral_response_count"), errors="coerce"
        )
        if pd.notna(candidate_count) and (
            pd.isna(current_count) or candidate_count > current_count
        ):
            best_insufficient = parsed

    if pd.notna(current.iloc[0]["pastoral_score"]):
        return current
    return best_insufficient


def _pastoral_row_is_usable(row: pd.Series) -> bool:
    return pd.notna(row.get("pastoral_score"))


def refresh_parent_view_for_frame(
    frame: pd.DataFrame,
    *,
    session: requests.Session | None = None,
    max_schools: int = PARENT_VIEW_LIVE_REFRESH_LIMIT,
) -> pd.DataFrame:
    """Refresh Parent View for a manageable set of candidate schools.

    The bulk management release remains the offline fallback. Live Parent View
    is used only when a lookup explicitly relies on pastoral care and the
    candidate set is small enough to query responsibly.
    """
    if frame.empty or "urn" not in frame.columns or len(frame) > max_schools:
        return frame

    own_session = session is None
    active_session = session or create_session()
    try:
        live_rows: dict[str, pd.Series] = {}
        for urn in frame["urn"].astype("string").fillna(""):
            urn_text = str(urn).strip()
            if not urn_text:
                continue
            try:
                live = fetch_latest_parent_view_school(active_session, urn_text)
            except SchoolFinderError:
                continue
            if not live.empty:
                live_rows[urn_text] = live.iloc[0]

        if not live_rows:
            return frame

        result = frame.copy()
        for index, row in result.iterrows():
            urn_text = str(row.get("urn", "")).strip()
            live = live_rows.get(urn_text)
            if live is None:
                continue

            # A usable live/current-URN survey wins. If live Parent View only has
            # an insufficient current survey, keep a usable bulk value instead.
            existing_usable = _pastoral_row_is_usable(row)
            live_usable = _pastoral_row_is_usable(live)
            if existing_usable and not live_usable:
                continue
            for column in PASTORAL_OUTPUT_COLUMNS:
                if column in live.index:
                    result.at[index, column] = live[column]
        return result
    finally:
        if own_session:
            active_session.close()
