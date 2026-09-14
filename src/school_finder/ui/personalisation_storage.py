"""Browser-persistence helpers for parent-specific school state."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Literal

from school_finder.models.personalisation import PersonalSchoolState, SchoolDisposition
from school_finder.ui.state import PERSONAL_SCHOOLS_KEY, get_personal_schools

STORAGE_SCHEMA_VERSION = 1
BROWSER_STORAGE_KEY = "school-finder.personalisation.v1"
PERSISTENCE_ENABLED_KEY = "school_finder.personal_storage_enabled"
PERSISTENCE_HYDRATED_KEY = "school_finder.personal_storage_hydrated"
PERSISTENCE_LAST_SYNC_KEY = "school_finder.personal_storage_last_sync"
PERSISTENCE_CLEAR_PENDING_KEY = "school_finder.personal_storage_clear_pending"
PERSISTENCE_WARNING_KEY = "school_finder.personal_storage_warning"

StorageAction = Literal["load", "save", "clear"]


@dataclass(frozen=True, slots=True)
class StorageCommand:
    """One browser-storage operation requested by the Python app."""

    action: StorageAction
    request_id: str
    payload: str | None = None


def encode_personalisation(personal: Mapping[str, PersonalSchoolState]) -> str:
    """Serialise personal school state into the stable browser-storage schema."""
    schools = {
        urn: {
            "disposition": school_state.disposition.value,
            "rating": school_state.rating,
            "notes": school_state.notes,
        }
        for urn, school_state in sorted(personal.items())
    }
    return json.dumps(
        {"schema_version": STORAGE_SCHEMA_VERSION, "schools": schools},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def decode_personalisation(payload: str) -> dict[str, PersonalSchoolState]:
    """Decode and validate a browser-storage payload."""
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("Saved personalisation is empty.")
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Saved personalisation is not valid JSON.") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError("Saved personalisation must be an object.")
    if decoded.get("schema_version") != STORAGE_SCHEMA_VERSION:
        raise ValueError("Saved personalisation uses an unsupported schema version.")
    raw_schools = decoded.get("schools")
    if not isinstance(raw_schools, Mapping):
        raise ValueError("Saved personalisation does not contain a schools object.")

    schools: dict[str, PersonalSchoolState] = {}
    for raw_urn, raw_state in raw_schools.items():
        if not isinstance(raw_urn, str) or not raw_urn.strip():
            continue
        if not isinstance(raw_state, Mapping):
            continue
        try:
            disposition = SchoolDisposition(raw_state.get("disposition", "neutral"))
            rating = raw_state.get("rating")
            notes = raw_state.get("notes")
            if notes is not None and not isinstance(notes, str):
                continue
            school_state = PersonalSchoolState(
                disposition=disposition,
                rating=rating,
                notes=notes,
            )
        except (TypeError, ValueError):
            continue
        if not school_state.is_default:
            schools[raw_urn.strip()] = school_state
    return schools


def is_persistence_hydrated(state: MutableMapping[str, Any]) -> bool:
    """Return whether this Streamlit session has checked browser storage."""
    return state.get(PERSISTENCE_HYDRATED_KEY) is True


def is_persistence_enabled(state: MutableMapping[str, Any]) -> bool:
    """Return whether the user opted to persist personalisation in this browser."""
    return state.get(PERSISTENCE_ENABLED_KEY) is True


def persistence_warning(state: MutableMapping[str, Any]) -> str | None:
    """Return the latest non-fatal browser-storage warning, if any."""
    value = state.get(PERSISTENCE_WARNING_KEY)
    return value if isinstance(value, str) and value else None


def enable_persistence(state: MutableMapping[str, Any]) -> None:
    """Opt in to browser persistence for the current personal school state."""
    state[PERSISTENCE_ENABLED_KEY] = True
    state[PERSISTENCE_HYDRATED_KEY] = True
    state.pop(PERSISTENCE_WARNING_KEY, None)
    state.pop(PERSISTENCE_LAST_SYNC_KEY, None)


def forget_persistence(state: MutableMapping[str, Any]) -> None:
    """Request deletion of saved browser data without clearing the live session."""
    state[PERSISTENCE_ENABLED_KEY] = False
    state[PERSISTENCE_HYDRATED_KEY] = True
    state[PERSISTENCE_CLEAR_PENDING_KEY] = True
    state.pop(PERSISTENCE_LAST_SYNC_KEY, None)
    state.pop(PERSISTENCE_WARNING_KEY, None)


def _save_command(payload: str) -> StorageCommand:
    digest = sha256(payload.encode("utf-8")).hexdigest()[:20]
    return StorageCommand("save", f"save-{digest}", payload)


def next_storage_command(state: MutableMapping[str, Any]) -> StorageCommand | None:
    """Return the next browser-storage operation required by this session."""
    if not is_persistence_hydrated(state):
        return StorageCommand("load", "load-v1")
    if state.get(PERSISTENCE_CLEAR_PENDING_KEY) is True:
        return StorageCommand("clear", "clear-v1")
    if not is_persistence_enabled(state):
        return None

    payload = encode_personalisation(get_personal_schools(state))
    if payload == state.get(PERSISTENCE_LAST_SYNC_KEY):
        return None
    return _save_command(payload)


def is_persistence_synced(state: MutableMapping[str, Any]) -> bool:
    """Return whether enabled persistence reflects the current session state."""
    if not is_persistence_enabled(state) or not is_persistence_hydrated(state):
        return False
    current = encode_personalisation(get_personal_schools(state))
    return current == state.get(PERSISTENCE_LAST_SYNC_KEY)


def _set_storage_error(state: MutableMapping[str, Any], action: str) -> None:
    if action == "load":
        message = "Saved schools could not be read from this browser. This session will continue without restoring them."
    elif action == "clear":
        message = "Saved schools could not be removed from this browser. You may need to clear this site's browser storage manually."
    else:
        message = "Your schools could not be saved in this browser. Personalisation will remain available for this session only."
    state[PERSISTENCE_WARNING_KEY] = message
    state[PERSISTENCE_HYDRATED_KEY] = True
    state[PERSISTENCE_ENABLED_KEY] = False
    state.pop(PERSISTENCE_CLEAR_PENDING_KEY, None)
    state.pop(PERSISTENCE_LAST_SYNC_KEY, None)


def handle_storage_response(
    state: MutableMapping[str, Any], response: Mapping[str, Any] | None
) -> None:
    """Apply one response from the browser-storage component to session state."""
    if not isinstance(response, Mapping):
        return
    action = response.get("action")
    request_id = response.get("request_id")
    if action not in {"load", "save", "clear"} or not isinstance(request_id, str):
        return
    if response.get("ok") is not True:
        _set_storage_error(state, action)
        return

    if action == "load":
        if is_persistence_hydrated(state):
            return
        payload = response.get("payload")
        if payload is None:
            state[PERSISTENCE_HYDRATED_KEY] = True
            state[PERSISTENCE_ENABLED_KEY] = False
            state.pop(PERSISTENCE_LAST_SYNC_KEY, None)
            return
        if not isinstance(payload, str):
            _set_storage_error(state, action)
            return
        try:
            schools = decode_personalisation(payload)
        except ValueError:
            _set_storage_error(state, action)
            return
        if schools:
            state[PERSONAL_SCHOOLS_KEY] = schools
        else:
            state.pop(PERSONAL_SCHOOLS_KEY, None)
        canonical = encode_personalisation(schools)
        state[PERSISTENCE_HYDRATED_KEY] = True
        state[PERSISTENCE_ENABLED_KEY] = True
        state[PERSISTENCE_LAST_SYNC_KEY] = canonical
        state.pop(PERSISTENCE_WARNING_KEY, None)
        return

    if action == "save":
        payload = response.get("payload")
        if isinstance(payload, str):
            state[PERSISTENCE_LAST_SYNC_KEY] = payload
            state.pop(PERSISTENCE_WARNING_KEY, None)
        return

    state.pop(PERSISTENCE_CLEAR_PENDING_KEY, None)
    state.pop(PERSISTENCE_LAST_SYNC_KEY, None)
    state.pop(PERSISTENCE_WARNING_KEY, None)
