"""Operator CLI for the genuine-human successor review workflow."""

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import stat

from harness.evidence import canonical_json_bytes
from harness.instances import (
    load_canonical_json, replace_canonical_json, sha256_bytes,
)

from . import generate_next_study
from .next_study_review import (
    build_assignments, build_pending_ledger, build_pilot,
    compile_adjudicated_outcomes,
    digest_review_artifact,
    export_adjudication_packet, export_review_packets, materialize_ledger,
    seal_submission,
    staffing_ready, validate_pilot_result, validate_sealed_submission,
    validate_assignments, validate_ledger, validate_pilot, validate_staffing,
    PILOT_RESULT_SCHEMA, REVIEW_PROTOCOL_VERSION, STAFFING_SCHEMA,
)
from .next_study_review_selection import validate_review_selection
from .next_study_review_training import (
    HANDBOOK_PATH, PRACTICE_PATH, REVIEW_PROTOCOL_PATH,
    qualification_roster_record, score_qualification,
    seal_qualification_submission, verify_artifacts as verify_training_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STAFFING = generate_next_study.EVIDENCE_DIRECTORY / generate_next_study.STAFFING_NAME
DEFAULT_READY_STAFFING = (
    generate_next_study.EVIDENCE_DIRECTORY / "office-v2-review-staffing-ready.json"
)
DEFAULT_LEDGER = generate_next_study.EVIDENCE_DIRECTORY / generate_next_study.REVIEW_LEDGER_NAME
DEFAULT_SELECTION = (
    generate_next_study.EVIDENCE_DIRECTORY / generate_next_study.REVIEW_SELECTION_NAME
)
DEFAULT_MATERIALIZED_LEDGER = (
    generate_next_study.EVIDENCE_DIRECTORY / "office-v2-review-materialized.json"
)
DEFAULT_ASSIGNMENTS = generate_next_study.EVIDENCE_DIRECTORY / "office-v2-review-assignments.json"
DEFAULT_PILOT = generate_next_study.EVIDENCE_DIRECTORY / "office-v2-review-pilot.json"
DEFAULT_PILOT_RESULT = generate_next_study.EVIDENCE_DIRECTORY / "office-v2-review-pilot-result.json"
DEFAULT_ADJUDICATED_OUTCOMES = (
    generate_next_study.EVIDENCE_DIRECTORY / "office-v2-adjudicated-outcomes.json"
)
DEFAULT_RECEIPTS = (
    generate_next_study.EVIDENCE_DIRECTORY / "office-v2-review-receipts"
)


class ReviewOperationsError(ValueError):
    pass


def _digest_file(path):
    return sha256_bytes(Path(path).read_bytes())


def _manifests():
    return [
        load_canonical_json(generate_next_study.DEFAULT_DIRECTORY / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def _selection():
    return validate_review_selection(
        load_canonical_json(DEFAULT_SELECTION), _manifests()
    )


def frozen_review_bindings():
    verify_training_artifacts()
    lock_path = generate_next_study.DEFAULT_DIRECTORY / generate_next_study.LOCK_NAME
    lock = load_canonical_json(lock_path)
    return {
        "generator_version": lock["generator_version"],
        "generator_source_sha256": lock["generator_source_sha256"],
        "oracle_source_sha256": lock["oracle_source_sha256"],
        "manifest_lock_sha256": _digest_file(lock_path),
        "handbook_sha256": _digest_file(HANDBOOK_PATH),
        "review_protocol_sha256": _digest_file(REVIEW_PROTOCOL_PATH),
        "review_selection_sha256": _digest_file(DEFAULT_SELECTION),
    }


def _load_submissions(directory):
    valid, errors = [], []
    directory = Path(directory)
    if not directory.is_dir():
        return valid, [{"path": str(directory), "error": "directory_missing"}]
    json_paths = sorted(directory.glob("*.json"))
    marker_paths = sorted(directory.glob("*.json.complete"))
    known_markers = {Path(str(path) + ".complete") for path in json_paths}
    for marker in marker_paths:
        if marker not in known_markers:
            errors.append({"path": str(marker), "error": "orphan_completion_marker"})
    for path in json_paths:
        try:
            marker = Path(str(path) + ".complete")
            file_stat = os.lstat(path)
            marker_stat = os.lstat(marker)
            if not stat.S_ISREG(file_stat.st_mode) or not stat.S_ISREG(marker_stat.st_mode):
                raise ReviewOperationsError("submission or marker is not a regular file")
            if marker_stat.st_size != 0:
                raise ReviewOperationsError("completion marker must be empty")
            submission = load_canonical_json(path)
            validate_sealed_submission(submission)
            valid.append(submission)
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return valid, errors


def _load_published_json(path):
    path = Path(path)
    marker = Path(str(path) + ".complete")
    try:
        file_stat = os.lstat(path)
        marker_stat = os.lstat(marker)
    except FileNotFoundError:
        raise ReviewOperationsError("published document or completion marker is missing")
    if not stat.S_ISREG(file_stat.st_mode) or not stat.S_ISREG(marker_stat.st_mode):
        raise ReviewOperationsError("published document or marker is not a regular file")
    if marker_stat.st_size != 0:
        raise ReviewOperationsError("published document marker must be empty")
    return load_canonical_json(path)


def _publish_json_marker_last(path, document):
    """Publish one immutable JSON document, then its empty commit marker."""

    path = Path(path)
    marker = Path(str(path) + ".complete")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or marker.exists():
        raise ReviewOperationsError("sealed publication path already exists")
    payload = canonical_json_bytes(document, allow_float=False, newline=True)
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        raise
    marker_descriptor = os.open(
        str(marker), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        os.fsync(marker_descriptor)
    finally:
        os.close(marker_descriptor)
    return path


def _nearest_rank(values, proportion):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(proportion * len(ordered)) - 1]


def build_progress(assignments, submissions, entry_errors=(), manifests=None, staffing=None):
    if manifests is not None:
        validate_assignments(assignments, manifests, staffing)
    elif (
        not isinstance(assignments, dict)
        or assignments.get("case_count") != 308
        or assignments.get("planned_judgment_count") != 396
        or not isinstance(assignments.get("records"), list)
        or len(assignments["records"]) != 308
    ):
        raise ReviewOperationsError("progress assignments are invalid")
    assignment_by_packet = {
        item["packet_id"]: item for item in assignments["records"]
    }
    if len(assignment_by_packet) != 308:
        raise ReviewOperationsError("progress assignments contain duplicate packets")
    unique, duplicate_count = {}, 0
    for submission in submissions:
        validate_sealed_submission(submission)
        key = (submission["packet_id"], submission["role"])
        if key in unique:
            duplicate_count += 1
        else:
            unique[key] = submission
    reviewer_counts, review_durations, adjudication_durations = Counter(), [], []
    by_packet = defaultdict(dict)
    for (packet_id, role), submission in unique.items():
        if packet_id not in assignment_by_packet:
            raise ReviewOperationsError("progress contains an unassigned packet")
        assignment = assignment_by_packet[packet_id]
        role = submission["role"]
        if role not in ("primary", "secondary", "adjudicator"):
            raise ReviewOperationsError("progress contains an invalid role")
        if submission["reviewer_id"] != assignment[role]:
            raise ReviewOperationsError("progress submission signer is not assigned")
        reviewer_counts[submission["reviewer_id"]] += 1
        if role in ("primary", "secondary"):
            review_durations.append(submission["review_duration_seconds"])
        else:
            adjudication_durations.append(submission["review_duration_seconds"])
        by_packet[packet_id][role] = submission
    agreements = disputes = adjudications = resolved = 0
    for roles in by_packet.values():
        if "primary" in roles and "secondary" in roles:
            first = roles["primary"]["response"]
            second = roles["secondary"]["response"]
            same = all(first[key] == second[key] for key in (
                "prompt_valid", "outcome", "accepted_alternatives",
            ))
            agreements += int(same)
            disputes += int(not same)
            if "adjudicator" in roles:
                adjudications += 1
                resolved += int(not same)
        elif "adjudicator" in roles:
            raise ReviewOperationsError("adjudication cannot precede both reviews")
    reviewer_submissions = sum(
        role in ("primary", "secondary") for _packet, role in unique
    )
    primary_submissions = sum(role == "primary" for _packet, role in unique)
    secondary_submissions = sum(role == "secondary" for _packet, role in unique)
    return {
        "schema_version": "brick.next-study.review-progress/1",
        "assigned_cases": assignments["case_count"],
        "planned_reviewer_judgments": assignments["planned_judgment_count"],
        "maximum_expanded_reviewer_judgments": assignments["expanded_judgment_count"],
        "sealed_reviewer_judgments": reviewer_submissions,
        "sealed_primary_judgments": primary_submissions,
        "sealed_secondary_judgments": secondary_submissions,
        "sealed_adjudications": sum(
            role == "adjudicator" for _packet, role in unique
        ),
        "fully_double_reviewed_cases": agreements + disputes,
        "exact_agreements": agreements,
        "disputes": disputes,
        "resolved_disputes": resolved,
        "adjudications_on_seen_packets": adjudications,
        "reviewer_submission_counts": dict(sorted(reviewer_counts.items())),
        "median_review_seconds": _nearest_rank(review_durations, 0.5),
        "p90_review_seconds": _nearest_rank(review_durations, 0.9),
        "median_adjudication_seconds": _nearest_rank(
            adjudication_durations, 0.5
        ),
        "entry_errors": len(entry_errors),
        "duplicate_submissions": duplicate_count,
        "complete": (
            primary_submissions == assignments["case_count"]
            and secondary_submissions >= assignments["fixed_double_review_cases"]
            and disputes == resolved and not entry_errors and not duplicate_count
        ),
    }


def _find_packet(bundle, packet_id):
    for item in bundle.get("packets", []):
        packet = item.get("packet", {})
        if packet.get("packet_id") == packet_id:
            return item["role"], packet
    raise ReviewOperationsError("packet id is absent from reviewer bundle")


def _write_json(path, document):
    replace_canonical_json(Path(path), document)


def _status(args):
    staffing = validate_staffing(
        load_canonical_json(args.staffing), require_ready=False
    )
    manifests = _manifests()
    ledger = validate_ledger(load_canonical_json(args.ledger), manifests, _selection())
    protocol = verify_training_artifacts()
    assignments_present = Path(args.assignments).is_file()
    report = {
        "staffing_ready": staffing_ready(staffing),
        "active_reviewers": len(staffing.get("active_reviewers", [])),
        "ledger_status": ledger.get("status"),
        "completed_cases": ledger.get("completed_cases"),
        "assignments_present": assignments_present,
        "pilot_present": Path(args.pilot).is_file(),
        "pilot_result_present": Path(args.pilot_result).is_file(),
        "qualification_version": protocol["practice_version"],
        "qualification_cases": protocol["score_denominator"],
        "live_model_calls": 0,
    }
    if assignments_present and args.submissions:
        submissions, errors = _load_submissions(args.submissions)
        report["progress"] = build_progress(
            load_canonical_json(args.assignments), submissions, errors,
            manifests, staffing if staffing_ready(staffing) else None,
        )
    print(json.dumps(report, sort_keys=True))


def _init_assignments(args):
    staffing = validate_staffing(load_canonical_json(args.staffing))
    assignments = build_assignments(_manifests(), staffing, _selection())
    _write_json(args.output, assignments)
    print(json.dumps({
        "status": "written", "cases": assignments["case_count"],
        "planned_judgments": assignments["planned_judgment_count"],
        "expanded_judgments": assignments["expanded_judgment_count"],
        "output": str(args.output),
    }, sort_keys=True))


def _build_pilot(args):
    assignments = load_canonical_json(args.assignments)
    pilot = build_pilot(
        assignments, _manifests(), frozen_review_bindings(), _selection()
    )
    _write_json(args.output, pilot)
    print(json.dumps({
        "status": "written", "cases": 44, "judgments": 88,
        "output": str(args.output),
    }, sort_keys=True))


def _export(args, full):
    staffing = validate_staffing(load_canonical_json(args.staffing))
    assignments = load_canonical_json(args.assignments)
    pilot = load_canonical_json(args.pilot)
    manifests = _manifests()
    bindings = frozen_review_bindings()
    selection = _selection()
    validate_assignments(assignments, manifests, staffing, selection)
    validate_pilot(pilot, assignments, manifests, bindings, selection)
    included = {item["packet_id"] for item in pilot["records"]}
    if full:
        result = load_canonical_json(args.pilot_result)
        validate_pilot_result(pilot, result, bindings)
        included = {
            item["packet_id"] for item in assignments["records"]
            if item["packet_id"] not in included
        }
    requested_roles = None
    if full and result["global_escalation_triggered"]:
        requested_roles = {
            packet_id: ("primary", "secondary") for packet_id in included
        }
    paths = export_review_packets(
        args.output_dir, manifests, staffing, assignments,
        _digest_file(HANDBOOK_PATH), included, requested_roles,
    )
    print(json.dumps({
        "status": "written", "scope": "full_remaining" if full else "pilot",
        "reviewer_bundles": [str(path) for path in paths],
    }, sort_keys=True))


def _seal(args):
    bundle = load_canonical_json(args.bundle)
    role, packet = _find_packet(bundle, args.packet_id)
    if bundle["reviewer_id"] != args.reviewer_id:
        raise ReviewOperationsError("reviewer does not own this bundle")
    if args.role and args.role != role:
        raise ReviewOperationsError("requested role disagrees with bundle")
    if not args.attest:
        raise ReviewOperationsError("reviewer must explicitly provide --attest")
    if role == "adjudicator" and not args.attest_unseen:
        raise ReviewOperationsError(
            "adjudicator must explicitly provide --attest-unseen"
        )
    response = load_canonical_json(args.response)
    attestations = {
        "identity_confirmed": True,
        "no_source_access": True,
        "no_generative_ai": True,
        "no_case_discussion": True,
        "independent_response": True,
    }
    if role == "adjudicator":
        attestations.update({
            "reviews_unseen_before_seal": True, "oracle_unseen": True,
        })
    submission = seal_submission(
        packet, args.reviewer_id, role, response, args.started_at,
        args.sealed_at, attestations,
    )
    _publish_json_marker_last(args.output, submission)
    print(json.dumps({
        "status": "sealed", "packet_id": args.packet_id,
        "role": role, "output": str(args.output),
    }, sort_keys=True))


def _response_template(args):
    bundle = load_canonical_json(args.bundle)
    role, _packet = _find_packet(bundle, args.packet_id)
    identity_key = "adjudicator_id" if role == "adjudicator" else "reviewer_id"
    document = {
        identity_key: bundle["reviewer_id"],
        "prompt_valid": None,
        "outcome": [],
        "accepted_alternatives": [],
        "rationale": "",
    }
    _write_json(args.output, document)
    print(json.dumps({
        "status": "template_written", "packet_id": args.packet_id,
        "role": role, "output": str(args.output),
    }, sort_keys=True))


def _qualification_template(args):
    practice = load_canonical_json(PRACTICE_PATH)
    document = [
        {
            "practice_id": packet["practice_id"],
            "prompt_valid": None,
            "outcome": [],
            "accepted_alternatives": [],
            "rationale": "",
        }
        for packet in practice["packets"]
    ]
    _write_json(args.output, document)
    print(json.dumps({
        "status": "template_written", "cases": len(document),
        "output": str(args.output),
    }, sort_keys=True))


def _seal_qualification(args):
    if not args.attest:
        raise ReviewOperationsError(
            "reviewer must explicitly provide --attest for qualification"
        )
    responses = load_canonical_json(args.responses)
    document = seal_qualification_submission(
        args.reviewer_id, responses, args.sealed_at,
        {
            "identity_confirmed": True,
            "no_source_access": True,
            "no_generative_ai": True,
            "independent_response": True,
        },
    )
    _publish_json_marker_last(args.output, document)
    print(json.dumps({
        "status": "sealed", "reviewer_id": args.reviewer_id,
        "output": str(args.output),
    }, sort_keys=True))


def _export_adjudication(args):
    staffing = validate_staffing(load_canonical_json(args.staffing))
    assignments = load_canonical_json(args.assignments)
    manifests = _manifests()
    validate_assignments(assignments, manifests, staffing, _selection())
    submissions, errors = _load_submissions(args.submissions)
    if errors:
        raise ReviewOperationsError("adjudication export has invalid submissions")
    roles = {
        item["role"]: item for item in submissions
        if item["packet_id"] == args.packet_id
    }
    if set(roles) != {"primary", "secondary"}:
        raise ReviewOperationsError("adjudication requires exactly two sealed reviews")
    selection = _selection()
    probe = materialize_ledger(
        build_pending_ledger(manifests, selection), manifests, assignments,
        list(roles.values()), (), selection,
    )
    assignment = next(
        item for item in assignments["records"] if item["packet_id"] == args.packet_id
    )
    entry = next(
        item for item in probe["entries"]
        if item["instance_id"] == assignment["instance_id"]
    )
    if entry["status"] != "disputed":
        raise ReviewOperationsError("adjudication is allowed only for a derived dispute")
    path = export_adjudication_packet(
        args.output, manifests, staffing, assignments, args.packet_id,
        _digest_file(HANDBOOK_PATH),
    )
    print(json.dumps({
        "status": "written", "scope": "adjudication",
        "packet_id": args.packet_id, "output": str(path),
    }, sort_keys=True))


def _export_escalation(args):
    """Export only secondary reviews newly required by the derived ledger."""

    staffing = validate_staffing(load_canonical_json(args.staffing))
    assignments = load_canonical_json(args.assignments)
    manifests, selection = _manifests(), _selection()
    validate_assignments(assignments, manifests, staffing, selection)
    submissions, errors = _load_submissions(args.submissions)
    if errors:
        raise ReviewOperationsError("escalation export has invalid submissions")
    reviews = [item for item in submissions if item["role"] in ("primary", "secondary")]
    adjudications = [item for item in submissions if item["role"] == "adjudicator"]
    ledger = materialize_ledger(
        build_pending_ledger(manifests, selection), manifests, assignments,
        reviews, adjudications, selection,
    )
    by_instance = {item["instance_id"]: item for item in assignments["records"]}
    requested = {}
    for entry in ledger["entries"]:
        if entry["secondary_required"] and entry["reviews"]["secondary"] is None:
            packet_id = by_instance[entry["instance_id"]]["packet_id"]
            requested[packet_id] = ("secondary",)
    if not requested:
        raise ReviewOperationsError("no unresolved secondary-review escalation exists")
    paths = export_review_packets(
        args.output_dir, manifests, staffing, assignments,
        _digest_file(HANDBOOK_PATH), set(requested), requested,
    )
    print(json.dumps({
        "status": "written", "scope": "global" if ledger["global_escalation"] else "case",
        "required_secondary_cases": len(requested),
        "reviewer_bundles": [str(path) for path in paths],
    }, sort_keys=True))


def _intake(args):
    assignments = load_canonical_json(args.assignments)
    manifests = _manifests()
    selection = _selection()
    validate_assignments(assignments, manifests, selection=selection)
    output = Path(args.output)
    if output.resolve() == Path(DEFAULT_LEDGER).resolve():
        raise ReviewOperationsError(
            "intake cannot overwrite the checked-in pristine pending ledger"
        )
    incoming, errors = _load_submissions(args.submissions)
    receipt_directory = Path(args.receipt_dir)
    existing, receipt_errors = (
        _load_submissions(receipt_directory)
        if receipt_directory.exists() else ([], [])
    )
    if errors or receipt_errors:
        raise ReviewOperationsError(
            "submission intake has %d invalid files"
            % (len(errors) + len(receipt_errors))
        )
    merged = {
        (item["packet_id"], item["role"]): item for item in existing
    }
    if len(merged) != len(existing):
        raise ReviewOperationsError("receipt journal contains duplicate submissions")
    new_items = []
    for submission in incoming:
        key = (submission["packet_id"], submission["role"])
        prior = merged.get(key)
        if prior is not None and prior != submission:
            raise ReviewOperationsError("intake would replace sealed review work")
        if prior is None:
            merged[key] = submission
            new_items.append(submission)
    submissions = list(merged.values())
    build_progress(assignments, submissions, manifests=manifests)
    review_submissions = [
        item for item in submissions if item["role"] in ("primary", "secondary")
    ]
    adjudications = [item for item in submissions if item["role"] == "adjudicator"]
    ledger = materialize_ledger(
        build_pending_ledger(manifests, selection), manifests, assignments,
        review_submissions, adjudications, selection,
    )
    # Prove that the entire merged journal is structurally materializable before
    # committing even one new receipt.  This prevents an otherwise well-formed
    # but assignment-mismatched packet from permanently poisoning the journal.
    for submission in new_items:
        receipt_path = receipt_directory / (
            "%s.%s.json" % (submission["packet_id"], submission["role"])
        )
        _publish_json_marker_last(receipt_path, submission)
    terminal = ledger["status"] in ("complete", "rejected")
    if terminal:
        if output.exists():
            if _load_published_json(output) != ledger:
                raise ReviewOperationsError("terminal materialized ledger drifted")
        else:
            _publish_json_marker_last(output, ledger)
    progress = build_progress(assignments, submissions, manifests=manifests)
    print(json.dumps({
        "status": ledger["status"], "completed_cases": ledger["completed_cases"],
        "progress": progress,
        "receipt_directory": str(receipt_directory),
        "materialized_output": str(output) if terminal else None,
    }, sort_keys=True))


def _compile_outcomes(args):
    manifests = _manifests()
    selection = _selection()
    ledger = validate_ledger(_load_published_json(args.ledger), manifests, selection)
    outcomes = compile_adjudicated_outcomes(ledger, manifests, selection)
    _publish_json_marker_last(args.output, outcomes)
    print(json.dumps({
        "status": "published", "cases": outcomes["case_count"],
        "output": str(args.output), "live_model_calls": 0,
    }, sort_keys=True))


def _qualification(args):
    result = score_qualification(_load_published_json(args.submission))
    _publish_json_marker_last(args.output, result)
    if args.roster_record:
        _publish_json_marker_last(
            args.roster_record, qualification_roster_record(result)
        )
    print(json.dumps({
        "status": "qualified" if result["qualified"] else "not_qualified",
        "reviewer_id": result["reviewer_id"],
        "score": "%d/%d" % (
            result["score_numerator"], result["score_denominator"],
        ),
        "output": str(args.output),
    }, sort_keys=True))


def _reviewer_record(args):
    if not args.attest_all_roster_requirements:
        raise ReviewOperationsError(
            "reviewer must attest all roster requirements explicitly"
        )
    result = _load_published_json(args.qualification_result)
    if result.get("reviewer_id") != args.reviewer_id:
        raise ReviewOperationsError("qualification identity disagrees with reviewer")
    qualification = qualification_roster_record(result)
    if qualification["qualified"] is not True:
        raise ReviewOperationsError("unqualified reviewer cannot enter the roster")
    record = {
        "reviewer_id": args.reviewer_id,
        "name": args.name,
        "identity_attested": True,
        "conflicts_attested": True,
        "availability_attested": True,
        "access_ready": True,
        "compensation_arranged": True,
        "confidentiality_attested": True,
        "no_generative_ai_attested": True,
        "no_source_access_attested": True,
        "qualification": qualification,
    }
    _publish_json_marker_last(args.output, record)
    print(json.dumps({
        "status": "reviewer_record_written", "reviewer_id": args.reviewer_id,
        "output": str(args.output),
    }, sort_keys=True))


def _records_in(directory):
    directory = Path(directory)
    if not directory.is_dir():
        raise ReviewOperationsError("reviewer-record directory is missing")
    paths = sorted(directory.glob("*.json"))
    return [_load_published_json(path) for path in paths]


def _assemble_staffing(args):
    active = _records_in(args.active_dir)
    backups = [] if args.backup_dir is None else _records_in(args.backup_dir)
    staffing = {
        "schema_version": STAFFING_SCHEMA,
        "review_protocol_version": REVIEW_PROTOCOL_VERSION,
        "status": "ready",
        "active_reviewers": active,
        "backup_reviewers": backups,
    }
    validate_staffing(staffing)
    _publish_json_marker_last(args.output, staffing)
    print(json.dumps({
        "status": "ready", "active_reviewers": len(active),
        "backup_reviewers": len(backups), "output": str(args.output),
    }, sort_keys=True))


def _pilot_result_template(args):
    pilot = load_canonical_json(args.pilot)
    document = {
        "schema_version": PILOT_RESULT_SCHEMA,
        "pilot_sha256": digest_review_artifact(pilot),
        "status": "pending_completion",
        "case_count": 44,
        "judgment_count": 88,
        "median_review_seconds": None,
        "p90_review_seconds": None,
        "entry_errors": None,
        "exact_agreements": None,
        "disputes": None,
        "adjudications": None,
        "median_adjudication_seconds": None,
        "protocol_changed": None,
        "prompt_or_oracle_defects": None,
        "reliability_events": None,
        "global_escalation_triggered": None,
    }
    _write_json(args.output, document)
    print(json.dumps({
        "status": "template_written", "output": str(args.output),
    }, sort_keys=True))


def _validate_pilot(args):
    result = validate_pilot_result(
        load_canonical_json(args.pilot), load_canonical_json(args.result),
        frozen_review_bindings(),
    )
    print(json.dumps({
        "status": result["status"], "cases": result["case_count"],
        "judgments": result["judgment_count"],
    }, sort_keys=True))


def _build_pilot_result(args):
    pilot = load_canonical_json(args.pilot)
    assignments = load_canonical_json(args.assignments)
    manifests = _manifests()
    validate_assignments(assignments, manifests, selection=_selection())
    validate_pilot(
        pilot, assignments, manifests, frozen_review_bindings(), _selection()
    )
    submissions, errors = _load_submissions(args.submissions)
    if errors:
        raise ReviewOperationsError(
            "pilot result cannot seal with invalid submission files"
        )
    pilot_ids = {item["packet_id"] for item in pilot["records"]}
    if any(item["packet_id"] not in pilot_ids for item in submissions):
        raise ReviewOperationsError("pilot submission directory contains non-pilot cases")
    progress = build_progress(assignments, submissions, manifests=manifests)
    if (
        progress["sealed_reviewer_judgments"] != 88
        or progress["fully_double_reviewed_cases"] != 44
        or progress["disputes"] != progress["resolved_disputes"]
        or progress["duplicate_submissions"] != 0
    ):
        raise ReviewOperationsError("pilot submissions are not complete and resolved")
    selection = _selection()
    reviews = [item for item in submissions if item["role"] in ("primary", "secondary")]
    adjudications = [item for item in submissions if item["role"] == "adjudicator"]
    ledger = materialize_ledger(
        build_pending_ledger(manifests, selection), manifests, assignments,
        reviews, adjudications, selection,
    )
    pilot_instances = {item["instance_id"] for item in pilot["records"]}
    pilot_entries = [
        item for item in ledger["entries"] if item["instance_id"] in pilot_instances
    ]
    if any(item["status"] not in ("agreed", "adjudicated", "rejected") for item in pilot_entries):
        raise ReviewOperationsError("pilot has unresolved oracle-bound cases")
    defects = sum(item["status"] == "rejected" for item in pilot_entries)
    if defects != args.prompt_or_oracle_defects:
        raise ReviewOperationsError("declared pilot defects disagree with derived ledger")
    reliability_events = len(
        set(ledger["reliability_event_cases"]) & pilot_instances
    )
    result = {
        "schema_version": PILOT_RESULT_SCHEMA,
        "pilot_sha256": digest_review_artifact(pilot),
        "status": "complete_counted_toward_full_review",
        "case_count": 44,
        "judgment_count": 88,
        "median_review_seconds": progress["median_review_seconds"],
        "p90_review_seconds": progress["p90_review_seconds"],
        "entry_errors": args.entry_errors_observed,
        "exact_agreements": progress["exact_agreements"],
        "disputes": progress["disputes"],
        "adjudications": progress["resolved_disputes"],
        "median_adjudication_seconds": (
            progress["median_adjudication_seconds"] or 0
        ),
        "protocol_changed": not args.attest_no_protocol_change,
        "prompt_or_oracle_defects": defects,
        "reliability_events": reliability_events,
        "global_escalation_triggered": reliability_events >= 2,
    }
    validate_pilot_result(pilot, result, frozen_review_bindings())
    _write_json(args.output, result)
    print(json.dumps({
        "status": result["status"], "output": str(args.output),
    }, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--staffing", type=Path, default=DEFAULT_STAFFING)
    status.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    status.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    status.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    status.add_argument("--pilot-result", type=Path, default=DEFAULT_PILOT_RESULT)
    status.add_argument("--submissions", type=Path)
    status.set_defaults(handler=_status)

    assignments = commands.add_parser("init-assignments")
    assignments.add_argument("--staffing", type=Path, default=DEFAULT_STAFFING)
    assignments.add_argument("--output", type=Path, default=DEFAULT_ASSIGNMENTS)
    assignments.set_defaults(handler=_init_assignments)

    pilot = commands.add_parser("build-pilot")
    pilot.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    pilot.add_argument("--output", type=Path, default=DEFAULT_PILOT)
    pilot.set_defaults(handler=_build_pilot)

    for name, full in (("export-pilot", False), ("export-full", True)):
        export = commands.add_parser(name)
        export.add_argument("--staffing", type=Path, default=DEFAULT_STAFFING)
        export.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
        export.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
        export.add_argument("--pilot-result", type=Path, default=DEFAULT_PILOT_RESULT)
        export.add_argument("--output-dir", type=Path, required=True)
        export.set_defaults(handler=lambda args, full=full: _export(args, full))

    seal = commands.add_parser("seal-review")
    seal.add_argument("--bundle", type=Path, required=True)
    seal.add_argument("--packet-id", required=True)
    seal.add_argument("--reviewer-id", required=True)
    seal.add_argument("--role", choices=("primary", "secondary", "adjudicator"))
    seal.add_argument("--response", type=Path, required=True)
    seal.add_argument("--started-at", required=True)
    seal.add_argument("--sealed-at", required=True)
    seal.add_argument(
        "--attest", action="store_true",
        help="Attest identity, independence, no source access/AI/discussion",
    )
    seal.add_argument(
        "--attest-unseen", action="store_true",
        help="Adjudicator attests reviews and oracle were unseen before sealing",
    )
    seal.add_argument("--output", type=Path, required=True)
    seal.set_defaults(handler=_seal)

    adjudication = commands.add_parser("export-adjudication")
    adjudication.add_argument("--staffing", type=Path, default=DEFAULT_STAFFING)
    adjudication.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    adjudication.add_argument("--packet-id", required=True)
    adjudication.add_argument("--submissions", type=Path, required=True)
    adjudication.add_argument("--output", type=Path, required=True)
    adjudication.set_defaults(handler=_export_adjudication)

    escalation = commands.add_parser("export-escalation")
    escalation.add_argument("--staffing", type=Path, default=DEFAULT_STAFFING)
    escalation.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    escalation.add_argument("--submissions", type=Path, required=True)
    escalation.add_argument("--output-dir", type=Path, required=True)
    escalation.set_defaults(handler=_export_escalation)

    response_template = commands.add_parser("response-template")
    response_template.add_argument("--bundle", type=Path, required=True)
    response_template.add_argument("--packet-id", required=True)
    response_template.add_argument("--output", type=Path, required=True)
    response_template.set_defaults(handler=_response_template)

    qualification_template = commands.add_parser("qualification-template")
    qualification_template.add_argument("--output", type=Path, required=True)
    qualification_template.set_defaults(handler=_qualification_template)

    seal_qualification = commands.add_parser("seal-qualification")
    seal_qualification.add_argument("--reviewer-id", required=True)
    seal_qualification.add_argument("--responses", type=Path, required=True)
    seal_qualification.add_argument("--sealed-at", required=True)
    seal_qualification.add_argument("--attest", action="store_true")
    seal_qualification.add_argument("--output", type=Path, required=True)
    seal_qualification.set_defaults(handler=_seal_qualification)

    intake = commands.add_parser("intake")
    intake.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS)
    intake.add_argument("--submissions", type=Path, required=True)
    intake.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPTS)
    intake.add_argument("--output", type=Path, default=DEFAULT_MATERIALIZED_LEDGER)
    intake.set_defaults(handler=_intake)

    outcomes = commands.add_parser("compile-outcomes")
    outcomes.add_argument("--ledger", type=Path, default=DEFAULT_MATERIALIZED_LEDGER)
    outcomes.add_argument("--output", type=Path, default=DEFAULT_ADJUDICATED_OUTCOMES)
    outcomes.set_defaults(handler=_compile_outcomes)

    qualification = commands.add_parser("score-qualification")
    qualification.add_argument("--submission", type=Path, required=True)
    qualification.add_argument("--output", type=Path, required=True)
    qualification.add_argument("--roster-record", type=Path)
    qualification.set_defaults(handler=_qualification)

    reviewer_record = commands.add_parser("reviewer-record")
    reviewer_record.add_argument("--reviewer-id", required=True)
    reviewer_record.add_argument("--name", required=True)
    reviewer_record.add_argument("--qualification-result", type=Path, required=True)
    reviewer_record.add_argument(
        "--attest-all-roster-requirements", action="store_true",
    )
    reviewer_record.add_argument("--output", type=Path, required=True)
    reviewer_record.set_defaults(handler=_reviewer_record)

    staffing = commands.add_parser("assemble-staffing")
    staffing.add_argument("--active-dir", type=Path, required=True)
    staffing.add_argument("--backup-dir", type=Path)
    staffing.add_argument("--output", type=Path, default=DEFAULT_READY_STAFFING)
    staffing.set_defaults(handler=_assemble_staffing)

    pilot_template = commands.add_parser("pilot-result-template")
    pilot_template.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    pilot_template.add_argument("--output", type=Path, default=DEFAULT_PILOT_RESULT)
    pilot_template.set_defaults(handler=_pilot_result_template)

    validate_pilot = commands.add_parser("validate-pilot")
    validate_pilot.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    validate_pilot.add_argument("--result", type=Path, default=DEFAULT_PILOT_RESULT)
    validate_pilot.set_defaults(handler=_validate_pilot)

    build_pilot_result = commands.add_parser("build-pilot-result")
    build_pilot_result.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    build_pilot_result.add_argument(
        "--assignments", type=Path, default=DEFAULT_ASSIGNMENTS,
    )
    build_pilot_result.add_argument("--submissions", type=Path, required=True)
    build_pilot_result.add_argument(
        "--entry-errors-observed", type=int, default=0,
    )
    build_pilot_result.add_argument(
        "--prompt-or-oracle-defects", type=int, default=0,
    )
    build_pilot_result.add_argument(
        "--attest-no-protocol-change", action="store_true",
    )
    build_pilot_result.add_argument("--output", type=Path, default=DEFAULT_PILOT_RESULT)
    build_pilot_result.set_defaults(handler=_build_pilot_result)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()


__all__ = ["ReviewOperationsError", "build_progress", "frozen_review_bindings", "main"]
