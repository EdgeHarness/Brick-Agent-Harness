"""Independent read-only verifier for the fixed v0.13.6 recovery release."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from harness import evidence as _evidence
from harness.evidence import AttemptKey, canonical_json_bytes, validate_committed, validate_prepared
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]
SUCCESSOR_ROOT = ROOT / "results-next-study" / "focused-recovery-v0136"
OLD_ROOT = ROOT / "results-next-study" / "focused-v0135-focused-followup-r1"
PROTOCOL_PATH = ROOT / "bench" / "focused_recovery_successor_protocol.json"
AUTHORIZATION_PATH = SUCCESSOR_ROOT / "authorization.json"
BLOCKS = ("B1b_recovery", "B2_repeatability")
RUNS = {
    "B1b_recovery": (SUCCESSOR_ROOT / "b1b-recovery", "v0136-b1b-recovery-r1"),
    "B2_repeatability": (SUCCESSOR_ROOT / "b2-repeatability", "v0136-b2-repeatability-r1"),
}
VERIFICATION_SCHEMA = "brick.focused-recovery-successor.independent-verification/1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class VerificationError(ValueError):
    pass


def _digest(value, allow_float=False):
    return hashlib.sha256(canonical_json_bytes(value, allow_float=allow_float)).hexdigest()


def _file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _time(value, label):
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise VerificationError(label + " is not a timezone-aware timestamp") from exc
    if parsed.utcoffset() is None:
        raise VerificationError(label + " is not a timezone-aware timestamp")
    return parsed


def _published(path, label):
    path = Path(path); marker = path.with_name(path.name + ".complete")
    if not path.is_file() or not marker.is_file() or marker.stat().st_size != 0:
        raise VerificationError(label + " is not marker-last")
    try:
        return load_canonical_json(path)
    except Exception as exc:
        raise VerificationError(label + " is not canonical JSON") from exc


def _self_digest(document, field, label):
    if not isinstance(document, dict) or not isinstance(document.get(field), str):
        raise VerificationError(label + " digest is absent")
    unsigned = dict(document); supplied = unsigned.pop(field)
    if _SHA256.fullmatch(supplied) is None or supplied != _digest(unsigned):
        raise VerificationError(label + " self-digest drifted")
    return supplied


def _tree_manifest(root):
    records = []
    for path in sorted(Path(root).rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise VerificationError("bound tree contains a symlink")
        if path.is_file():
            records.append({"path": path.relative_to(root).as_posix(),
                            "size": path.stat().st_size, "sha256": _file_digest(path)})
    return {"files": len(records), "tree_sha256": _digest(records)}


def _candidate_tree(candidate):
    members = []
    for member in sorted(candidate.rglob("*"), key=lambda item: item.relative_to(candidate).as_posix()):
        if member.is_symlink():
            raise VerificationError("candidate contains a symlink")
        if member.is_file():
            members.append({"path": member.relative_to(candidate).as_posix(),
                            "size": member.stat().st_size, "sha256": _file_digest(member)})
    return _digest(members)


def _resource_metrics(result, actions):
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    ledger = diagnostics.get("ledger") if isinstance(diagnostics.get("ledger"), dict) else {}
    actions = actions if isinstance(actions, list) else []
    reads = {"read_email", "list_emails", "list_events", "read_spreadsheet", "recall_memories"}
    mutations = {"send_email", "add_event", "send_message", "set_reminder",
                 "create_presentation", "create_spreadsheet", "save_memory"}
    exact_flag = ledger.get("generated_tokens_exact"); tokens = metrics.get("generated_tokens")
    exact = tokens if exact_flag is True and type(tokens) is int and tokens >= 0 else None
    def milliseconds(ms_key, seconds_key):
        value = metrics.get(ms_key)
        if type(value) is int and value >= 0:
            return value
        seconds = metrics.get(seconds_key, 0)
        return int(round(seconds * 1000)) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0 else 0
    return {
        "model_calls": metrics.get("model_calls", ledger.get("model_calls", 0)),
        "successful_reads": sum(item.get("ok") is True and item.get("tool") in reads for item in actions if isinstance(item, dict)),
        "successful_mutations": sum(item.get("ok") is True and item.get("tool") in mutations for item in actions if isinstance(item, dict)),
        "generated_tokens_exact": exact,
        "generated_tokens_lower_bound": None if exact is not None else ledger.get("generated_tokens_lower_bound", 0),
        "generated_tokens_upper_bound": None if exact is not None else ledger.get("generated_tokens_upper_bound", 6144),
        "model_time_ms": milliseconds("model_time_ms", "model_time_seconds"),
        "wall_time_ms": milliseconds("wall_time_ms", "wall_time_seconds"),
    }


def _attempt_record(committed, cell):
    result = committed["result"]; grade = committed["grade"]
    raw_origin = result.get("failure_origin")
    if raw_origin in ("none", "model") and grade.get("grader_status") == "graded":
        origin = raw_origin; strict = grade.get("candidate_decision")
    elif raw_origin == "environment":
        origin = "environment"; strict = None
    else:
        origin = "instrument"; strict = None
    repeat = committed["attempt_key"]["repeat"]
    failure = result.get("failure")
    retryable = bool(origin == "environment" and repeat == 0 and
                     isinstance(failure, dict) and failure.get("retryable") is True)
    return {
        "schema_version": "brick.focused-followup.attempt-record/2",
        "logical_cell_id": cell["logical_cell_id"], "repeat": repeat,
        "trial_seed": cell["trial_seed"], "failure_origin": origin,
        "retryable": retryable, "strict_success": strict,
        "opportunity_budget_exhausted": bool(
            isinstance(failure, dict) and failure.get("type") == "opportunity_budget_exhausted"
        ),
        "evidence_sha256": _digest(
            {key: value for key, value in committed.items() if key != "actions"},
            allow_float=True,
        ),
        "grade_record_sha256": _digest(committed.get("grade"), allow_float=True),
        "marker_last_verified": True,
        **_resource_metrics(result, committed.get("actions", {}).get("actions", [])),
    }


def _validate_repository(protocol, authorization):
    if _tree_manifest(OLD_ROOT) != authorization["old_tree_manifest"]:
        raise VerificationError("immutable old tree differs from authorization")
    for label, binding in protocol["old_bindings"].items():
        if label in ("runs_root", "schedules"):
            continue
        path = (ROOT / binding["path"]).resolve()
        if path != (ROOT / "bench" / "focused_followup_protocol.json").resolve():
            try:
                path.relative_to(OLD_ROOT.resolve())
            except ValueError as exc:
                raise VerificationError("old binding escapes immutable root") from exc
        if _file_digest(path) != binding["file_sha256"]:
            raise VerificationError("old binding changed: " + label)
    source_paths = {
        "recovery_module": ROOT / "bench" / "focused_recovery_successor.py",
        "recovery_protocol": PROTOCOL_PATH,
        "supervisor": ROOT / authorization["source_digests"]["supervisor_path"],
        "classifier_source": ROOT / authorization["source_digests"]["classifier_source_path"],
        "parser_incident": ROOT / authorization["source_digests"]["parser_incident_path"],
        "projection_rewrite_incident": ROOT / authorization["source_digests"]["projection_rewrite_incident_path"],
        "release_verifier": ROOT / authorization["source_digests"]["release_verifier_path"],
    }
    for label, path in source_paths.items():
        if _file_digest(path) != authorization["source_digests"][label]:
            raise VerificationError("authorization-bound source changed: " + label)
    for relative, digest in authorization["source_digests"]["live_implementation_delta"]["current_path_digests"].items():
        current = hashlib.sha256((ROOT / relative).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if current != digest:
            raise VerificationError("authorization-bound live source changed: " + relative)
    transitive_paths = {
        "focused_followup": ROOT / "bench" / "focused_followup.py",
        "focused_protocol": ROOT / "bench" / "focused_followup_protocol.json",
        "generator": ROOT / "domains" / "office_demo" / "generators_v2.py",
        "strict_graders": ROOT / "domains" / "office_demo" / "strict_graders.py",
        "office_files": ROOT / "domains" / "office_demo" / "office_files.py",
        "world": ROOT / "domains" / "office_demo" / "world.py",
        "contracts": ROOT / "domains" / "office_demo" / "contracts.py",
        "reviewed_grader": ROOT / "domains" / "office_demo" / "reviewed_grader_v2.py",
        "validated_outcomes_validator": ROOT / "bench" / "next_study_validated_outcomes.py",
        "validated_outcomes": ROOT / "evidence" / "next-study" / "office-v2-validated-outcomes.json",
        "manifest_lock": ROOT / "bench" / "manifests" / "office-v2" / "manifest-lock.json",
    }
    for split in ("calibration", "development", "validation", "sentinel", "retained", "adversarial"):
        transitive_paths["manifest_" + split] = ROOT / "bench" / "manifests" / "office-v2" / (split + ".json")
    expected_transitive = authorization["source_digests"]["transitive_source_digests"]
    if set(transitive_paths) != set(expected_transitive):
        raise VerificationError("transitive source inventory schema drifted")
    for label, path in transitive_paths.items():
        if _file_digest(path) != expected_transitive[label]:
            raise VerificationError("authorization-bound transitive source changed: " + label)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()
    if head != authorization["commit_sha"]:
        raise VerificationError("HEAD differs from authorization")
    tag_object = subprocess.run(["git", "rev-parse", "v0.13.6^{tag}"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
    if tag_object != authorization["tag_object_sha"]:
        raise VerificationError("annotated tag differs from authorization")
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                            cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    if status:
        raise VerificationError("independent verification requires the authorized clean worktree")


def _run_and_terminal(authorization, archive, block):
    terminal_entry = archive["terminal_artifacts"][block]
    terminal_path = ROOT / terminal_entry["path"]
    terminal = _published(terminal_path, "terminal " + block)
    if terminal_entry["file_sha256"] != _file_digest(terminal_path):
        raise VerificationError("terminal file hash differs from archive")
    runs_root, run_id = RUNS[block]
    run_path = runs_root / run_id / "run.json"
    run = load_canonical_json(run_path)
    run_sha = _file_digest(run_path)
    if run.get("run_id") != run_id or run_sha != terminal["run_sha256"]:
        raise VerificationError("fixed run identity drifted: " + block)
    schedule = archive["schedules"][block]
    if _digest(schedule) != authorization["schedule_digests"][block]:
        raise VerificationError("archived schedule differs from authorization: " + block)
    cells = {(cell["instance_id"], cell["condition"], cell["trial_seed"], cell["trial_index"]): cell
             for cell in schedule["records"]}
    start_path = runs_root / "focused-recovery-starts" / authorization["authorization_sha256"] / (block + ".json")
    block_start = _published(start_path, "block start " + block)
    _self_digest(block_start, "start_sha256", "block start")
    if (
        block_start["run_id"] != run_id or block_start["run_sha256"] != run_sha
        or block_start["schedule_sha256"] != _digest(schedule)
        or _time(block_start["started_at"], "block start") < _time(authorization["issued_at"], "authorization")
    ):
        raise VerificationError("block start binding or chronology drifted")
    candidate_records = []; committed_records = []; by_cell = defaultdict(list)
    attempts_root = runs_root / run_id / "attempts"
    for logical_dir in sorted(attempts_root.iterdir(), key=lambda item: item.name):
        if logical_dir.is_symlink() or not logical_dir.is_dir():
            raise VerificationError("irregular logical attempt directory")
        for candidate in sorted(logical_dir.iterdir(), key=lambda item: item.name):
            if candidate.is_symlink() or not candidate.is_dir():
                raise VerificationError("irregular physical candidate")
            attempt = json.loads((candidate / "attempt.json").read_bytes())
            key = attempt["attempt_key"]
            coordinate = (key["instance"]["id"], key["condition"]["name"],
                          key["sampling"]["seed"], key["sampling"]["trial_index"])
            cell = cells.get(coordinate)
            parsed = AttemptKey.from_dict(key)
            if cell is None or parsed.logical_hash != logical_dir.name or attempt["physical_uuid"] != candidate.name:
                raise VerificationError("candidate does not join archived schedule")
            state = "committed" if (candidate / "COMMITTED").is_file() else (
                "prepared" if (candidate / "PREPARED.json").is_file() else "abandoned")
            if state == "committed":
                validated = validate_committed(candidate, expected_key=parsed,
                                               expected_run={"run_id": run_id, "run_sha256": run_sha})
                committed = _evidence._record_from_validated(validated)
                committed["actions"] = validated["semantic"]["actions"]
                committed_records.append(_attempt_record(committed, cell))
            elif state == "prepared":
                validate_prepared(candidate, expected_key=parsed,
                                  expected_run={"run_id": run_id, "run_sha256": run_sha})
            record = {"logical_cell_id": cell["logical_cell_id"], "logical_hash": logical_dir.name,
                      "physical_uuid": candidate.name, "repeat": key["repeat"], "state": state,
                      "candidate_tree_sha256": _candidate_tree(candidate)}
            candidate_records.append(record); by_cell[cell["logical_cell_id"]].append(record)
    candidate_records.sort(key=lambda item: (item["logical_cell_id"], item["repeat"], item["physical_uuid"]))
    if len(candidate_records) > schedule["maximum_physical_attempts"] or any(len(v) > 2 for v in by_cell.values()):
        raise VerificationError("physical candidate ceiling exceeded")
    digest_field = "seal_sha256" if terminal_entry["disposition"] == "sealed" else "termination_sha256"
    if _self_digest(terminal, digest_field, "terminal") != terminal_entry[digest_field]:
        raise VerificationError("terminal digest differs from archive")
    if terminal["candidate_records_sha256"] != _digest(candidate_records):
        raise VerificationError("terminal candidate inventory digest drifted")
    if terminal["candidate_state_counts"] != dict(sorted(Counter(r["state"] for r in candidate_records).items())):
        raise VerificationError("terminal candidate states drifted")
    if terminal["physical_attempts"] != len(candidate_records):
        raise VerificationError("terminal physical count drifted")
    committed_records.sort(key=lambda item: (item["logical_cell_id"], item["repeat"]))
    if terminal["attempt_records_sha256"] != _digest(committed_records):
        raise VerificationError("terminal committed-attempt ledger drifted")
    grouped = defaultdict(dict)
    for record in committed_records:
        grouped[record["logical_cell_id"]][record["repeat"]] = record
    final = {}; invalid = []
    for cell in schedule["records"]:
        entries = grouped.get(cell["logical_cell_id"], {})
        first, second = entries.get(0), entries.get(1)
        if second is not None and (first is None or not first["retryable"]):
            raise VerificationError("terminal retry topology drifted")
        if first is not None:
            final[cell["logical_cell_id"]] = second or first
            if final[cell["logical_cell_id"]]["failure_origin"] not in ("none", "model"):
                invalid.append(cell["logical_cell_id"])
    if (
        terminal["logical_cells_complete"] != len(final)
        or terminal["instrument_invalid_cells"] != len(invalid)
        or terminal.get("missing_cells", len(schedule["records"]) - len(final))
        != len(schedule["records"]) - len(final)
    ):
        raise VerificationError("terminal logical outcome counts drifted")
    start_root = (runs_root / "focused-recovery-cell-starts" /
                  authorization["authorization_sha256"] / block)
    starts = []
    cells_by_id = {cell["logical_cell_id"]: cell for cell in schedule["records"]}
    if start_root.exists():
        for path in sorted(start_root.iterdir(), key=lambda item: item.name):
            if path.name.endswith(".json.complete"):
                json_path = path.with_name(path.name[:-9])
                if not json_path.is_file() or path.stat().st_size != 0:
                    raise VerificationError("orphan logical-cell start marker")
                continue
            if path.suffix != ".json" or path.stem not in cells_by_id:
                raise VerificationError("foreign logical-cell start")
            item = _published(path, "logical-cell start")
            _self_digest(item, "cell_start_sha256", "logical-cell start")
            cell = cells_by_id[path.stem]
            if (
                item["authorization_sha256"] != authorization["authorization_sha256"]
                or item["run_id"] != run_id or item["run_sha256"] != run_sha
                or item["schedule_sha256"] != _digest(schedule)
                or item["block_start_sha256"] != block_start["start_sha256"]
                or item["logical_cell_id"] != cell["logical_cell_id"]
                or item["instance_id"] != cell["instance_id"]
                or item["condition"] != cell["condition"]
                or item["trial_seed"] != cell["trial_seed"]
                or item["trial_index"] != cell["trial_index"]
                or _time(item["started_at"], "logical-cell start") < _time(block_start["started_at"], "block start")
            ):
                raise VerificationError("logical-cell start binding drifted")
            starts.append({"logical_cell_id": path.stem,
                           "cell_start_sha256": item["cell_start_sha256"],
                           "file_sha256": _file_digest(path)})
    if terminal["logical_cells_started"] != len(starts) or terminal["cell_start_records_sha256"] != _digest(starts):
        raise VerificationError("terminal logical-cell start inventory drifted")
    return terminal, block_start


def verify_release(verified_at=None):
    protocol = load_canonical_json(PROTOCOL_PATH)
    authorization = _published(AUTHORIZATION_PATH, "authorization")
    _self_digest(authorization, "authorization_sha256", "authorization")
    if authorization["protocol_sha256"] != _digest(protocol):
        raise VerificationError("authorization protocol binding drifted")
    frozen_specs = {
        block: {
            "run_id": protocol["execution"]["blocks"][block]["run_id"],
            "runs_root": protocol["execution"]["blocks"][block]["runs_root"],
            "logical_cells": protocol["execution"]["blocks"][block]["logical_cells"],
            "maximum_physical_attempts": protocol["execution"]["blocks"][block]["maximum_physical_attempts"],
        }
        for block in BLOCKS
    }
    if (
        authorization["schedule_digests"] != {
            block: protocol["execution"]["blocks"][block]["schedule_sha256"]
            for block in BLOCKS
        }
        or authorization["run_specs"] != frozen_specs
        or protocol["execution"]["maximum_logical_cells"] != 264
        or protocol["execution"]["maximum_physical_attempts"] != 528
    ):
        raise VerificationError("authorization schedule/run ceilings differ from fixed protocol")
    _validate_repository(protocol, authorization)
    auth = authorization["authorization_sha256"]
    analysis_path = SUCCESSOR_ROOT / "analysis" / auth / "analysis.json"
    report_path = SUCCESSOR_ROOT / "reports" / auth / "report.json"
    release_root = SUCCESSOR_ROOT / "release" / auth
    analysis = _published(analysis_path, "analysis"); report = _published(report_path, "report")
    archive = _published(release_root / "archive.json", "archive")
    manifest = _published(release_root / "manifest.json", "manifest")
    _self_digest(analysis, "analysis_sha256", "analysis")
    _self_digest(report, "report_sha256", "report")
    _self_digest(archive, "archive_sha256", "archive")
    _self_digest(manifest, "manifest_sha256", "manifest")
    recovery_schedule = archive["schedules"]["B1b_recovery"]
    repeat_schedule = archive["schedules"]["B2_repeatability"]
    if (
        recovery_schedule.get("logical_cell_count") != 24
        or len(recovery_schedule.get("records", [])) != 24
        or {item.get("family") for item in recovery_schedule["records"]} != {"xlsx_basic"}
        or len({item.get("instance_id") for item in recovery_schedule["records"]}) != 12
        or set(Counter(item.get("instance_id") for item in recovery_schedule["records"]).values()) != {2}
        or any(
            {item.get("condition") for item in recovery_schedule["records"] if item.get("instance_id") == instance_id}
            != {"native_tools", "harness_full"}
            for instance_id in {item.get("instance_id") for item in recovery_schedule["records"]}
        )
        or any(item.get("trial_index") != 0 for item in recovery_schedule["records"])
        or len(repeat_schedule.get("records", [])) != 240
        or any(item.get("trial_index") != 1 for item in repeat_schedule["records"])
        or _digest(repeat_schedule) != protocol["old_bindings"]["schedules"]["B2"]
    ):
        raise VerificationError("archived fixed 24/240 schedule identities drifted")
    validated_blocks = {block: _run_and_terminal(authorization, archive, block) for block in BLOCKS}
    terminals = {block: item[0] for block, item in validated_blocks.items()}
    starts = {block: item[1] for block, item in validated_blocks.items()}
    terminal_times = [
        _time(item.get("block_finished_at", item.get("terminated_at")), "terminal time")
        for item in terminals.values()
    ]
    if not (
        _time(authorization["issued_at"], "authorization")
        <= min(terminal_times)
        <= max(terminal_times)
        <= _time(analysis["analyzed_at"], "analysis")
        <= _time(report["reported_at"], "report")
        <= _time(archive["archived_at"], "archive")
        <= _time(manifest["manifested_at"], "manifest")
    ):
        raise VerificationError("release chronology drifted")
    b1_terminal_time = _time(
        terminals["B1b_recovery"].get("block_finished_at", terminals["B1b_recovery"].get("terminated_at")),
        "B1 terminal",
    )
    if _time(starts["B2_repeatability"]["started_at"], "B2 start") < b1_terminal_time:
        raise VerificationError("B2 start predates B1 terminal")
    if (
        report["analysis_sha256"] != analysis["analysis_sha256"]
        or archive["authorization"]["file_sha256"] != _file_digest(AUTHORIZATION_PATH)
        or archive["analysis"]["file_sha256"] != _file_digest(analysis_path)
        or archive["report"]["file_sha256"] != _file_digest(report_path)
        or archive["analysis"]["analysis_sha256"] != analysis["analysis_sha256"]
        or archive["report"]["report_sha256"] != report["report_sha256"]
        or manifest["archive_sha256"] != archive["archive_sha256"]
        or manifest["archive_file_sha256"] != _file_digest(release_root / "archive.json")
        or manifest["analysis_sha256"] != analysis["analysis_sha256"]
        or manifest["report_sha256"] != report["report_sha256"]
        or report["terminal_dispositions"] != analysis["terminal_dispositions"]
        or archive["terminal_dispositions"] != analysis["terminal_dispositions"]
        or manifest["terminal_dispositions"] != analysis["terminal_dispositions"]
        or any(item.get("claim") is not None or item.get("may_issue_or_alter_claim") is not False
               for item in (analysis, report, archive, manifest))
    ):
        raise VerificationError("release cross-binding or nonclaiming contract drifted")
    for block, terminal in terminals.items():
        terminal_sha = terminal.get("seal_sha256", terminal.get("termination_sha256"))
        if analysis["terminal_dispositions"][block]["terminal_sha256"] != terminal_sha:
            raise VerificationError("analysis terminal binding drifted")
    verified_at = verified_at or datetime.datetime.now(datetime.timezone.utc).isoformat()
    if _time(verified_at, "verification") < _time(manifest["manifested_at"], "manifest"):
        raise VerificationError("verification predates manifest")
    document = {
        "schema_version": VERIFICATION_SCHEMA, "status": "independently_rederived_valid",
        "authorization_sha256": auth, "archive_sha256": archive["archive_sha256"],
        "manifest_sha256": manifest["manifest_sha256"],
        "verifier_source_sha256": _file_digest(Path(__file__)),
        "old_root_read_only": True, "both_terminals_revalidated": True,
        "claim": None, "may_issue_or_alter_claim": False, "verified_at": verified_at,
    }
    document["verification_sha256"] = _digest(document)
    return document


def _publish_verification(document):
    auth = document["authorization_sha256"]
    path = SUCCESSOR_ROOT / "release" / auth / "independent-verification.json"
    marker = path.with_name(path.name + ".complete")
    if marker.exists() and not path.is_file():
        raise VerificationError("verification marker exists without JSON")
    if marker.exists() and (not marker.is_file() or marker.stat().st_size != 0):
        raise VerificationError("verification marker is invalid")
    if path.is_file():
        existing = load_canonical_json(path)
        rebuilt = verify_release(existing["verified_at"])
        if existing != rebuilt:
            raise VerificationError("existing verification differs from rederivation")
        document = existing
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(canonical_json_bytes(document, newline=True, allow_float=False))
            handle.flush(); os.fsync(handle.fileno())
    if not marker.exists():
        with marker.open("xb") as handle:
            handle.flush(); os.fsync(handle.fileno())
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify"); verify.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        document = verify_release()
        expected = SUCCESSOR_ROOT / "release" / document["authorization_sha256"] / "independent-verification.json"
        if Path(args.output).resolve() != expected.resolve():
            raise VerificationError("verification output must be the fixed authorization-bound path")
        document = _publish_verification(document)
        print(json.dumps({"status": document["status"],
                          "verification_sha256": document["verification_sha256"]}, sort_keys=True))
    except VerificationError as exc:
        parser.exit(2, "focused recovery verification error: %s\n" % exc)


if __name__ == "__main__":
    main()
