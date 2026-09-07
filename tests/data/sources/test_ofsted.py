from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import ofsted
from school_finder.data.sources.common import CsvSource
from school_finder.errors import SchoolFinderError


class Response:
    def __init__(self, text="", error=None): self.text, self.error = text, error
    def raise_for_status(self):
        if self.error: raise self.error


class Session:
    def __init__(self, response=None, error=None): self.response, self.error = response, error
    def get(self, *args, **kwargs):
        if self.error: raise self.error
        return self.response


def test_discover_ofsted_csv_matches_label_and_resolves_relative_url():
    html = '<a href="/files/latest.csv"><span>State-funded schools</span> – latest inspections as at 31 August 2026</a>'
    source = ofsted.discover_ofsted_csv(
        Session(Response(html)),
        "https://www.gov.uk/page",
        required_phrases=("state-funded schools", "latest inspections as at"),
        source_name="Ofsted test",
    )
    assert source.url == "https://www.gov.uk/files/latest.csv"
    assert "31 August 2026" in source.release_label


def test_discover_ofsted_csv_ignores_non_csv_and_errors_if_missing():
    html = '<a href="/files/latest.xlsx">State-funded schools latest inspections as at today</a>'
    with pytest.raises(SchoolFinderError, match="Could not discover"):
        ofsted.discover_ofsted_csv(Session(Response(html)), "https://www.gov.uk/page", required_phrases=("state-funded",), source_name="Test")


def test_discover_ofsted_csv_wraps_request_error():
    with pytest.raises(SchoolFinderError, match="Could not retrieve"):
        ofsted.discover_ofsted_csv(Session(error=requests.Timeout()), "https://www.gov.uk/page", required_phrases=("x",), source_name="Test")


def test_latest_source_wrappers_use_expected_pages(monkeypatch):
    calls = []
    def fake(session, page_url, **kwargs):
        calls.append((page_url, kwargs))
        return CsvSource(kwargs["source_name"], "url", "label")
    monkeypatch.setattr(ofsted, "discover_ofsted_csv", fake)
    state = ofsted.discover_latest_ofsted_source(object())
    independent = ofsted.discover_latest_independent_ofsted_source(object())
    assert state.name.startswith("Ofsted state-funded")
    assert independent.name.startswith("Ofsted non-association")
    assert calls[0][0] == ofsted.OFSTED_MANAGEMENT_URL
    assert calls[1][0] == ofsted.OFSTED_INDEPENDENT_URL


def test_read_ofsted_quality_maps_aliases_dates_and_keeps_latest_per_urn(tmp_path: Path):
    path = tmp_path / "ofsted.csv"
    pd.DataFrame([
        {"URN":"100001", "Overall effectiveness":"Requires improvement", "Inspection start date":"01/01/2024", "Publication date":"15/01/2024", "Safeguarding standards":"Met", "Quality of education":"Good"},
        {"URN":"100001", "Overall effectiveness":"Good", "Inspection start date":"02/02/2025", "Publication date":"20/02/2025", "Safeguarding standards":"Met", "Quality of education":"Good"},
        {"URN":"", "Overall effectiveness":"Outstanding"},
    ]).to_csv(path, index=False)
    result = ofsted.read_ofsted_quality(path)
    assert len(result) == 1
    assert result.iloc[0]["ofsted_rating"] == "Good"
    assert result.iloc[0]["ofsted_inspection_date"] == pd.Timestamp("2025-02-02")
    assert result.iloc[0]["ofsted_curriculum_teaching"] == "Good"
    assert pd.isna(result.iloc[0]["ofsted_inclusion"])


def test_read_ofsted_quality_requires_urn(tmp_path):
    path = tmp_path / "ofsted.csv"
    pd.DataFrame({"School": ["Example"]}).to_csv(path, index=False)
    with pytest.raises(SchoolFinderError, match="URN column"):
        ofsted.read_ofsted_quality(path)


def test_discover_ofsted_csv_skips_unrelated_anchor_before_match():
    html = (
        '<a href="/unrelated.csv">Something else</a>'
        '<a href="/latest.csv">State-funded schools latest inspections as at today</a>'
    )
    source = ofsted.discover_ofsted_csv(
        Session(Response(html)), "https://www.gov.uk/page",
        required_phrases=("state-funded schools", "latest inspections as at"),
        source_name="Test",
    )
    assert source.url.endswith("/latest.csv")
