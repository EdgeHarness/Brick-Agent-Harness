import ast
import copy

import pytest

from bench import focused_recovery_release_verifier as verifier


def test_verifier_is_a_separate_read_only_implementation():
    tree = ast.parse(verifier.Path(verifier.__file__).read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "bench.focused_recovery_successor" not in imports
    assert "focused_recovery_successor" not in imports
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in {
            "build_release_archive", "validate_release_manifest", "analyze",
        }
        for node in ast.walk(tree)
    )


def test_independent_self_digest_rejects_tamper():
    document = {"schema_version": "fixture/1", "value": 1}
    document["fixture_sha256"] = verifier._digest(document)
    assert verifier._self_digest(document, "fixture_sha256", "fixture") == document["fixture_sha256"]
    forged = copy.deepcopy(document); forged["value"] = 2
    with pytest.raises(verifier.VerificationError, match="self-digest drifted"):
        verifier._self_digest(forged, "fixture_sha256", "fixture")


def test_private_complete_release_independently_rederives_when_present():
    if not verifier.AUTHORIZATION_PATH.with_name("authorization.json.complete").is_file():
        pytest.skip("private successor release is absent in clean CI")
    authorization = verifier._published(verifier.AUTHORIZATION_PATH, "authorization")
    head = verifier.subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=verifier.ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if head != authorization["commit_sha"]:
        pytest.skip("private successor release belongs to a different immutable checkout")
    status = verifier.subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=verifier.ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()
    if status:
        pytest.skip("private successor rederivation requires its clean immutable checkout")
    verification_path = (
        verifier.SUCCESSOR_ROOT / "release" / authorization["authorization_sha256"]
        / "independent-verification.json"
    )
    if not verification_path.is_file():
        pytest.skip("successor release has not reached independent verification")
    existing = verifier._published(verification_path, "verification")
    assert verifier.verify_release(existing["verified_at"]) == existing
