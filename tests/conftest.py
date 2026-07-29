"""Shared offline fixtures for the characterization suite."""

import urllib.request
from pathlib import Path

import pytest
import requests

from harness.domain import load_domain
from harness.memory import MemoryStore
from harness.runtime import AttemptContext, RunConfig, RunHooks


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch):
    """A unit test must fail rather than silently reaching Ollama or the web."""

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in the offline test suite")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


@pytest.fixture
def attempt_factory(tmp_path):
    counter = {"value": 0}

    def make(
        *,
        domain_name="office_demo",
        condition="harness",
        max_calls=14,
        hooks=None,
    ):
        counter["value"] += 1
        domain = load_domain(domain_name)
        workdir = Path(
            tmp_path, f"{domain_name}-{counter['value']}"
        )
        world = domain.make_world(workdir)
        memory = MemoryStore(
            str(tmp_path / f"memory-{counter['value']}.jsonl")
        )
        return AttemptContext(
            attempt_id=f"test-{counter['value']}",
            config=RunConfig(
                condition=condition,
                max_calls=max_calls,
                today=domain.default_today,
            ),
            domain=domain,
            tools=domain.registry,
            policy=domain.default_policy,
            world=world,
            memory=memory,
            workdir=workdir,
            artifact_dir=workdir / "files",
            hooks=hooks or RunHooks(),
        )

    return make
