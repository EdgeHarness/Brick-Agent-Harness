"""Which process served the tokens, and on which machine.

The harness posts to a fixed local port and whatever is listening decides what
runs. Both alternate backends bind that same port, and the NPU shim rewrites
the model tag to whatever it has loaded, so a shim left running from an
earlier session turns every later run into a different experiment with no
outward sign. These tests pin the fingerprint that notices.
"""
import json

import pytest

from harness import backend


class FakeResponse:
    def __init__(self, body):
        self._body = body.encode("utf-8") if isinstance(body, str) else body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def answering(body):
    def opener(url, timeout=None):
        return FakeResponse(body)
    return opener


def refusing(error):
    def opener(url, timeout=None):
        raise error
    return opener


# ------------------------------------------------------------ the fingerprint --

def test_real_ollama_is_recognised_by_its_semver(monkeypatch):
    monkeypatch.setattr(backend.urllib.request, "urlopen",
                        answering('{"version": "0.32.5"}'))
    assert backend.identify() == {"backend": "ollama", "version": "0.32.5"}


def test_the_npu_shim_names_itself(monkeypatch):
    monkeypatch.setattr(backend.urllib.request, "urlopen",
                        answering('{"version": "npu-shim"}'))
    assert backend.identify()["backend"] == "npu"


def test_the_llamacpp_shim_names_itself(monkeypatch):
    monkeypatch.setattr(backend.urllib.request, "urlopen",
                        answering('{"version": "llama.cpp-shim"}'))
    assert backend.identify()["backend"] == "llamacpp"


# ------------------------------------------------- it must never raise --

@pytest.mark.parametrize("error", [
    OSError("connection refused"),
    ValueError("not json"),
])
def test_a_failing_probe_answers_unreachable_rather_than_raising(monkeypatch,
                                                                 error):
    """This runs before every live run. A probe that crashes is worse than
    the confusion it exists to prevent."""
    monkeypatch.setattr(backend.urllib.request, "urlopen", refusing(error))
    assert backend.identify() == {"backend": "unreachable", "version": None}


def test_a_body_that_is_not_json_does_not_raise(monkeypatch):
    monkeypatch.setattr(backend.urllib.request, "urlopen",
                        answering("<html>nope</html>"))
    assert backend.identify()["backend"] == "unreachable"


def test_an_empty_version_is_unknown_not_ollama(monkeypatch):
    monkeypatch.setattr(backend.urllib.request, "urlopen", answering('{}'))
    assert backend.identify()["backend"] == "unknown"


# ------------------------------------------------------------- the warning --

def _on(monkeypatch, system, machine, version):
    monkeypatch.setattr(backend, "host", lambda: {
        "hostname": "test", "system": system, "release": "1",
        "machine": machine, "python": "3.12.0",
    })
    monkeypatch.setattr(backend.urllib.request, "urlopen",
                        answering(json.dumps({"version": version})))


def test_the_npu_shim_on_a_mac_is_flagged(monkeypatch):
    """An Apple Silicon Mac also reports arm64, so checking the architecture
    alone would let the one host this exists to catch pass straight through."""
    _on(monkeypatch, "Darwin", "arm64", "npu-shim")
    warning = backend.stamp()["warning"]
    assert warning is not None
    assert "Darwin arm64" in warning
    assert "Snapdragon" in warning


def test_the_npu_shim_on_an_intel_windows_box_is_flagged(monkeypatch):
    _on(monkeypatch, "Windows", "AMD64", "npu-shim")
    assert "Snapdragon" in backend.stamp()["warning"]


def test_the_npu_shim_on_windows_arm64_is_where_it_belongs(monkeypatch):
    _on(monkeypatch, "Windows", "ARM64", "npu-shim")
    assert backend.stamp()["warning"] is None


def test_a_llamacpp_shim_anywhere_is_worth_saying_out_loud(monkeypatch):
    _on(monkeypatch, "Darwin", "arm64", "llama.cpp-shim")
    assert "llamacpp shim is serving this run" in backend.stamp()["warning"]


def test_plain_ollama_warns_about_nothing(monkeypatch):
    _on(monkeypatch, "Darwin", "arm64", "0.32.5")
    assert backend.stamp()["warning"] is None


# ------------------------------------------------------------ the host --

def test_the_host_record_carries_what_tells_two_runs_apart():
    where = backend.host()
    assert set(where) == {"hostname", "system", "release", "machine", "python"}
    assert all(isinstance(v, str) and v for v in where.values())


def test_a_stamp_is_json_serialisable_because_it_goes_into_evidence(monkeypatch):
    _on(monkeypatch, "Darwin", "arm64", "0.32.5")
    json.dumps(backend.stamp())


def test_the_probe_survives_the_offline_suites_own_network_block():
    """The autouse conftest fixture replaces urlopen with something that
    raises AssertionError. A probe that ran before every live run and could
    not survive that would fail the whole suite rather than answer.

    This is not the swallow the verifier used to do. That one turned a
    failure into a claimed success; this one records "unreachable", which is
    both true here and visible in the evidence.
    """
    assert backend.identify() == {"backend": "unreachable", "version": None}


def test_an_unreachable_backend_still_produces_a_usable_stamp():
    record = backend.stamp()
    assert record["backend"]["backend"] == "unreachable"
    assert record["host"]["hostname"]
    assert record["warning"] is None
    json.dumps(record)
