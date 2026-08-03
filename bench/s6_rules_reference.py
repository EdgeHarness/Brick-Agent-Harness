"""Run the deterministic office rules reference and strict generated graders.

This command is model-free.  It is an architecture-selection reference, not a
primary or descriptive model condition, and cannot establish a harness effect.
The S6C protocol keeps retained execution disabled, so this runner does too.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

from domains.office_demo.generated_grader import build_grader
from domains.office_demo.rules_reference import REFERENCE_VERSION, execute
from harness.evidence import canonical_json_bytes
from harness.experiment import validate_protocol
from harness.instances import load_canonical_json, validate_manifest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PROTOCOL = HERE / "s6_protocol.json"
DEFAULT_MANIFESTS = HERE / "manifests" / "office-v1"


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def implementation_sha256():
    paths = (
        ROOT / "domains" / "office_demo" / "rules_reference.py",
        ROOT / "domains" / "office_demo" / "generated_grader.py",
        ROOT / "domains" / "office_demo" / "office_files.py",
        ROOT / "domains" / "office_demo" / "generators.py",
        ROOT / "bench" / "s6_rules_reference.py",
    )
    document = {
        path.relative_to(ROOT).as_posix(): _sha256_file(path) for path in paths
    }
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def run(protocol_path, manifests_root, split, instance_id=None):
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    validate_protocol(protocol)
    if split == "retained" or protocol["retained_execution_enabled"] is not False:
        raise RuntimeError(
            "S6C mechanically forbids retained reference execution; unlock belongs "
            "to S8/S9"
        )
    manifest = load_canonical_json(Path(manifests_root) / (split + ".json"))
    validate_manifest(manifest)
    instances = manifest["instances"]
    if instance_id is not None:
        instances = [
            item for item in instances if item["content"]["id"] == instance_id
        ]
        if len(instances) != 1:
            raise ValueError("instance id is absent or ambiguous")

    records = []
    for instance in instances:
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="brick-s6-rules-") as directory:
            evidence = execute(instance, directory)
            outcome = build_grader(instance).grade_evidence(evidence)
            artifacts = [
                {
                    "name": name,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
                for name, payload in sorted(evidence.artifact_map().items())
            ]
        records.append(
            {
                "instance_id": instance["content"]["id"],
                "family": instance["content"]["family"],
                "instance_content_sha256": instance["content_sha256"],
                "grader_status": outcome.grader_status,
                "strict_success": outcome.strict_success,
                "checks": [
                    {"id": key, "passed": passed}
                    for key, _description, passed in outcome.checks
                ],
                "action_count": len(evidence.actions),
                "artifacts": artifacts,
                "wall_seconds": time.monotonic() - started,
            }
        )
    return {
        "schema_version": "brick.s6.rules-reference-summary/1",
        "reference_version": REFERENCE_VERSION,
        "implementation_sha256": implementation_sha256(),
        "run_kind": "model_free_architecture_reference",
        "split": split,
        "case_count": len(records),
        "strict_successes": sum(item["strict_success"] is True for item in records),
        "all_strict": bool(records) and all(
            item["strict_success"] is True for item in records
        ),
        "records": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--manifests", type=Path, default=DEFAULT_MANIFESTS)
    parser.add_argument(
        "--split",
        choices=("development", "validation", "sentinel", "adversarial", "retained"),
        default="development",
    )
    parser.add_argument("--instance-id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        summary = run(
            args.protocol, args.manifests, args.split, args.instance_id
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": "brick.s6.rules-reference-summary/1",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    payload = canonical_json_bytes(summary, allow_float=True, newline=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(payload)
    print(payload.decode("utf-8"), end="")
    return 0 if summary["all_strict"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
