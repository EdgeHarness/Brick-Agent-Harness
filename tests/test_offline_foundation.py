import pathlib
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
    assert project["version"] == "0.3.0"
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
        ".gguf",
        ".safetensors",
        ".onnx",
        ".bin",
        ".ckpt",
        ".pt",
        ".pth",
    )

    offenders = [
        path
        for path in tracked
        if path == ".env"
        or (path.startswith(".env.") and path != ".env.example")
        or path.startswith(runtime_prefixes)
        or any(segment in f"/{path}" for segment in runtime_segments)
        or path.endswith(sensitive_suffixes)
    ]
    assert offenders == []
