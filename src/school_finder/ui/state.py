"""Session-state helpers for the Streamlit interface."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from school_finder.models.search import SchoolSearchResult

LATEST_SEARCH_KEY = "school_finder.latest_search"
SELECTED_SCHOOL_URN_KEY = "school_finder.selected_school_urn"


def get_latest_search(state: MutableMapping[str, Any]) -> SchoolSearchResult | None:
    """Return the most recent successful search stored for this session."""
    value = state.get(LATEST_SEARCH_KEY)
    return value if isinstance(value, SchoolSearchResult) else None


def get_selected_school_urn(state: MutableMapping[str, Any]) -> str | None:
    """Return the school URN selected for the detail view."""
    value = state.get(SELECTED_SCHOOL_URN_KEY)
    return value if isinstance(value, str) and value.strip() else None


def select_school(state: MutableMapping[str, Any], urn: str) -> str:
    """Select a school for inspection in the detail view."""
    selected = str(urn).strip()
    if not selected:
        raise ValueError("urn is required.")
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
    selected = get_selected_school_urn(state)
    if selected and not any(school.identity.urn == selected for school in result.schools):
        clear_selected_school(state)
    return result


def clear_latest_search(state: MutableMapping[str, Any]) -> None:
    """Remove any stored search result and selected school from the current session."""
    state.pop(LATEST_SEARCH_KEY, None)
    clear_selected_school(state)
