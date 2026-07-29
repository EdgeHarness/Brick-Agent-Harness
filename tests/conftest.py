"""Shared offline fixtures for the characterization suite."""

import urllib.request

import pytest
import requests

from harness.memory import MemoryStore
from harness.world import World


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch):
    """A unit test must fail rather than silently reaching Ollama or the web."""

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in the offline test suite")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


@pytest.fixture
def world_and_memory(tmp_path):
    workdir = tmp_path / "episode"
    world = World(str(workdir))
    memory = MemoryStore(str(tmp_path / "memory" / "memory.jsonl"))
    return world, memory
