"""Session-state helpers for the Streamlit interface."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from dataclasses import replace
from typing import Any

from school_finder.models.personalisation import PersonalSchoolState, SchoolDisposition
from school_finder.models.search import SchoolSearchResult

LATEST_SEARCH_KEY = "school_finder.latest_search"
SELECTED_SCHOOL_URN_KEY = "school_finder.selected_school_urn"
COMPARE_URNS_KEY = "school_finder.compare_urns"
PERSONAL_SCHOOLS_KEY = "school_finder.personal_schools"
MAX_COMPARE_SCHOOLS = 4


def _required_urn(urn: str) -> str:
    selected = str(urn).strip()
    if not selected:
        raise ValueError("urn is required.")
    return selected


def get_personal_schools(
    state: MutableMapping[str, Any],
) -> dict[str, PersonalSchoolState]:
    """Return valid parent-specific school states, keyed by normalised URN."""
    value = state.get(PERSONAL_SCHOOLS_KEY, {})
    if not isinstance(value, Mapping):
        return {}
    personal: dict[str, PersonalSchoolState] = {}
    for urn, school_state in value.items():
        if not isinstance(urn, str) or not urn.strip():
            continue
        if isinstance(school_state, PersonalSchoolState):
            personal[urn.strip()] = school_state
    return personal


def get_personal_school(
    state: MutableMapping[str, Any], urn: str
) -> PersonalSchoolState:
    """Return parent-specific state for one school, defaulting to neutral."""
    selected = _required_urn(urn)
    return get_personal_schools(state).get(selected, PersonalSchoolState())


def _store_personal_school(
    state: MutableMapping[str, Any], urn: str, school_state: PersonalSchoolState
) -> PersonalSchoolState:
    personal = get_personal_schools(state)
    if school_state.is_default:
        personal.pop(urn, None)
    else:
        personal[urn] = school_state
    if personal:
        state[PERSONAL_SCHOOLS_KEY] = personal
    else:
        state.pop(PERSONAL_SCHOOLS_KEY, None)
    return school_state


def set_school_disposition(
    state: MutableMapping[str, Any],
    urn: str,
    disposition: SchoolDisposition | str,
) -> PersonalSchoolState:
    """Set whether a school is neutral, shortlisted, or not for this family."""
    selected = _required_urn(urn)
    resolved = (
        disposition
        if isinstance(disposition, SchoolDisposition)
        else SchoolDisposition(disposition)
    )
    current = get_personal_school(state, selected)
    return _store_personal_school(
        state, selected, replace(current, disposition=resolved)
    )


def set_school_rating(
    state: MutableMapping[str, Any], urn: str, rating: int | None
) -> PersonalSchoolState:
    """Set or clear a parent's 1-5 rating for a school."""
    selected = _required_urn(urn)
    current = get_personal_school(state, selected)
    return _store_personal_school(state, selected, replace(current, rating=rating))


def set_school_notes(
    state: MutableMapping[str, Any], urn: str, notes: str | None
) -> PersonalSchoolState:
    """Set or clear free-text notes for a school."""
    selected = _required_urn(urn)
    current = get_personal_school(state, selected)
    return _store_personal_school(state, selected, replace(current, notes=notes))


def clear_school_personalisation(state: MutableMapping[str, Any], urn: str) -> None:
    """Remove all parent-specific state for one school."""
    selected = _required_urn(urn)
    personal = get_personal_schools(state)
    personal.pop(selected, None)
    if personal:
        state[PERSONAL_SCHOOLS_KEY] = personal
    else:
        state.pop(PERSONAL_SCHOOLS_KEY, None)


def get_shortlisted_urns(state: MutableMapping[str, Any]) -> tuple[str, ...]:
    """Return URNs explicitly shortlisted by the parent."""
    return tuple(
        urn
        for urn, school_state in get_personal_schools(state).items()
        if school_state.disposition is SchoolDisposition.SHORTLISTED
    )


def get_rejected_urns(state: MutableMapping[str, Any]) -> tuple[str, ...]:
    """Return URNs explicitly marked as not for this family."""
    return tuple(
        urn
        for urn, school_state in get_personal_schools(state).items()
        if school_state.disposition is SchoolDisposition.NOT_FOR_US
    )


def get_latest_search(state: MutableMapping[str, Any]) -> SchoolSearchResult | None:
    """Return the most recent successful search stored for this session."""
    value = state.get(LATEST_SEARCH_KEY)
    return value if isinstance(value, SchoolSearchResult) else None



def get_compare_urns(state: MutableMapping[str, Any]) -> tuple[str, ...]:
    """Return valid school URNs selected for comparison, preserving order."""
    value = state.get(COMPARE_URNS_KEY, ())
    if not isinstance(value, (list, tuple)):
        return ()
    seen: set[str] = set()
    urns: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip() and item.strip() not in seen:
            urn = item.strip()
            seen.add(urn)
            urns.append(urn)
    return tuple(urns[:MAX_COMPARE_SCHOOLS])


def add_compare_school(state: MutableMapping[str, Any], urn: str) -> tuple[str, ...]:
    """Add a school to the comparison selection (maximum four)."""
    selected = _required_urn(urn)
    urns = list(get_compare_urns(state))
    if selected not in urns:
        if len(urns) >= MAX_COMPARE_SCHOOLS:
            raise ValueError(f"You can compare up to {MAX_COMPARE_SCHOOLS} schools.")
        urns.append(selected)
    state[COMPARE_URNS_KEY] = urns
    return tuple(urns)


def remove_compare_school(state: MutableMapping[str, Any], urn: str) -> tuple[str, ...]:
    """Remove a school from the comparison selection."""
    selected = str(urn).strip()
    urns = [value for value in get_compare_urns(state) if value != selected]
    if urns:
        state[COMPARE_URNS_KEY] = urns
    else:
        state.pop(COMPARE_URNS_KEY, None)
    return tuple(urns)


def clear_compare_schools(state: MutableMapping[str, Any]) -> None:
    """Clear all comparison selections."""
    state.pop(COMPARE_URNS_KEY, None)


def get_selected_school_urn(state: MutableMapping[str, Any]) -> str | None:
    """Return the school URN selected for the detail view."""
    value = state.get(SELECTED_SCHOOL_URN_KEY)
    return value if isinstance(value, str) and value.strip() else None


def select_school(state: MutableMapping[str, Any], urn: str) -> str:
    """Select a school for inspection in the detail view."""
    selected = _required_urn(urn)
    state[SELECTED_SCHOOL_URN_KEY] = selected
    return selected


def clear_selected_school(state: MutableMapping[str, Any]) -> None:
    """Clear the current detail-page selection."""
    state.pop(SELECTED_SCHOOL_URN_KEY, None)


def set_latest_search(
    state: MutableMapping[str, Any], result: SchoolSearchResult
) -> SchoolSearchResult:
    """Persist a successful search result and keep only a still-valid school selection."""
    state[LATEST_SEARCH_KEY] = result
    valid_urns = {school.identity.urn for school in result.schools}
    selected = get_selected_school_urn(state)
    if selected and selected not in valid_urns:
        clear_selected_school(state)
    compare = [urn for urn in get_compare_urns(state) if urn in valid_urns]
    if compare:
        state[COMPARE_URNS_KEY] = compare
    else:
        clear_compare_schools(state)
    return result


def clear_latest_search(state: MutableMapping[str, Any]) -> None:
    """Remove any stored search result and selected school from the current session."""
    state.pop(LATEST_SEARCH_KEY, None)
    clear_selected_school(state)
    clear_compare_schools(state)
