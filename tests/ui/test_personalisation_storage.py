from __future__ import annotations

import json

import pytest

from school_finder.models.personalisation import PersonalSchoolState, SchoolDisposition
from school_finder.ui.personalisation_storage import (
    BROWSER_STORAGE_KEY,
    PERSISTENCE_CLEAR_PENDING_KEY,
    PERSISTENCE_ENABLED_KEY,
    PERSISTENCE_HYDRATED_KEY,
    PERSISTENCE_LAST_SYNC_KEY,
    PERSISTENCE_WARNING_KEY,
    STORAGE_SCHEMA_VERSION,
    StorageCommand,
    decode_personalisation,
    enable_persistence,
    encode_personalisation,
    forget_persistence,
    handle_storage_response,
    is_persistence_enabled,
    is_persistence_hydrated,
    is_persistence_synced,
    next_storage_command,
    persistence_warning,
)
from school_finder.ui.state import PERSONAL_SCHOOLS_KEY


def _payload(schools=None, *, version=STORAGE_SCHEMA_VERSION):
    return json.dumps({"schema_version": version, "schools": schools or {}})


def test_storage_constants_and_round_trip_are_stable_and_unicode_safe():
    assert BROWSER_STORAGE_KEY == "school-finder.personalisation.v1"
    personal = {
        "200002": PersonalSchoolState(SchoolDisposition.NOT_FOR_US, 2, "No thanks"),
        "100001": PersonalSchoolState(SchoolDisposition.SHORTLISTED, 5, "Great ✓"),
    }

    encoded = encode_personalisation(personal)

    assert '"schools":{"100001"' in encoded
    assert "Great ✓" in encoded
    assert decode_personalisation(encoded) == personal


def test_decode_rejects_invalid_envelopes():
    invalid = [
        None,
        "   ",
        "not json",
        "[]",
        _payload(version=999),
        json.dumps({"schema_version": STORAGE_SCHEMA_VERSION, "schools": []}),
    ]
    for payload in invalid:
        with pytest.raises(ValueError):
            decode_personalisation(payload)  # type: ignore[arg-type]


def test_decode_skips_invalid_school_entries_and_default_rows():
    payload = _payload(
        {
            "": {"disposition": "shortlisted"},
            "bad-state": None,
            "bad-notes": {"disposition": "shortlisted", "notes": 123},
            "bad-disposition": {"disposition": "maybe"},
            "bad-rating": {"disposition": "shortlisted", "rating": 9},
            "default": {"disposition": "neutral", "rating": None, "notes": None},
            " 100001 ": {
                "disposition": "shortlisted",
                "rating": 4,
                "notes": "  Saved note  ",
            },
        }
    )

    decoded = decode_personalisation(payload)

    assert decoded == {
        "100001": PersonalSchoolState(SchoolDisposition.SHORTLISTED, 4, "Saved note")
    }


def test_persistence_status_helpers_require_literal_true_and_valid_warning():
    assert is_persistence_hydrated({}) is False
    assert is_persistence_hydrated({PERSISTENCE_HYDRATED_KEY: 1}) is False
    assert is_persistence_hydrated({PERSISTENCE_HYDRATED_KEY: True}) is True
    assert is_persistence_enabled({PERSISTENCE_ENABLED_KEY: "yes"}) is False
    assert is_persistence_enabled({PERSISTENCE_ENABLED_KEY: True}) is True
    assert persistence_warning({}) is None
    assert persistence_warning({PERSISTENCE_WARNING_KEY: 123}) is None
    assert persistence_warning({PERSISTENCE_WARNING_KEY: ""}) is None
    assert persistence_warning({PERSISTENCE_WARNING_KEY: "problem"}) == "problem"


def test_enable_and_forget_persistence_manage_only_storage_flags():
    personal = {"100001": PersonalSchoolState(SchoolDisposition.SHORTLISTED)}
    state = {
        PERSONAL_SCHOOLS_KEY: personal,
        PERSISTENCE_WARNING_KEY: "old",
        PERSISTENCE_LAST_SYNC_KEY: "old payload",
    }

    enable_persistence(state)
    assert state[PERSONAL_SCHOOLS_KEY] == personal
    assert state[PERSISTENCE_ENABLED_KEY] is True
    assert state[PERSISTENCE_HYDRATED_KEY] is True
    assert PERSISTENCE_WARNING_KEY not in state
    assert PERSISTENCE_LAST_SYNC_KEY not in state

    forget_persistence(state)
    assert state[PERSONAL_SCHOOLS_KEY] == personal
    assert state[PERSISTENCE_ENABLED_KEY] is False
    assert state[PERSISTENCE_CLEAR_PENDING_KEY] is True
    assert PERSISTENCE_LAST_SYNC_KEY not in state


def test_next_storage_command_load_clear_disabled_save_and_synced_paths():
    state = {}
    assert next_storage_command(state) == StorageCommand("load", "load-v1")

    state = {
        PERSISTENCE_HYDRATED_KEY: True,
        PERSISTENCE_CLEAR_PENDING_KEY: True,
    }
    assert next_storage_command(state) == StorageCommand("clear", "clear-v1")

    state = {PERSISTENCE_HYDRATED_KEY: True}
    assert next_storage_command(state) is None

    state = {
        PERSISTENCE_HYDRATED_KEY: True,
        PERSISTENCE_ENABLED_KEY: True,
    }
    command = next_storage_command(state)
    assert command is not None
    assert command.action == "save"
    assert command.request_id.startswith("save-")
    assert decode_personalisation(command.payload) == {}  # type: ignore[arg-type]

    state[PERSISTENCE_LAST_SYNC_KEY] = command.payload
    assert next_storage_command(state) is None

    state[PERSONAL_SCHOOLS_KEY] = {
        "100001": PersonalSchoolState(SchoolDisposition.SHORTLISTED)
    }
    changed = next_storage_command(state)
    assert changed is not None and changed.action == "save"
    assert changed.payload != command.payload


def test_is_persistence_synced_requires_enabled_hydrated_and_current_payload():
    assert is_persistence_synced({}) is False
    assert (
        is_persistence_synced(
            {PERSISTENCE_ENABLED_KEY: True, PERSISTENCE_HYDRATED_KEY: False}
        )
        is False
    )
    state = {
        PERSISTENCE_ENABLED_KEY: True,
        PERSISTENCE_HYDRATED_KEY: True,
    }
    assert is_persistence_synced(state) is False
    state[PERSISTENCE_LAST_SYNC_KEY] = encode_personalisation({})
    assert is_persistence_synced(state) is True


def test_handle_storage_response_ignores_missing_or_malformed_responses():
    state = {}
    for response in (
        None,
        "bad",
        {},
        {"action": "unknown", "request_id": "x", "ok": True},
        {"action": "load", "request_id": 123, "ok": True},
    ):
        handle_storage_response(state, response)  # type: ignore[arg-type]
    assert state == {}


def test_handle_load_absent_payload_marks_checked_without_opt_in():
    state = {}
    handle_storage_response(
        state,
        {"action": "load", "request_id": "load-v1", "ok": True, "payload": None},
    )
    assert state[PERSISTENCE_HYDRATED_KEY] is True
    assert state[PERSISTENCE_ENABLED_KEY] is False
    assert PERSISTENCE_LAST_SYNC_KEY not in state


def test_handle_load_restores_and_canonicalises_saved_personalisation():
    state = {PERSISTENCE_WARNING_KEY: "old warning"}
    payload = _payload(
        {
            "100001": {
                "disposition": "shortlisted",
                "rating": 4,
                "notes": "Great",
            }
        }
    )
    handle_storage_response(
        state,
        {"action": "load", "request_id": "load-v1", "ok": True, "payload": payload},
    )
    assert state[PERSONAL_SCHOOLS_KEY]["100001"].rating == 4
    assert state[PERSISTENCE_ENABLED_KEY] is True
    assert state[PERSISTENCE_HYDRATED_KEY] is True
    assert state[PERSISTENCE_LAST_SYNC_KEY] == encode_personalisation(
        state[PERSONAL_SCHOOLS_KEY]
    )
    assert PERSISTENCE_WARNING_KEY not in state

    before = dict(state)
    handle_storage_response(
        state,
        {"action": "load", "request_id": "load-v1", "ok": True, "payload": None},
    )
    assert state == before


def test_handle_load_of_empty_saved_envelope_clears_old_session_personalisation():
    state = {
        PERSONAL_SCHOOLS_KEY: {
            "100001": PersonalSchoolState(SchoolDisposition.SHORTLISTED)
        }
    }
    handle_storage_response(
        state,
        {
            "action": "load",
            "request_id": "load-v1",
            "ok": True,
            "payload": _payload(),
        },
    )
    assert PERSONAL_SCHOOLS_KEY not in state
    assert state[PERSISTENCE_ENABLED_KEY] is True


def test_handle_load_invalid_payload_types_and_content_degrade_to_session_only():
    for payload in (123, "not json"):
        state = {}
        handle_storage_response(
            state,
            {"action": "load", "request_id": "load-v1", "ok": True, "payload": payload},
        )
        assert state[PERSISTENCE_ENABLED_KEY] is False
        assert state[PERSISTENCE_HYDRATED_KEY] is True
        assert "could not be read" in state[PERSISTENCE_WARNING_KEY]


def test_storage_errors_have_action_specific_copy_and_disable_persistence():
    expected = {
        "load": "could not be read",
        "save": "could not be saved",
        "clear": "could not be removed",
    }
    for action, phrase in expected.items():
        state = {
            PERSISTENCE_ENABLED_KEY: True,
            PERSISTENCE_CLEAR_PENDING_KEY: True,
            PERSISTENCE_LAST_SYNC_KEY: "old",
        }
        handle_storage_response(
            state,
            {"action": action, "request_id": "x", "ok": False},
        )
        assert phrase in state[PERSISTENCE_WARNING_KEY]
        assert state[PERSISTENCE_ENABLED_KEY] is False
        assert state[PERSISTENCE_HYDRATED_KEY] is True
        assert PERSISTENCE_CLEAR_PENDING_KEY not in state
        assert PERSISTENCE_LAST_SYNC_KEY not in state


def test_handle_save_acknowledges_string_payload_only():
    state = {PERSISTENCE_WARNING_KEY: "old"}
    handle_storage_response(
        state,
        {"action": "save", "request_id": "save-x", "ok": True, "payload": 123},
    )
    assert PERSISTENCE_LAST_SYNC_KEY not in state
    assert state[PERSISTENCE_WARNING_KEY] == "old"

    payload = encode_personalisation({})
    handle_storage_response(
        state,
        {"action": "save", "request_id": "save-x", "ok": True, "payload": payload},
    )
    assert state[PERSISTENCE_LAST_SYNC_KEY] == payload
    assert PERSISTENCE_WARNING_KEY not in state


def test_handle_clear_acknowledgement_only_clears_storage_bookkeeping():
    personal = {"100001": PersonalSchoolState(SchoolDisposition.SHORTLISTED)}
    state = {
        PERSONAL_SCHOOLS_KEY: personal,
        PERSISTENCE_CLEAR_PENDING_KEY: True,
        PERSISTENCE_LAST_SYNC_KEY: "old",
        PERSISTENCE_WARNING_KEY: "old",
    }
    handle_storage_response(
        state,
        {"action": "clear", "request_id": "clear-v1", "ok": True, "payload": None},
    )
    assert state[PERSONAL_SCHOOLS_KEY] == personal
    assert PERSISTENCE_CLEAR_PENDING_KEY not in state
    assert PERSISTENCE_LAST_SYNC_KEY not in state
    assert PERSISTENCE_WARNING_KEY not in state
