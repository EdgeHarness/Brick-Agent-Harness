"""Which process is answering on 11434, and which machine we are on.

The harness never chooses a backend. It posts to a fixed local port and
whatever is listening decides what actually runs. That is deliberate and it is
what lets the NPU and llama.cpp shims work without a line of harness code.

It is also how a run silently becomes a different experiment. Both shims bind
the same port as Ollama, and the NPU one replaces the requested model tag with
whatever GenieX has loaded and then reports that model under the requested
alias, so `/api/tags` looks right and every number afterwards is about a model
nobody asked for. Nothing in the loop cross-checks this. A shim left running
from an earlier session is not a hypothetical: it is the default outcome of
closing a terminal.

Both shims answer `/api/version` with their own name, so the fingerprint is
free. Take it, and write it down. Hard rule 3 asks every live run to record
its host; this is the other half of the same question, because "which machine"
and "which process served the tokens" are only useful together.
"""
import json
import platform
import socket
import urllib.error
import urllib.request

from .llm import OLLAMA_URL

# What each shim calls itself at /api/version. Real Ollama answers a semver,
# so anything not in this table and not empty is taken to be Ollama itself.
_SHIM_VERSIONS = {
    "npu-shim": "npu",
    "llama.cpp-shim": "llamacpp",
}

# The NPU shim serves a Snapdragon Copilot+ machine through GenieX, which
# means Windows on ARM64 and nothing else. Both halves matter: an Apple
# Silicon Mac also reports arm64, so testing the architecture alone would let
# the one host this check exists to catch pass straight through.
def _is_npu_host(where):
    return (where["system"] == "Windows"
            and where["machine"].lower() in ("arm64", "aarch64"))


def identify(url=None, timeout=2.0):
    """What is listening. Never raises; unreachable is an answer, not an error.

    A probe that can crash the run is worse than the confusion it prevents,
    and this one runs before every live run.
    """
    url = url or OLLAMA_URL
    try:
        with urllib.request.urlopen(f"{url}/api/version", timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
    except Exception:
        # Deliberately everything. This runs before every live run and its
        # only job is to answer a question; a probe that can end the run is
        # worse than not knowing. It is also not the swallow that _verify
        # used to do: that one turned a failure into a claimed success,
        # while this one records "unreachable", which is the truth and is
        # visible in the evidence. The offline test suite blocks the network
        # outright, and answering "unreachable" there is correct.
        return {"backend": "unreachable", "version": None}
    version = str(body.get("version") or "")
    return {"backend": _SHIM_VERSIONS.get(version, "ollama" if version else "unknown"),
            "version": version or None}


def host():
    """The machine, in the terms the evidence needs to tell two runs apart."""
    return {
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def stamp(url=None, timeout=2.0):
    """Host and backend together, for a run record.

    `warning` is populated rather than raised. Refusing to run would turn a
    development session on the wrong backend into no session at all, and the
    thing that actually protects a claim is the recorded fact, not a
    gatekeeper the operator learns to work around.
    """
    where = host()
    what = identify(url, timeout)
    record = {"host": where, "backend": what, "warning": None}
    if what["backend"] == "npu":
        # On a Snapdragon Copilot+ box the NPU shim is the intended backend
        # and says nothing. Anywhere else it is a leftover or a mistake, and
        # every number after it is about a model nobody asked for.
        if not _is_npu_host(where):
            record["warning"] = (
                f"the NPU shim is answering on {where['system']} "
                f"{where['machine']}, which is not a Snapdragon Copilot+ host. "
                "This run is not measuring what it claims to measure."
            )
    elif what["backend"] == "llamacpp":
        record["warning"] = (
            "a llamacpp shim is serving this run, not Ollama. If that was not "
            "deliberate, stop it and the port returns to Ollama."
        )
    return record
