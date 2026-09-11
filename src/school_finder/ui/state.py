"""Session-state helpers for the Streamlit interface."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from school_finder.models.search import SchoolSearchResult

LATEST_SEARCH_KEY = "school_finder.latest_search"


def get_latest_search(state: MutableMapping[str, Any]) -> SchoolSearchResult | None:
    """Return the most recent successful search stored for this session."""
    value = state.get(LATEST_SEARCH_KEY)
    return value if isinstance(value, SchoolSearchResult) else None


def set_latest_search(
    state: MutableMapping[str, Any], result: SchoolSearchResult
) -> SchoolSearchResult:
    """Persist a successful search result and return it for convenient chaining."""
    state[LATEST_SEARCH_KEY] = result
    return result


def clear_latest_search(state: MutableMapping[str, Any]) -> None:
    """Remove any stored search result from the current session."""
    state.pop(LATEST_SEARCH_KEY, None)
