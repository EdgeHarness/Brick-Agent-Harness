import pathlib
import re
import subprocess

import pytest
import requests


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 and 3.10 use the locked backport.
    import tomli as tomllib


def test_network_guard_blocks_http_requests():
    with pytest.raises(
        AssertionError,
        match="network access is forbidden in the offline test suite",
    ):
        requests.get("http://127.0.0.1:11434/api/tags")


def test_pep621_metadata_matches_the_locked_direct_dependencies():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]

    runtime_dependencies = [
        "requests==2.32.3",
        "openpyxl==3.1.5",
        "python-pptx==1.0.2",
    ]
    test_dependencies = ["pytest==8.3.5"]
    assert project["name"] == "brick-agent-harness"
    # The version is asserted as well-formed rather than pinned to a literal.
    # The release procedure permits bumping this scalar between the tested
    # candidate C and its metadata-only descendant R, and the behavior-tree
    # digest normalizes the version line so that bump is digest-neutral. A
    # literal pin here would make that permitted change impossible without
    # editing a test, which would alter the digest and void the F0 evidence.
    # Release identity is governed by the annotated tag, CHANGELOG.md and the
    # C..R diff review, not by this assertion.
    assert re.fullmatch(r"\d+\.\d+\.\d+", project["version"])
    assert project["requires-python"] == ">=3.9,<3.14"
    assert project["dependencies"] == runtime_dependencies
    assert project["optional-dependencies"]["test"] == test_dependencies

    direct_requirements = {
        line
        for line in (PROJECT_ROOT / "requirements.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }
    locked_requirements = {
        line
        for line in (PROJECT_ROOT / "requirements-lock.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }
    test_entrypoint = {
        line
        for line in (PROJECT_ROOT / "requirements-test.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }
    assert direct_requirements == set(runtime_dependencies)
    assert set(runtime_dependencies + test_dependencies) <= locked_requirements
    assert test_entrypoint == {"-r requirements-lock.txt"}


def test_sensitive_and_runtime_artifacts_are_not_tracked():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = [path for path in result.stdout.split("\0") if path]

    runtime_prefixes = (
        ".claude/",
        "private/",
        "results/",
        "results_smoke/",
        "results-dev",
        "finetune/data/",
        "training_scripts/data/",
        "training_scripts/assets/",
        "training_scripts/out/",
        "finetune/out/",
        "models/",
        "checkpoints/",
    )
    runtime_segments = ("/memory/", "/workspace/", "/logs/")
    sensitive_suffixes = (
        ".private.md",
        ".pem",
        ".key",
        ".p12",
        ".pfx",
        ".gguf",
        ".safetensors",
        ".onnx",
        ".bin",
        ".ckpt",
        ".pt",
        ".pth",
    )

    offenders = []
    for path in tracked:
        folded_path = path.casefold()
        filename = pathlib.PurePosixPath(folded_path).name
        if (
            filename == "brix.md"
            or filename == ".env"
            or (
                filename.startswith(".env.")
                and filename != ".env.example"
            )
            or folded_path.startswith(runtime_prefixes)
            or any(
                segment in f"/{folded_path}"
                for segment in runtime_segments
            )
            or "/runtime/" in f"/{folded_path}"
            or folded_path.endswith(sensitive_suffixes)
        ):
            offenders.append(path)
    assert offenders == []
    # This is deliberately a narrow high-confidence credential scan, not a
    # substitute for publication review or a dedicated secret-scanning tool.
    credential_patterns = (
        re.compile(
            rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
        re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
        re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
        re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
        re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),
    )
    content_offenders = []
    for relative in tracked:
        candidate = PROJECT_ROOT / relative
        # A deletion in the working tree is absent from the next commit even
        # though it remains in the index until staging. Do not make the
        # publication scan itself prevent removal of an unsafe tracked file.
        if not candidate.exists() and not candidate.is_symlink():
            continue
        blob = (
            str(candidate.readlink()).encode("utf-8")
            if candidate.is_symlink()
            else candidate.read_bytes()
        )
        if b"\0" in blob:
            continue
        if any(pattern.search(blob) for pattern in credential_patterns):
            content_offenders.append(relative)
    assert content_offenders == []


def test_retained_json_is_lf_pinned_and_contains_no_carriage_returns():
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "evidence/**/*.json text eol=lf" in attributes
    retained = sorted((PROJECT_ROOT / "evidence").glob("**/*.json"))
    assert retained
    for path in retained:
        assert b"\r" not in path.read_bytes(), path


def test_public_launchers_do_not_embed_the_original_machine_path():
    launchers = [
        PROJECT_ROOT / "Agent Lab.bat",
        *(PROJECT_ROOT / "agents").glob("*/run.ps1"),
    ]
    assert launchers
    for launcher in launchers:
        source = launcher.read_text(encoding="utf-8")
        assert r"C:\Users\Lab User" not in source
        assert "run_agent.py" in source or "webui.server" in source
