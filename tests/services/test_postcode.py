from pathlib import Path

import pandas as pd
import pytest

from school_finder.errors import SchoolFinderError
from school_finder.services import postcode as service
from school_finder.utils import format_postcode, normalise_postcode


def test_normalise_postcode():
    assert normalise_postcode(" sw1a 2aa ") == "SW1A2AA"


def test_format_postcode():
    assert format_postcode("sw1a2aa") == "SW1A 2AA"


def test_lookup_postcode_requires_value(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    with pytest.raises(SchoolFinderError, match="postcode is required"):
        service.lookup_postcode(Path("x"), "   ")


def test_lookup_postcode_rejects_older_schema(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(service, "parquet_columns", lambda path: {"postcode"})
    with pytest.raises(SchoolFinderError, match="older postcode schema"):
        service.lookup_postcode(Path("x"), "SW1A 2AA")


def test_lookup_postcode_wraps_parquet_errors(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(service, "parquet_columns", lambda path: {"postcode","postcode_key","easting","northing","is_current","termination_date"})
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad parquet")))
    with pytest.raises(SchoolFinderError, match="Could not read"):
        service.lookup_postcode(Path("x"), "SW1A 2AA")


def test_lookup_postcode_errors_when_not_found(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(service, "parquet_columns", lambda path: {"postcode","postcode_key","easting","northing","is_current","termination_date"})
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: pd.DataFrame(columns=["postcode","postcode_key","easting","northing","is_current","termination_date"]))
    with pytest.raises(SchoolFinderError, match="not found"):
        service.lookup_postcode(Path("x"), "SW1A 2AA")


def test_lookup_postcode_prefers_current_duplicate(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(service, "parquet_columns", lambda path: {"postcode","postcode_key","easting","northing","is_current","termination_date"})
    frame = pd.DataFrame([
        {"postcode":"SW1A 2AA","postcode_key":"RG226SX","easting":1,"northing":2,"is_current":False,"termination_date":"202001"},
        {"postcode":"SW1A 2AA","postcode_key":"RG226SX","easting":3,"northing":4,"is_current":True,"termination_date":""},
    ])
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: frame)
    result = service.lookup_postcode(Path("x"), "SW1A 2AA")
    assert result.easting == 3
    assert result.is_current is True
    assert result.termination_date is None


def test_lookup_postcode_returns_termination_for_old_postcode(monkeypatch):
    monkeypatch.setattr(service, "require_pyarrow", lambda: None)
    monkeypatch.setattr(service, "parquet_columns", lambda path: {"postcode","postcode_key","easting","northing","is_current","termination_date"})
    frame = pd.DataFrame([{"postcode":"SW1A 2AA","postcode_key":"RG226SX","easting":1,"northing":2,"is_current":False,"termination_date":"202001"}])
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: frame)
    assert service.lookup_postcode(Path("x"), "SW1A 2AA").termination_date == "202001"
