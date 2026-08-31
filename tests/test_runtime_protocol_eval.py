import json

import pytest

from evals.runtime_protocol import run_eval


def test_runtime_protocol_acceptance_is_deterministic_and_passes(
    tmp_path, monkeypatch
):
    first = run_eval.evaluate()
    second = run_eval.evaluate()
    assert first == second
    assert first["promotion_pass"] is True
    assert first["summary"] == {
        "acceptance_cases": 4,
        "legacy_false_completions": 2,
        "receipt_false_completions": 0,
        "legacy_unverified_completions": 1,
        "receipt_unverified_completions": 0,
        "valid_success_regressions": 0,
    }

    output = tmp_path / "report.json"
    run_eval.write_report(first, output)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded == first
    assert len(loaded["report_digest"]) == 64
    assert run_eval.validate_report(loaded)

    # The report is stored inside a later commit, so its generation-time HEAD
    # cannot equal that containing commit without a hash cycle. File digests,
    # not current HEAD equality, are the executable source boundary.
    monkeypatch.setattr(run_eval, "_git_head", lambda _root: "f" * 40)
    assert run_eval.validate_report(loaded)

    loaded["summary"]["receipt_false_completions"] = 99
    try:
        run_eval.validate_report(loaded)
    except ValueError as error:
        assert "digest" in str(error)
    else:
        raise AssertionError("tampered report was accepted")

    semantic_tamper = json.loads(output.read_text(encoding="utf-8"))
    semantic_tamper["summary"]["receipt_false_completions"] = 99
    unsigned = dict(semantic_tamper)
    unsigned.pop("report_digest")
    semantic_tamper["report_digest"] = run_eval.hashlib.sha256(
        run_eval.canonical_json_bytes(unsigned)
    ).hexdigest()
    with pytest.raises(ValueError, match="promotion decision"):
        run_eval.validate_report(semantic_tamper)


def test_runtime_protocol_eval_never_imports_frozen_benchmark():
    source = run_eval.Path(run_eval.__file__).read_text(encoding="utf-8")
    assert "from bench" not in source
    assert "import bench" not in source
