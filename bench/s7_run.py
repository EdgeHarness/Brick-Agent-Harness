"""Run the one active score-masked D0 cohort with deferred grading."""

import argparse
import datetime
import os
from pathlib import Path
from types import SimpleNamespace

from bench import s6_run, s7_preflight
from bench.s7_contract import DEFAULT_PROTOCOL, load_protocol, s7_protocol_sha256


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFESTS = ROOT / "bench" / "manifests" / "office-v1"
DEFAULT_RUNS = (
    Path("C:/BrickRuns/s7") if os.name == "nt" else ROOT / "results-s7"
)


def run(args, preflight=None):
    s7 = load_protocol(args.protocol)
    cohort = args.cohort or s7["d0"]["active_cohort"]
    if cohort != s7["d0"]["active_cohort"]:
        raise RuntimeError(
            "only the correction protocol's active D0 cohort may execute"
        )
    if getattr(args, "instance_id", None) is not None:
        raise ValueError("D0 forbids single-instance selection")
    if getattr(args, "max_cases", None) is not None:
        raise ValueError("D0 forbids case-count truncation")
    checked = preflight or s7_preflight.collect(args.protocol, require_clean=True)
    run_id = args.run_id or (
        "s7-%s-%s" % (
            cohort,
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        )
    )
    base_args = SimpleNamespace(
        protocol=ROOT / s7["base_protocol_path"],
        manifests=args.manifests,
        runs_root=args.runs_root,
        split="development",
        instance_id=None,
        condition=list(s7["d0"]["conditions"]),
        max_cases=None,
        run_id=run_id,
        allow_dirty=False,
    )
    policy = s6_run.RunPolicy(
        run_kind="score_masked_d0",
        grading_mode="deferred",
        score_masked=True,
        cohort=cohort,
        instance_prefix="development.%s." % cohort,
        protocol_binding={
            "schema_version": s7["schema_version"],
            "protocol_version": s7["protocol_version"],
            "sha256": s7_protocol_sha256(s7),
        },
        required_conditions=tuple(s7["d0"]["conditions"]),
        summary_schema="brick.s7.d0-run-summary/1",
        environment_retry_cooldown_seconds=(
            s7["environment_recovery"]["cooldown_seconds"]
        ),
        verify_transport_health_before_retry=(
            s7["environment_recovery"][
                "verify_loopback_version_and_model_digest"
            ]
        ),
    )
    summary = s6_run._run(base_args, policy, preflight=checked)
    if len(summary["cells"]) != s7["d0"]["primary_attempts_per_cohort"]:
        raise RuntimeError("D0 did not schedule exactly 88 primary attempts")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFESTS)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--cohort", choices=("d0a", "d0b"))
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
