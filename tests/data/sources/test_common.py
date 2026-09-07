from pathlib import Path

import pandas as pd
import pytest
import requests

from school_finder.data.sources import common
from school_finder.data.sources.common import CsvSource
from school_finder.errors import SchoolFinderError


class FakeResponse:
    def __init__(self, *, payload=None, text="", chunks=(), status_error=None):
        self._payload = payload
        self.text = text
        self._chunks = list(chunks)
        self._status_error = status_error
        self.closed = False

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_create_session_sets_user_agent():
    session = common.create_session()
    assert session.headers["User-Agent"] == common.USER_AGENT


def test_fetch_json_returns_mapping_and_passes_params():
    session = FakeSession(FakeResponse(payload={"ok": True}))
    assert common.fetch_json(session, "https://example.test", params={"q": "x"}) == {"ok": True}
    assert session.calls[0][1]["params"] == {"q": "x"}


@pytest.mark.parametrize(
    "response,match",
    [
        (FakeResponse(payload=[]), "unexpected data"),
        (FakeResponse(payload={"error": {"message": "bad"}}), "Service error"),
    ],
)
def test_fetch_json_rejects_invalid_payloads(response, match):
    with pytest.raises(SchoolFinderError, match=match):
        common.fetch_json(FakeSession(response), "https://example.test")


def test_fetch_json_wraps_request_errors():
    with pytest.raises(SchoolFinderError, match="Could not retrieve"):
        common.fetch_json(
            FakeSession(error=requests.ConnectionError("offline")),
            "https://example.test",
        )


def test_fetch_json_wraps_json_decode_errors():
    exc = requests.JSONDecodeError("bad", "x", 0)
    with pytest.raises(SchoolFinderError, match="invalid JSON"):
        common.fetch_json(FakeSession(FakeResponse(payload=exc)), "https://example.test")


def test_stream_download_writes_nonempty_chunks(tmp_path: Path):
    destination = tmp_path / "download.bin"
    response = FakeResponse(chunks=[b"abc", b"", b"def"])
    common.stream_download(FakeSession(response), "https://example.test/a", destination, minimum_size=6)
    assert destination.read_bytes() == b"abcdef"


def test_stream_download_removes_partial_file_on_request_error(tmp_path: Path):
    destination = tmp_path / "download.bin"
    destination.write_bytes(b"partial")
    with pytest.raises(SchoolFinderError, match="Could not download"):
        common.stream_download(
            FakeSession(error=requests.Timeout("timeout")),
            "https://example.test/a",
            destination,
            minimum_size=1,
        )
    assert not destination.exists()


def test_stream_download_rejects_unexpectedly_small_file(tmp_path: Path):
    destination = tmp_path / "download.bin"
    with pytest.raises(SchoolFinderError, match="unexpectedly small"):
        common.stream_download(
            FakeSession(FakeResponse(chunks=[b"tiny"])),
            "https://example.test/a",
            destination,
            minimum_size=10,
        )
    assert not destination.exists()


def test_download_csv_delegates_to_stream_download(tmp_path, monkeypatch, capsys):
    called = {}
    monkeypatch.setattr(
        common,
        "stream_download",
        lambda session, url, destination, minimum_size: called.update(
            url=url, destination=destination, minimum_size=minimum_size
        ),
    )
    source = CsvSource("Example source", "https://example.test/x.csv", "2026")
    destination = tmp_path / "x.csv"
    common.download_csv(object(), source, destination, minimum_size=123)
    assert called == {"url": source.url, "destination": destination, "minimum_size": 123}
    assert "Downloading Example source" in capsys.readouterr().err


def test_column_helpers_find_aliases():
    frame = pd.DataFrame(columns=[" School URN ", "Attainment 8 Average"])
    assert common.normalise_column_name(" Attainment 8 Average ") == "attainment8average"
    assert common.normalised_columns(frame)["schoolurn"] == " School URN "
    assert common.find_column(frame, "missing", "school_urn") == " School URN "
    assert common.find_column(frame, "missing") is None


def test_text_and_numeric_quality_clean_publisher_markers():
    series = pd.Series([" 12.5 ", "z", "X", "", None, "n/a", "3"])
    cleaned = common.clean_text_series(series)
    assert cleaned.iloc[0] == "12.5"
    numeric = common.numeric_quality(series)
    assert numeric.iloc[0] == 12.5
    assert pd.isna(numeric.iloc[1])
    assert pd.isna(numeric.iloc[2])
    assert pd.isna(numeric.iloc[3])
    assert numeric.iloc[6] == 3.0


def test_read_public_csv_falls_back_to_cp1252(tmp_path: Path):
    path = tmp_path / "publisher.csv"
    path.write_bytes("name\nSchool – Academy\n".encode("cp1252"))
    frame = common.read_public_csv(path, "Publisher")
    assert frame.iloc[0, 0] == "School – Academy"


def test_read_public_csv_reports_decode_failure(monkeypatch, tmp_path):
    error = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
    monkeypatch.setattr(pd, "read_csv", lambda *args, **kwargs: (_ for _ in ()).throw(error))
    with pytest.raises(SchoolFinderError, match="Could not decode Test CSV"):
        common.read_public_csv(tmp_path / "x.csv", "Test")
