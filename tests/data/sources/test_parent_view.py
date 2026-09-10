from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import parent_view
from school_finder.errors import SchoolFinderError


class Response:
    def __init__(self, error=None):
        self.error = error
        self.closed = False

    def raise_for_status(self):
        if self.error:
            raise self.error

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def get(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


def _write_parent_view_ods(path: Path, *, submissions=40):
    questions = [
        "",
        "",
        "1. My child is happy at this school",
        "",
        "",
        "2. My child feels safe at this school",
        "",
        "",
        "3. The school makes sure its pupils are well behaved",
        "",
        "",
        "4. My child has been bullied at this school. When the bullying took place, the school dealt with it quickly and effectively",
        "",
        "",
        "5. My child has Special Educational Needs and/or Disabilities. The school gives them the support they need to succeed",
        "",
        "",
        "6. The school communicates well with me about the things I need to know",
        "",
        "",
        "7. When I have raised concerns with the school they have been dealt with properly",
        "",
        "",
        "8. When the school makes decisions, it has the child's best interests at heart",
        "",
        "",
        "9. The school gives my child the right support to enable them to learn well",
        "",
        "",
        "10. Would you recommend this school to another parent?",
        "",
    ]
    responses = [
        "URN",
        "Submissions",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "I have not raised any concerns",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Strongly agree",
        "Agree",
        "Don't know",
        "Yes",
        "No",
    ]
    row = [
        "100001",
        submissions,
        0.50,
        0.30,
        0.20,
        0.60,
        0.30,
        0.10,
        0.30,
        0.40,
        0.30,
        0.20,
        0.30,
        0.50,
        0.40,
        0.30,
        0.30,
        0.40,
        0.30,
        0.30,
        0.30,
        0.20,
        0.50,
        0.40,
        0.35,
        0.25,
        0.50,
        0.25,
        0.25,
        0.85,
        0.15,
    ]
    raw = pd.DataFrame([questions, responses, row])
    with pd.ExcelWriter(path, engine="odf") as writer:
        pd.DataFrame([["Overview"]]).to_excel(writer, sheet_name="Overview", header=False, index=False)
        raw.to_excel(writer, sheet_name="School level", header=False, index=False)


def test_discover_parent_view_source_checks_release_and_wraps_errors():
    response = Response()
    source = parent_view.discover_parent_view_source(Session(response=response))
    assert source.url == parent_view.PARENT_VIEW_ODS_URL
    assert "6 April 2026" in source.release_label
    assert response.closed is True

    with pytest.raises(SchoolFinderError, match="Could not retrieve Ofsted Parent View"):
        parent_view.discover_parent_view_source(
            Session(error=requests.ConnectionError("offline"))
        )


def test_read_parent_view_school_extracts_questions_and_derives_score(tmp_path: Path):
    path = tmp_path / "parent-view.ods"
    _write_parent_view_ods(path)

    row = parent_view.read_parent_view_school(path).iloc[0]
    assert row["urn"] == "100001"
    assert row["pastoral_response_count"] == 40
    assert row["happy_pct"] == 80
    assert row["safe_pct"] == 90
    assert row["behaviour_positive_pct"] == 70
    assert row["bullying_dealt_with_pct"] == 50
    assert row["send_support_pct"] == 70
    assert row["communication_pct"] == 70
    assert row["concerns_dealt_with_pct"] == 50
    assert row["best_interests_pct"] == 75
    assert row["learning_support_pct"] == 75
    assert row["recommend_pct"] == 85
    assert row["pastoral_score_coverage_pct"] == 100
    assert row["pastoral_score"] == pytest.approx(72.75)
    assert row["parent_view_as_at_date"] == pd.Timestamp("2026-04-06")
    assert row["pastoral_source"] == parent_view.PARENT_VIEW_SOURCE_NAME


def test_pastoral_score_redistributes_missing_question_weights_and_has_minimum_coverage():
    frame = pd.DataFrame(
        [
            {
                "happy_pct": 80,
                "safe_pct": 90,
                "behaviour_positive_pct": 70,
                "bullying_dealt_with_pct": None,
                "send_support_pct": None,
                "communication_pct": 60,
                "concerns_dealt_with_pct": 50,
                "best_interests_pct": None,
                "learning_support_pct": None,
            },
            {
                "happy_pct": 80,
                "safe_pct": None,
                "behaviour_positive_pct": None,
                "bullying_dealt_with_pct": None,
                "send_support_pct": None,
                "communication_pct": None,
                "concerns_dealt_with_pct": None,
                "best_interests_pct": None,
                "learning_support_pct": None,
            },
        ]
    )
    result = parent_view.derive_pastoral_score(frame)
    assert result.iloc[0]["pastoral_score_coverage_pct"] == 50
    assert result.iloc[0]["pastoral_score"] == pytest.approx(78)
    assert result.iloc[1]["pastoral_score_coverage_pct"] == 15
    assert pd.isna(result.iloc[1]["pastoral_score"])


def test_low_submission_count_keeps_components_but_suppresses_overall_score(tmp_path: Path):
    path = tmp_path / "parent-view.ods"
    _write_parent_view_ods(path, submissions=9)
    row = parent_view.read_parent_view_school(path).iloc[0]
    assert row["happy_pct"] == 80
    assert pd.isna(row["pastoral_score"])


def test_percentage_parser_handles_percent_strings_fractions_and_missing():
    result = parent_view._parse_percentage(pd.Series(["75%", "0.8", 0.25, "40", "", None]))
    assert result.iloc[:4].tolist() == [75.0, 80.0, 25.0, 40.0]
    assert pd.isna(result.iloc[4])
    assert pd.isna(result.iloc[5])


def test_parent_view_requires_school_level_table(tmp_path: Path):
    path = tmp_path / "bad.ods"
    with pd.ExcelWriter(path, engine="odf") as writer:
        pd.DataFrame([["not", "a", "school", "table"]]).to_excel(
            writer, header=False, index=False
        )
    with pytest.raises(SchoolFinderError, match="school-level table"):
        parent_view.read_parent_view_school(path)


def test_parent_view_wraps_invalid_spreadsheet(tmp_path: Path):
    path = tmp_path / "bad.ods"
    path.write_text("not an ods")
    with pytest.raises(SchoolFinderError, match="Could not read Ofsted Parent View spreadsheet"):
        parent_view.read_parent_view_school(path)


def test_parent_view_helpers_handle_missing_and_aggregated_columns():
    frame = pd.DataFrame({
        "Some other question Agree": [0.5],
        "My child is happy at this school Positive": ["75%"],
        "My child feels safe at this school Disagree": [0.2],
        "My child feels safe at this school Don't know": [0.1],
    })
    assert parent_view._find_identity_column(frame, "URN") is None
    missing = parent_view._positive_percentage(frame, ("does not exist",))
    assert pd.isna(missing.iloc[0])
    aggregated = parent_view._positive_percentage(frame, ("child is happy",))
    assert aggregated.iloc[0] == 75
    no_positive = parent_view._positive_percentage(frame, ("child feels safe",))
    assert pd.isna(no_positive.iloc[0])


def test_parent_view_handles_empty_school_table_and_sheet_read_error(tmp_path: Path, monkeypatch):
    empty_path = tmp_path / "empty-school-table.ods"
    with pd.ExcelWriter(empty_path, engine="odf") as writer:
        pd.DataFrame([["URN", "Submissions"]]).to_excel(
            writer, sheet_name="School level", header=False, index=False
        )
    with pytest.raises(SchoolFinderError, match="school-level table"):
        parent_view.read_parent_view_school(empty_path)

    valid_path = tmp_path / "valid.ods"
    _write_parent_view_ods(valid_path)
    monkeypatch.setattr(parent_view.pd, "read_excel", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad sheet")))
    with pytest.raises(SchoolFinderError, match="Could not read Ofsted Parent View sheet"):
        parent_view.read_parent_view_school(valid_path)


def test_parent_view_requires_identity_columns_after_table_detection(monkeypatch):
    monkeypatch.setattr(
        parent_view,
        "_school_level_frame",
        lambda path: pd.DataFrame({"Other": ["value"]}),
    )
    with pytest.raises(SchoolFinderError, match="missing URN or submissions"):
        parent_view.read_parent_view_school(Path("ignored.ods"))


def _live_html(*, responses=40, survey_year="2025/26", old=False, links=()):
    if old:
        questions = [
            ("1. My child is happy at this school.", 60, 25),
            ("2. My child feels safe at this school.", 55, 30),
            ("3. The school makes sure its pupils are well behaved.", 45, 35),
            ("4. My child has been bullied and the school dealt with the bullying quickly and effectively.", 20, 30),
            ("6. When I have raised concerns with the school they have been dealt with properly.", 35, 30),
            ("7. My child has SEND, and the school gives them the support they need to succeed.", 30, 40),
            ("10. The school lets me know how my child is doing.", 40, 35),
            ("13. The school supports my child’s wider personal development.", 45, 35),
        ]
        recommend = "14. I would recommend this school to another parent."
    else:
        questions = [
            ("1. My child is happy at this school", 50, 30),
            ("2. My child feels safe at this school", 60, 30),
            ("3. The school makes sure its pupils are well behaved", 30, 40),
            ("4. My child has been bullied at this school. When the bullying took place, the school dealt with it quickly and effectively", 20, 30),
            ("5. My child has Special Educational Needs and/or Disabilities. The school gives them the support they need to succeed", 40, 30),
            ("6. The school communicates well with me about the things I need to know", 40, 30),
            ("7. When I have raised concerns with the school they have been dealt with properly", 30, 20),
            ("8. When the school makes decisions, it has the child's best interests at heart", 40, 35),
            ("9. The school gives my child the right support to enable them to learn well", 40, 35),
        ]
        recommend = "10. Would you recommend this school to another parent?"

    link_html = "".join(f'<a href="{href}">{label}</a>' for href, label in links)
    if old:
        count_html = f"<div>Responses for year:</div><div>{responses}</div>"
    else:
        count_html = (
            f"<div>Responses for this school:</div><div>{responses}</div>"
            f"<div>Responses for year:</div><div>{survey_year}</div>"
        )
    question_html = "".join(
        f"<section><h3>{question}</h3><div>Strongly agree : {strongly}%</div>"
        f"<div>Agree : {agree}%</div><div>Disagree : 5%</div>"
        f"<p>Figures based on {responses} responses up to 03-06-2026</p></section>"
        for question, strongly, agree in questions
    )
    return (
        "<html><body>"
        + link_html
        + count_html
        + question_html
        + f"<section><h3>{recommend}</h3><div>Yes : 85%</div><div>No : 15%</div>"
        + f"<p>Figures based on {responses} responses up to 03-06-2026</p></section>"
        + "</body></html>"
    )


def test_live_parent_view_parser_handles_new_questionnaire():
    result, links = parent_view.read_parent_view_live_html(
        _live_html(),
        urn="100001",
        source_url="https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/17",
    )
    row = result.iloc[0]
    assert row["pastoral_response_count"] == 40
    assert row["parent_view_survey_year"] == "2025/26"
    assert row["parent_view_questionnaire_version"] == "2025-11"
    assert row["happy_pct"] == 80
    assert row["safe_pct"] == 90
    assert row["recommend_pct"] == 85
    assert row["pastoral_score_coverage_pct"] == 100
    assert pd.notna(row["pastoral_score"])
    assert row["parent_view_as_at_date"] == pd.Timestamp("2026-06-03")
    assert links == []


def test_live_parent_view_parser_handles_legacy_questionnaire():
    result, _ = parent_view.read_parent_view_live_html(
        _live_html(old=True),
        urn="100001",
        source_url="https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/15",
        survey_year_hint="2024/25",
    )
    row = result.iloc[0]
    assert row["pastoral_response_count"] == 40
    assert row["parent_view_survey_year"] == "2024/25"
    assert row["parent_view_questionnaire_version"] == "2019-09"
    assert row["communication_pct"] == 75
    assert row["personal_development_pct"] == 80
    assert pd.isna(row["best_interests_pct"])
    assert row["pastoral_score_coverage_pct"] >= 50
    assert pd.notna(row["pastoral_score"])


class LiveResponse:
    def __init__(self, text, url, error=None):
        self.text = text
        self.url = url
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error


class LiveSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


def test_fetch_latest_parent_view_falls_back_to_latest_usable_same_urn_survey():
    current_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/17"
    old_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/15"
    current_html = _live_html(
        responses=1,
        links=(("/parent-view-results/survey/result/1/17", "2025/26"), (old_url, "2024/25")),
    )
    session = LiveSession(
        [
            LiveResponse(current_html, current_url),
            LiveResponse(_live_html(responses=71, old=True), old_url),
        ]
    )
    row = parent_view.fetch_latest_parent_view_school(session, "100001").iloc[0]
    assert row["pastoral_response_count"] == 71
    assert row["parent_view_survey_year"] == "2024/25"
    assert row["pastoral_source"] == parent_view.PARENT_VIEW_LIVE_SOURCE_NAME
    assert pd.notna(row["pastoral_score"])
    assert session.urls[0].endswith("/urn/100001")


def test_fetch_latest_parent_view_returns_insufficient_current_when_no_usable_history():
    current_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/17"
    session = LiveSession([LiveResponse(_live_html(responses=1), current_url)])
    row = parent_view.fetch_latest_parent_view_school(session, "100001").iloc[0]
    assert row["pastoral_response_count"] == 1
    assert pd.isna(row["pastoral_score"])


def test_fetch_latest_parent_view_wraps_initial_request_and_skips_failed_history():
    with pytest.raises(SchoolFinderError, match="live Parent View"):
        parent_view.fetch_latest_parent_view_school(
            LiveSession([requests.ConnectionError("offline")]), "100001"
        )

    current_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/17"
    old_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/15"
    current_html = _live_html(
        responses=1,
        links=((old_url, "2024/25"),),
    )
    result = parent_view.fetch_latest_parent_view_school(
        LiveSession(
            [
                LiveResponse(current_html, current_url),
                requests.ConnectionError("offline"),
            ]
        ),
        "100001",
    )
    assert pd.isna(result.iloc[0]["pastoral_score"])


def test_refresh_parent_view_prefers_usable_live_data_and_preserves_usable_bulk_fallback(monkeypatch):
    frame = pd.DataFrame(
        [
            {"urn": "1", "pastoral_score": None, "pastoral_response_count": None},
            {"urn": "2", "pastoral_score": 70.0, "pastoral_response_count": 50},
        ]
    )

    def fetch(session, urn):
        if urn == "1":
            return pd.DataFrame(
                [{
                    "urn": "1",
                    "pastoral_score": 82.0,
                    "pastoral_response_count": 80,
                    "pastoral_score_coverage_pct": 100.0,
                    "parent_view_survey_year": "2025/26",
                }]
            )
        return pd.DataFrame(
            [{
                "urn": "2",
                "pastoral_score": None,
                "pastoral_response_count": 1,
                "parent_view_survey_year": "2025/26",
            }]
        )

    monkeypatch.setattr(parent_view, "fetch_latest_parent_view_school", fetch)
    session = LiveSession([])
    result = parent_view.refresh_parent_view_for_frame(frame, session=session).set_index("urn")
    assert result.loc["1", "pastoral_score"] == 82
    assert result.loc["1", "pastoral_response_count"] == 80
    assert result.loc["2", "pastoral_score"] == 70
    assert result.loc["2", "pastoral_response_count"] == 50


def test_refresh_parent_view_handles_limits_network_failures_and_owned_session(monkeypatch):
    frame = pd.DataFrame([{"urn": "1", "pastoral_score": None}])
    assert parent_view.refresh_parent_view_for_frame(frame.iloc[0:0]).empty
    assert parent_view.refresh_parent_view_for_frame(frame.drop(columns="urn")).equals(frame.drop(columns="urn"))
    assert parent_view.refresh_parent_view_for_frame(pd.concat([frame] * 2), max_schools=1).equals(pd.concat([frame] * 2))

    owned = LiveSession([])
    monkeypatch.setattr(parent_view, "create_session", lambda: owned)
    monkeypatch.setattr(
        parent_view,
        "fetch_latest_parent_view_school",
        lambda session, urn: (_ for _ in ()).throw(SchoolFinderError("offline")),
    )
    result = parent_view.refresh_parent_view_for_frame(frame)
    assert result.equals(frame)
    assert owned.closed is True


def test_school_level_reader_combines_multiple_school_tables(tmp_path: Path):
    first = tmp_path / "multi.ods"
    questions = ["", "", "1. My child is happy at this school", ""]
    responses = ["URN", "Submissions", "Strongly agree", "Agree"]
    with pd.ExcelWriter(first, engine="odf") as writer:
        pd.DataFrame([questions, responses, ["100001", 20, 0.4, 0.4]]).to_excel(
            writer, sheet_name="State schools", header=False, index=False
        )
        pd.DataFrame([questions, responses, ["100002", 30, 0.5, 0.4]]).to_excel(
            writer, sheet_name="Independent schools", header=False, index=False
        )
    result = parent_view.read_parent_view_school(first)
    assert set(result["urn"]) == {"100001", "100002"}


def test_live_parent_view_parser_prefers_question_figures_over_misleading_summary_count():
    html = _live_html(responses=404).replace(
        "<div>Responses for this school:</div><div>404</div>",
        "<div>Responses for this school:</div><div>1</div>",
    )
    result, _ = parent_view.read_parent_view_live_html(
        html,
        urn="149707",
        source_url="https://parentview.ofsted.gov.uk/parent-view-results/survey/result/5001663/17",
        survey_year_hint="2025/26",
    )
    row = result.iloc[0]
    assert row["pastoral_response_count"] == 404
    assert pd.notna(row["pastoral_score"])


def test_live_parent_view_parser_handles_response_count_in_responses_for_year_label():
    html = _live_html(responses=79, survey_year="2025/26")
    html = html.replace(
        "<div>Responses for this school:</div><div>79</div><div>Responses for year:</div><div>2025/26</div>",
        "<div>Responses for year:</div><div>79</div>",
    )
    source_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/12191/17"
    html = html.replace(
        "<html><body>",
        '<html><body><a href="/parent-view-results/survey/result/12191/17/">2025/26</a>',
    )
    result, links = parent_view.read_parent_view_live_html(
        html, urn="116440", source_url=source_url
    )
    row = result.iloc[0]
    assert row["pastoral_response_count"] == 79
    assert row["parent_view_survey_year"] == "2025/26"
    assert pd.notna(row["pastoral_score"])
    assert links[0][1] == "2025/26"


def test_fetch_latest_parent_view_uses_browser_headers():
    class HeaderSession(LiveSession):
        def __init__(self, responses):
            super().__init__(responses)
            self.headers_seen = []

        def get(self, url, **kwargs):
            self.headers_seen.append(kwargs.get("headers"))
            return super().get(url, **kwargs)

    current_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/1/17"
    session = HeaderSession([LiveResponse(_live_html(responses=40), current_url)])
    parent_view.fetch_latest_parent_view_school(session, "100001")
    assert session.headers_seen[0]["Accept-Language"].startswith("en-GB")
    assert "Mozilla/5.0" in session.headers_seen[0]["User-Agent"]


def test_fetch_latest_parent_view_does_not_trust_stale_urn_landing_tab():
    landing_url = "https://parentview.ofsted.gov.uk/parent-view-results/urn/149707"
    current_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result/5001663/18"
    usable_url = "https://parentview.ofsted.gov.uk/parent-view-results/survey/result-print/5001663/17"
    landing_html = _live_html(
        responses=0,
        survey_year="2026/27",
        links=(
            ("/parent-view-results/survey/result/5001663/18", "2026/27"),
            ("/parent-view-results/survey/result/5001663/17#results", "2025/26"),
        ),
    )
    no_results = "<html><body><div>Responses for year:</div><div>0</div></body></html>"
    session = LiveSession(
        [
            LiveResponse(landing_html, landing_url),
            LiveResponse(no_results, current_url),
            LiveResponse(_live_html(responses=404), usable_url),
        ]
    )

    row = parent_view.fetch_latest_parent_view_school(session, "149707").iloc[0]

    assert row["pastoral_response_count"] == 404
    assert row["parent_view_survey_year"] == "2025/26"
    assert pd.notna(row["pastoral_score"])
    assert usable_url in session.urls


def test_survey_targets_are_found_even_when_tab_url_has_fragment_or_non_year_label():
    html = (
        '<a href="/parent-view-results/survey/result/12191/17#results">Latest results</a>'
        '<a href="/parent-view-results/survey/result/12191/15?view=all">2024/25</a>'
    )
    _, links = parent_view.read_parent_view_live_html(
        html,
        urn="116440",
        source_url="https://parentview.ofsted.gov.uk/parent-view-results/urn/116440",
    )
    targets = parent_view._survey_targets_from_html(
        html,
        "https://parentview.ofsted.gov.uk/parent-view-results/urn/116440",
        links,
    )
    assert (12191, 17, None) in targets
    assert (12191, 15, "2024/25") in targets
