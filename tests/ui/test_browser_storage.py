from __future__ import annotations

from types import SimpleNamespace

import pytest

from school_finder.ui import browser_storage
from school_finder.ui.personalisation_storage import StorageCommand


class FakeFactory:
    def __init__(self, response=None):
        self.response = response
        self.registrations = []
        self.mounts = []

    def component(self, **kwargs):
        self.registrations.append(kwargs)

        def renderer(**kwargs):
            self.mounts.append(kwargs)
            return SimpleNamespace(response=self.response)

        return renderer


def _fake_streamlit(factory):
    return SimpleNamespace(components=SimpleNamespace(v2=factory))


def test_component_registration_is_cached_for_same_streamlit_owner(monkeypatch):
    monkeypatch.setattr(browser_storage, "_component", None)
    monkeypatch.setattr(browser_storage, "_component_owner", None)
    factory = FakeFactory()
    fake = _fake_streamlit(factory)

    first = browser_storage._component_for(fake)
    second = browser_storage._component_for(fake)

    assert first is second
    assert len(factory.registrations) == 1
    assert factory.registrations[0]["name"] == "school_finder_personalisation_storage"
    assert "localStorage" in factory.registrations[0]["js"]


def test_component_registration_rejects_streamlit_without_components_v2(monkeypatch):
    monkeypatch.setattr(browser_storage, "_component", None)
    monkeypatch.setattr(browser_storage, "_component_owner", None)
    with pytest.raises(RuntimeError, match="1.51 or newer"):
        browser_storage._component_for(SimpleNamespace())


def test_run_storage_command_mounts_expected_payload_and_returns_mapping(monkeypatch):
    monkeypatch.setattr(browser_storage, "_component", None)
    monkeypatch.setattr(browser_storage, "_component_owner", None)
    response = {"action": "save", "request_id": "save-x", "ok": True}
    factory = FakeFactory(response)
    fake = _fake_streamlit(factory)
    command = StorageCommand("save", "save-x", '{"hello":"world"}')

    assert browser_storage.run_storage_command(fake, command) == response
    mount = factory.mounts[0]
    assert mount["data"] == {
        "action": "save",
        "request_id": "save-x",
        "payload": '{"hello":"world"}',
        "storage_key": "school-finder.personalisation.v1",
    }
    assert mount["default"] == {"response": None}
    assert callable(mount["on_response_change"])
    mount["on_response_change"]()
    assert mount["key"] == "school-finder-personalisation-storage"
    assert mount["height"] == 1


def test_run_storage_command_ignores_non_mapping_component_response(monkeypatch):
    monkeypatch.setattr(browser_storage, "_component", None)
    monkeypatch.setattr(browser_storage, "_component_owner", None)
    fake = _fake_streamlit(FakeFactory("not a mapping"))
    assert browser_storage.run_storage_command(fake, StorageCommand("load", "load-v1")) is None
