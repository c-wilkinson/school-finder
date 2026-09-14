"""Tiny Streamlit Components v2 bridge for browser localStorage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from school_finder.ui.personalisation_storage import BROWSER_STORAGE_KEY, StorageCommand

_COMPONENT_JS = r"""
export default function(component) {
  const { data, parentElement, setStateValue } = component;
  if (parentElement.__schoolFinderStorageRequest === data.request_id) {
    return;
  }
  parentElement.__schoolFinderStorageRequest = data.request_id;

  const respond = (response) => setStateValue("response", response);
  try {
    if (data.action === "load") {
      respond({
        action: data.action,
        request_id: data.request_id,
        ok: true,
        payload: window.localStorage.getItem(data.storage_key),
      });
      return;
    }
    if (data.action === "save") {
      window.localStorage.setItem(data.storage_key, data.payload);
      respond({
        action: data.action,
        request_id: data.request_id,
        ok: true,
        payload: data.payload,
      });
      return;
    }
    if (data.action === "clear") {
      window.localStorage.removeItem(data.storage_key);
      respond({
        action: data.action,
        request_id: data.request_id,
        ok: true,
        payload: null,
      });
    }
  } catch (error) {
    respond({
      action: data.action,
      request_id: data.request_id,
      ok: false,
      error: String(error),
      payload: null,
    });
  }
}
"""

_component = None
_component_owner = None


def _component_for(st_module):
    """Register the inline component once for a given Streamlit module/test double."""
    global _component, _component_owner
    if _component is not None and _component_owner is st_module:
        return _component
    components = getattr(st_module, "components", None)
    v2 = getattr(components, "v2", None)
    factory = getattr(v2, "component", None)
    if factory is None:
        raise RuntimeError(
            "Remembering schools on this device requires Streamlit 1.51 or newer."
        )
    _component = factory(
        name="school_finder_personalisation_storage",
        js=_COMPONENT_JS,
    )
    _component_owner = st_module
    return _component


def run_storage_command(st_module, command: StorageCommand) -> Mapping[str, Any] | None:
    """Mount the browser-storage bridge and return its latest response."""
    component = _component_for(st_module)
    result = component(
        data={
            "action": command.action,
            "request_id": command.request_id,
            "payload": command.payload,
            "storage_key": BROWSER_STORAGE_KEY,
        },
        default={"response": None},
        on_response_change=lambda: None,
        key="school-finder-personalisation-storage",
        height=1,
    )
    response = getattr(result, "response", None)
    return response if isinstance(response, Mapping) else None
