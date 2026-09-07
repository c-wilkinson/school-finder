from datetime import datetime, timedelta, timezone

from school_finder import utils


def test_log_writes_to_stderr(capsys):
    utils.log("hello")
    captured = capsys.readouterr()
    assert captured.err == "hello\n"
    assert captured.out == ""


def test_utc_now_is_timezone_aware_utc():
    value = utils.utc_now()
    assert value.tzinfo == timezone.utc


def test_iso_utc_converts_offset_and_uses_z_suffix():
    value = datetime(2026, 9, 7, 13, 30, tzinfo=timezone(timedelta(hours=1)))
    assert utils.iso_utc(value) == "2026-09-07T12:30:00Z"


def test_normalise_and_format_postcode():
    assert utils.normalise_postcode(" rg22  6sx ") == "RG226SX"
    assert utils.format_postcode("rg226sx") == "RG22 6SX"
    assert utils.format_postcode("AB") == "AB"
