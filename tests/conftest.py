"""Shared offline fixtures for the characterization suite."""

import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

import pytest
import requests

from harness.domain import load_domain
from harness.memory import MemoryStore
from harness.runtime import AttemptContext, RunConfig, RunHooks


# --- S4 deterministic Windows path contract --------------------------------
#
# Windows fails `CreateDirectoryW` at MAX_PATH - 12 = 248, not 260, because it
# reserves twelve characters for an 8.3 name inside the new directory. A
# directory junction is created through that API, so the S4 layout -- a 64-hex
# logical hash plus a 36-character physical UUID, 156 characters before any
# test root -- sits close to the limit.
#
# Under pytest's default root (~98 characters here) the worst case reaches 254
# and the junction case fails with WinError 206. That failure is not constant:
# it moves with the pytest counter (`pytest-99` -> `pytest-100` adds a
# character) and with the operator's user name, so the S4 gate could silently
# pass or fail depending on how often the suite had been run. A release gate
# must not depend on either. The root is therefore bounded explicitly and the
# bound is asserted, so a regression fails loudly at setup instead of
# reappearing as an intermittent gate result.
#
# Long-path support is deliberately NOT relied upon: this host has
# LongPathsEnabled=0, and the S4 exit gate must hold on a default Windows
# configuration, since validating Windows filesystem behaviour is its purpose.
WINDOWS_DIRECTORY_PATH_LIMIT = 248
S4_PATH_MARGIN = 32
S4_MAX_WORST_PATH = WINDOWS_DIRECTORY_PATH_LIMIT - S4_PATH_MARGIN

# The deepest path any S4 test creates below its root. Derived from the longest
# run id and the longest artifact leaf actually used by the S4 suite rather
# than assumed, and asserted against the real modules by
# tests/test_s4_path_contract.py.
S4_LONGEST_RUN_ID = "s4-platform-test"
S4_LONGEST_ARTIFACT_LEAF = "reparse-link"
S4_PLATFORM_ROOT_ENV = "BRICK_S4_PLATFORM_ROOT"


def s4_worst_suffix_length(
    run_id=S4_LONGEST_RUN_ID, leaf=S4_LONGEST_ARTIFACT_LEAF
):
    """Length of the deepest path an S4 test creates below its root."""
    return len(
        "\\runs\\{run}\\attempts\\{logical}\\{physical}\\artifacts\\{leaf}".format(
            run=run_id,
            logical="a" * 64,
            physical="b" * 36,
            leaf=leaf,
        )
    )


S4_MAX_ROOT_LENGTH = S4_MAX_WORST_PATH - s4_worst_suffix_length()


def s4_root_is_within_budget(root):
    return len(str(root)) <= S4_MAX_ROOT_LENGTH


@pytest.fixture
def s4_bounded_root(tmp_path):
    """A test root short enough that the deepest S4 path stays under 248.

    POSIX keeps pytest's `tmp_path`: it has no MAX_PATH equivalent. On Windows
    the canonical native attestor supplies an already-bounded root through
    ``BRICK_S4_PLATFORM_ROOT``; an ordinary run allocates one directly under the
    temp directory instead of beneath pytest's deep per-test path.
    """
    if os.name != "nt":
        yield tmp_path
        return

    supplied = os.environ.get(S4_PLATFORM_ROOT_ENV)
    if supplied:
        base = Path(supplied)
        if not base.is_absolute():
            raise AssertionError(
                "{} must be absolute, got {!r}".format(
                    S4_PLATFORM_ROOT_ENV, supplied
                )
            )
        base.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="", dir=str(base)))
    else:
        root = Path(tempfile.mkdtemp(prefix="s4p-"))

    if not s4_root_is_within_budget(root):
        shutil.rmtree(root, ignore_errors=True)
        raise AssertionError(
            "S4 test root is too long for the Windows directory limit: "
            "{} characters, maximum {}. The deepest S4 path adds {} "
            "characters and must stay at or below {} of the {} limit.".format(
                len(str(root)),
                S4_MAX_ROOT_LENGTH,
                s4_worst_suffix_length(),
                S4_MAX_WORST_PATH,
                WINDOWS_DIRECTORY_PATH_LIMIT,
            )
        )

    try:
        yield root
    finally:
        # Strict: a cleanup failure fails teardown rather than being swallowed,
        # so a leaked handle or an undeleted reparse point is visible.
        shutil.rmtree(root)


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
        guards=False,
        profile=None,
        verifier_rounds=2,
        runtime_protocol="legacy",
        task_id=None,
        completion_checker=None,
        cancel_check=None,
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
                guards=guards,
                verifier_rounds=verifier_rounds,
                runtime_protocol=runtime_protocol,
                **({"profile": profile} if profile is not None else {}),
            ),
            domain=domain,
            tools=domain.registry,
            policy=domain.default_policy,
            world=world,
            memory=memory,
            workdir=workdir,
            artifact_dir=workdir / "files",
            hooks=hooks or RunHooks(),
            authoritative_task_id=task_id,
            completion_checker=completion_checker,
            cancel_check=cancel_check,
        )

    return make
