"""Evidence extraction, resume, unmask, and release checks for the successor.

No function in this module calls a model.  A future authorized runner may use
these fail-closed transformations around the existing model transport.
"""

import copy
import datetime
import hashlib
import hmac
import json
from pathlib import Path
import re
import subprocess

from harness.evidence import EvidenceStore, validate_committed
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, sha256_bytes, validate_manifest

from .next_study_descriptive import REPORT_SCHEMA as DESCRIPTIVE_REPORT_SCHEMA
from .next_study_report import (
    FAILURE_TAXONOMY_SCHEMA, PROGRAM_BINDINGS_SCHEMA, RESOURCE_REPORT_SCHEMA,
    validate_study_report,
)

from .next_study_program import (
    BenchmarkLease, MAXIMUM_LOGICAL_CELLS, MAXIMUM_PHYSICAL_ATTEMPTS,
    execution_allowed, primary_mask_key_commitment,
    retry_decision, validate_authorization,
    validate_program_state,
)
from .next_study_schedule import (
    DESCRIPTIVE_SCHEDULE_SCHEMA, SCHEDULE_SCHEMA, validate_phase_schedule,
)
from .next_study_statistics import GRADE_LEDGER_SCHEMA, PROTOCOL_VERSION


PREFLIGHT_SCHEMA = "brick.next-study.preflight/1"
EXECUTION_CONTEXT_SCHEMA = "brick.next-study.execution-context/1"
ATTEMPT_RECORD_SCHEMA = "brick.next-study.attempt-record/2"
MASKED_LEDGER_SCHEMA = "brick.next-study.masked-grade-ledger/3"
RELEASE_ATTESTATION_SCHEMA = "brick.next-study.release-attestation/2"
RELEASE_ARCHIVE_SCHEMA = "brick.next-study.release-archive/1"
RECOVERY_ATTESTATION_SCHEMA = "brick.next-study.recovery-attestation/1"
PREFLIGHT_GATE_SCHEMA = "brick.next-study.preflight-gate-evidence/1"
PREFLIGHT_GATE_ARTIFACTS = {
    "construct_contract_complete": "construct_contract",
    "semantic_internal_validity_complete": "semantic_simulation",
    "independent_validated_outcomes_complete": "validated_outcomes",
    "grader_mutation_matrix_complete": "grader_mutation_audit",
    "grader_machine_conformance_complete": "grader_machine_conformance",
    "native_lenovo_preflight_passed": "native_preflight",
    "clean_checkout_reproduction_passed": "clean_checkout_reproduction",
}


class NextStudyRuntimeError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _sha256(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise NextStudyRuntimeError("%s must be lowercase SHA-256 hex" % label)
    return value


def _timestamp(value, label):
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise NextStudyRuntimeError("%s must be ISO-8601" % label)
    if parsed.utcoffset() is None:
        raise NextStudyRuntimeError("%s must include a timezone" % label)
    return parsed


def _mask_value(masking_key, label, value):
    _sha256(masking_key, "primary mask key")
    return hmac.new(
        bytes.fromhex(masking_key),
        (label + "|" + value).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _schedule_cells(schedule, phase=None, count=None):
    if (
        not isinstance(schedule, dict)
        or schedule.get("schema_version")
        not in (SCHEDULE_SCHEMA, DESCRIPTIVE_SCHEDULE_SCHEMA)
        or not isinstance(schedule.get("records"), list)
        or schedule.get("logical_cell_count") != len(schedule["records"])
        or phase is not None and schedule.get("phase") != phase
        or count is not None and schedule.get("logical_cell_count") != count
    ):
        raise NextStudyRuntimeError("successor schedule is invalid")
    cells = {item.get("logical_cell_id"): item for item in schedule["records"]}
    if len(cells) != len(schedule["records"]) or None in cells:
        raise NextStudyRuntimeError("successor schedule contains duplicate cells")
    return cells


def preflight(
    authorization, current_fingerprint, schedules, gate_evidence, lease,
):
    if set(schedules) != {"calibration", "sentinel", "primary", "descriptives"}:
        raise NextStudyRuntimeError("preflight schedules are incomplete")
    schedule_digests = {name: _digest(value) for name, value in schedules.items()}
    required_gates = set(PREFLIGHT_GATE_ARTIFACTS)
    if not isinstance(gate_evidence, dict) or set(gate_evidence) != required_gates:
        raise NextStudyRuntimeError("preflight gate evidence has unexpected keys")
    try:
        validate_authorization(authorization)
        for gate, artifact_name in PREFLIGHT_GATE_ARTIFACTS.items():
            evidence = gate_evidence[gate]
            if not isinstance(evidence, dict) or set(evidence) != {
                "schema_version", "status", "artifact_name",
                "artifact_sha256",
            }:
                raise NextStudyRuntimeError(
                    "preflight gate %s has unexpected evidence" % gate
                )
            if (
                evidence["schema_version"] != PREFLIGHT_GATE_SCHEMA
                or evidence["status"] != "sealed_pass"
                or evidence["artifact_name"] != artifact_name
                or evidence["artifact_sha256"]
                != authorization["artifact_digests"][artifact_name]
            ):
                raise NextStudyRuntimeError(
                    "preflight gate %s is not authorization-bound" % gate
                )
            _sha256(evidence["artifact_sha256"], "%s artifact" % gate)
        gates_pass = True
    except (KeyError, ValueError):
        gates_pass = False
    try:
        validate_authorization(authorization)
        if not isinstance(lease, BenchmarkLease):
            raise NextStudyRuntimeError("preflight requires an owned BenchmarkLease")
        lease.validate_held(authorization["authorization_sha256"])
        lease_pass = True
    except (KeyError, ValueError):
        lease_pass = False
    fingerprint_pass = execution_allowed(
        authorization, current_fingerprint, schedule_digests
    )
    return {
        "schema_version": PREFLIGHT_SCHEMA,
        "passed": gates_pass and lease_pass and fingerprint_pass,
        "all_offline_gates_passed": gates_pass,
        "machine_wide_lease_held": lease_pass,
        "fingerprint_and_schedules_match": fingerprint_pass,
        "research_catalog_closed": True,
        "plugin_entry_points_enumerated": False,
        "model_calls": 0,
    }


def validate_attempt_record(record, scheduled_cell):
    expected = {
        "schema_version", "logical_cell_id", "repeat", "trial_seed",
        "failure_origin", "retryable", "strict_success", "evidence_sha256",
        "grade_record_sha256", "marker_last_verified", "model_calls",
        "successful_reads", "successful_mutations", "generated_tokens_exact",
        "generated_tokens_lower_bound", "generated_tokens_upper_bound",
        "model_time_ms", "wall_time_ms",
    }
    if not isinstance(record, dict) or set(record) != expected:
        raise NextStudyRuntimeError("attempt record has unexpected keys")
    if record["schema_version"] != ATTEMPT_RECORD_SCHEMA:
        raise NextStudyRuntimeError("attempt record schema drifted")
    if record["logical_cell_id"] != scheduled_cell["logical_cell_id"]:
        raise NextStudyRuntimeError("attempt is not scheduled")
    if record["trial_seed"] != scheduled_cell["trial_seed"]:
        raise NextStudyRuntimeError("same-seed identity drifted")
    if type(record["repeat"]) is not int or record["repeat"] not in (0, 1):
        raise NextStudyRuntimeError("physical repeat must be zero or one")
    if record["failure_origin"] not in (
        "none", "model", "environment", "instrument",
    ):
        raise NextStudyRuntimeError("attempt failure origin is invalid")
    if type(record["retryable"]) is not bool:
        raise NextStudyRuntimeError("attempt retryable flag must be boolean")
    sentinel = scheduled_cell.get("phase") == "sentinel"
    if record["failure_origin"] in ("environment", "instrument") or sentinel:
        if record["strict_success"] is not None:
            raise NextStudyRuntimeError("ungraded or invalid attempt success must be null")
    elif type(record["strict_success"]) is not bool:
        raise NextStudyRuntimeError("valid/model attempt success must be boolean")
    if record["marker_last_verified"] is not True:
        raise NextStudyRuntimeError("attempt evidence lacks marker-last verification")
    for field in ("evidence_sha256", "grade_record_sha256"):
        _sha256(record[field], "attempt %s" % field)
    if record["failure_origin"] == "model" and record["retryable"]:
        raise NextStudyRuntimeError("model failures, including parser rejection, cannot retry")
    if record["retryable"] and (
        record["failure_origin"] != "environment" or record["repeat"] != 0
    ):
        raise NextStudyRuntimeError("only initial environment failures may be retryable")
    if record["failure_origin"] == "none" and record["retryable"]:
        raise NextStudyRuntimeError("successful attempts cannot be retryable")
    for field in (
        "model_calls", "successful_reads", "successful_mutations",
        "model_time_ms", "wall_time_ms",
    ):
        if type(record[field]) is not int or record[field] < 0:
            raise NextStudyRuntimeError("attempt resource field is invalid")
    exact = record["generated_tokens_exact"]
    lower = record["generated_tokens_lower_bound"]
    upper = record["generated_tokens_upper_bound"]
    if exact is None:
        if (
            type(lower) is not int or lower < 0
            or upper is not None and (type(upper) is not int or upper < lower)
        ):
            raise NextStudyRuntimeError("attempt token bounds are invalid")
    elif (
        type(exact) is not int or exact < 0 or lower is not None or upper is not None
    ):
        raise NextStudyRuntimeError("exact tokens cannot be mixed with bounds")
    return record


def _resource_metrics(result, actions):
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    diagnostics = (
        result.get("diagnostics")
        if isinstance(result.get("diagnostics"), dict)
        else {}
    )
    ledger = diagnostics.get("ledger") if isinstance(diagnostics.get("ledger"), dict) else {}
    actions = actions if isinstance(actions, list) else []
    model_calls = metrics.get("model_calls", ledger.get("model_calls", 0))
    reads = sum(
        item.get("ok") is True and item.get("tool") in (
            "read_email", "list_emails", "list_events", "read_spreadsheet",
            "recall_memories",
        )
        for item in actions if isinstance(item, dict)
    )
    mutations = sum(
        item.get("ok") is True and item.get("tool") in (
            "send_email", "add_event", "send_message", "set_reminder",
            "create_presentation", "create_spreadsheet", "save_memory",
        )
        for item in actions if isinstance(item, dict)
    )
    exact_flag = ledger.get("generated_tokens_exact")
    tokens = metrics.get("generated_tokens")
    if exact_flag is True and type(tokens) is int and tokens >= 0:
        exact, lower, upper = tokens, None, None
    else:
        exact = None
        lower = ledger.get("generated_tokens_lower_bound", 0)
        upper = ledger.get("generated_tokens_upper_bound", 6144)
    def milliseconds(ms_key, seconds_key):
        value = metrics.get(ms_key)
        if type(value) is int and value >= 0:
            return value
        seconds = metrics.get(seconds_key, 0)
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds >= 0:
            return int(round(seconds * 1000))
        return 0
    return {
        "model_calls": model_calls if type(model_calls) is int and model_calls >= 0 else 0,
        "successful_reads": reads,
        "successful_mutations": mutations,
        "generated_tokens_exact": exact,
        "generated_tokens_lower_bound": lower,
        "generated_tokens_upper_bound": upper,
        "model_time_ms": milliseconds("model_time_ms", "model_time_seconds"),
        "wall_time_ms": milliseconds("wall_time_ms", "wall_time_seconds"),
    }


def seal_recovery_attestation(
    logical_cell_id, evidence_record_sha256, authorization_sha256,
    cooldown_seconds, attested_at,
):
    _sha256(logical_cell_id, "recovery logical cell")
    _sha256(evidence_record_sha256, "recovery evidence record")
    _sha256(authorization_sha256, "recovery authorization")
    if type(cooldown_seconds) is not int or cooldown_seconds < 1:
        raise NextStudyRuntimeError("recovery cooldown must be a positive integer")
    _timestamp(attested_at, "recovery attestation time")
    document = {
        "schema_version": RECOVERY_ATTESTATION_SCHEMA,
        "logical_cell_id": logical_cell_id,
        "repeat": 0,
        "evidence_record_sha256": evidence_record_sha256,
        "authorization_sha256": authorization_sha256,
        "cooldown_seconds": cooldown_seconds,
        "health_verified": True,
        "same_seed_available": True,
        "attested_at": attested_at,
    }
    document["attestation_sha256"] = _digest(document)
    return document


def _validate_recovery_attestation(document):
    expected = {
        "schema_version", "logical_cell_id", "repeat",
        "evidence_record_sha256", "authorization_sha256",
        "cooldown_seconds", "health_verified", "same_seed_available",
        "attested_at", "attestation_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyRuntimeError("recovery attestation has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("attestation_sha256")
    _sha256(supplied, "recovery attestation digest")
    if supplied != _digest(unsigned):
        raise NextStudyRuntimeError("recovery attestation digest drifted")
    rebuilt = seal_recovery_attestation(
        document["logical_cell_id"], document["evidence_record_sha256"],
        document["authorization_sha256"], document["cooldown_seconds"],
        document["attested_at"],
    )
    if rebuilt != document:
        raise NextStudyRuntimeError("recovery attestation semantics drifted")
    return document


def extract_attempt_records(
    evidence_store, schedule, recovery_attestations=(), authorization_sha256=None,
):
    """Derive successor attempt records from marker-last committed evidence."""

    if not isinstance(evidence_store, EvidenceStore):
        raise NextStudyRuntimeError("attempt extraction requires an EvidenceStore")
    scheduled = _schedule_cells(schedule)
    coordinate_map = {}
    for logical_id, cell in scheduled.items():
        key = (cell["instance_id"], cell["condition"], cell["trial_seed"])
        if key in coordinate_map:
            raise NextStudyRuntimeError("schedule sampling coordinates are ambiguous")
        coordinate_map[key] = (logical_id, cell)
    attestation_by_cell = {}
    for attestation in recovery_attestations:
        _validate_recovery_attestation(attestation)
        logical_id = attestation["logical_cell_id"]
        if logical_id in attestation_by_cell or logical_id not in scheduled:
            raise NextStudyRuntimeError("recovery attestation is duplicate or unscheduled")
        if authorization_sha256 is None or attestation["authorization_sha256"] != authorization_sha256:
            raise NextStudyRuntimeError("recovery attestation authorization drifted")
        attestation_by_cell[logical_id] = attestation
    projection = evidence_store.read_committed()
    if (
        not isinstance(projection, dict)
        or projection.get("schema_version") != "brick.evidence-results/1"
        or not isinstance(projection.get("records"), list)
    ):
        raise NextStudyRuntimeError("evidence projection schema drifted")
    extracted, seen = [], set()
    for committed in projection["records"]:
        key = committed.get("attempt_key")
        try:
            coordinate = (
                key["instance"]["id"], key["condition"]["name"],
                key["sampling"]["seed"],
            )
            repeat = key["repeat"]
            model_digest = key["model"]["digest"]
        except (KeyError, TypeError):
            raise NextStudyRuntimeError("committed attempt key is incomplete")
        match = coordinate_map.get(coordinate)
        if match is None:
            raise NextStudyRuntimeError("committed evidence is unscheduled")
        logical_id, cell = match
        expected_model_digest = cell.get(
            "model_sha256", schedule.get("model_sha256")
        )
        _sha256(expected_model_digest, "scheduled model digest")
        if model_digest != "sha256:" + expected_model_digest:
            raise NextStudyRuntimeError("committed model digest drifted")
        if key["instance"].get("content_sha256") != cell["content_sha256"]:
            raise NextStudyRuntimeError("committed instance binding drifted")
        identity = (logical_id, repeat)
        if identity in seen:
            raise NextStudyRuntimeError("committed physical attempt is duplicated")
        seen.add(identity)
        # The immutable evidence projection may contain measured durations and
        # diagnostic fractions. Hash those canonical bytes explicitly rather
        # than pretending the upstream evidence schema is integer-only.
        evidence_digest = sha256_bytes(
            canonical_json_bytes(committed, allow_float=True)
        )
        raw_origin = committed.get("failure_origin")
        grader_status = committed.get("grader_status")
        sentinel_ungraded = (
            schedule.get("phase") == "sentinel" and grader_status == "not_run"
        )
        if raw_origin in ("runner", "operator") or (
            grader_status != "graded" and not sentinel_ungraded
        ):
            origin = "instrument"
        elif raw_origin in ("none", "model", "environment"):
            origin = raw_origin
        else:
            raise NextStudyRuntimeError("committed failure origin is unsupported")
        attestation = attestation_by_cell.get(logical_id)
        retryable = False
        if attestation is not None:
            if origin != "environment" or repeat != 0:
                raise NextStudyRuntimeError("recovery attestation targets an ineligible attempt")
            if attestation["evidence_record_sha256"] != evidence_digest:
                raise NextStudyRuntimeError("recovery attestation evidence drifted")
            retryable = True
        strict_success = committed.get("strict_success")
        if origin in ("environment", "instrument") or sentinel_ungraded:
            strict_success = None
        record = {
            "schema_version": ATTEMPT_RECORD_SCHEMA,
            "logical_cell_id": logical_id,
            "repeat": repeat,
            "trial_seed": cell["trial_seed"],
            "failure_origin": origin,
            "retryable": retryable,
            "strict_success": strict_success,
            "evidence_sha256": evidence_digest,
            "grade_record_sha256": sha256_bytes(
                canonical_json_bytes(committed.get("grade"), allow_float=True)
            ),
            "marker_last_verified": True,
        }
        candidate = (
            evidence_store.attempts_dir
            / committed["logical_hash"]
            / committed["physical_uuid"]
        )
        validated = validate_committed(
            candidate,
            expected_run={
                "run_id": evidence_store.run_id,
                "run_sha256": evidence_store.run_sha256,
            },
        )
        semantic = validated["semantic"]
        if semantic["key"].to_dict() != key:
            raise NextStudyRuntimeError(
                "committed evidence changed after projection validation"
            )
        record.update(
            _resource_metrics(
                semantic["result"], semantic["actions"]["actions"]
            )
        )
        validate_attempt_record(record, cell)
        extracted.append(record)
    unused = set(attestation_by_cell) - {item["logical_cell_id"] for item in extracted}
    if unused:
        raise NextStudyRuntimeError("recovery attestation has no committed evidence")
    return sorted(extracted, key=lambda item: (item["logical_cell_id"], item["repeat"]))


def resume_queue(schedule, attempts):
    scheduled = _schedule_cells(schedule)
    by_cell = {}
    for record in attempts:
        cell = scheduled.get(record.get("logical_cell_id"))
        if cell is None:
            raise NextStudyRuntimeError("attempt references an unscheduled cell")
        validate_attempt_record(record, cell)
        key = (record["logical_cell_id"], record["repeat"])
        if key in by_cell:
            raise NextStudyRuntimeError("physical attempt is duplicated")
        by_cell[key] = record
    if len(attempts) > min(schedule["maximum_physical_attempts"], MAXIMUM_PHYSICAL_ATTEMPTS):
        raise NextStudyRuntimeError("physical-attempt ceiling exceeded")
    queue = []
    for logical_id, cell in scheduled.items():
        first = by_cell.get((logical_id, 0))
        second = by_cell.get((logical_id, 1))
        if first is None:
            if second is not None:
                raise NextStudyRuntimeError("recovery attempt exists without repeat zero")
            queue.append({"logical_cell_id": logical_id, "repeat": 0})
            continue
        eligible = retry_decision({
            "repeat": first["repeat"],
            "failure_origin": first["failure_origin"],
            "retryable": first["retryable"],
            "same_seed_available": first["trial_seed"] == cell["trial_seed"],
        })["eligible"]
        if eligible and second is None:
            queue.append({"logical_cell_id": logical_id, "repeat": 1})
        elif not eligible and second is not None:
            raise NextStudyRuntimeError("ineligible cell has a recovery attempt")
    return queue


def build_masked_grade_ledger(
    schedule, attempts, retained_manifest, sealed_at, masking_key,
    expected_mask_key_commitment=None,
    execution_context="authorized_research",
):
    try:
        validate_phase_schedule(schedule, retained_manifest)
    except ValueError as exc:
        raise NextStudyRuntimeError(str(exc))
    if schedule["phase"] != "primary" or schedule["logical_cell_count"] != 880:
        raise NextStudyRuntimeError("masked grade ledger requires the primary schedule")
    if resume_queue(schedule, attempts):
        raise NextStudyRuntimeError("primary attempts are incomplete")
    commitment = primary_mask_key_commitment(masking_key)
    if (
        expected_mask_key_commitment is not None
        and commitment != expected_mask_key_commitment
    ):
        raise NextStudyRuntimeError("primary mask key differs from authorization")
    by_cell = {}
    for attempt in attempts:
        by_cell.setdefault(attempt["logical_cell_id"], []).append(attempt)
    records = []
    for cell in schedule["records"]:
        candidates = sorted(by_cell[cell["logical_cell_id"]], key=lambda item: item["repeat"])
        final = candidates[-1]
        if final["failure_origin"] in ("environment", "instrument"):
            raise NextStudyRuntimeError("invalid primary cell cannot be sealed")
        records.append({
            "masked_cell_id": _mask_value(
                masking_key, "logical-cell", cell["logical_cell_id"]
            ),
            "repeat": final["repeat"],
            "evidence_commitment": _mask_value(
                masking_key, "evidence", final["evidence_sha256"]
            ),
            "grade_record_commitment": _mask_value(
                masking_key, "grade", final["grade_record_sha256"]
            ),
            "outcome_origin": (
                "model_terminal_failure" if final["failure_origin"] == "model"
                else "completed"
            ),
            "strict_success": final["strict_success"],
        })
    _timestamp(sealed_at, "masked grade-ledger seal time")
    return {
        "schema_version": MASKED_LEDGER_SCHEMA,
        "execution_context": {
            "schema_version": EXECUTION_CONTEXT_SCHEMA,
            "value": execution_context,
        },
        "protocol_version": PROTOCOL_VERSION,
        "status": "sealed_complete_masked",
        "cell_count": 880,
        "schedule_sha256": _digest(schedule),
        "mask_key_commitment": commitment,
        "sealed_at": sealed_at,
        "records": sorted(records, key=lambda item: item["masked_cell_id"]),
    }


def unmask_primary(
    masked_ledger, schedule, retained_manifest, attempts, masking_key, sealed_at,
):
    validate_manifest(retained_manifest)
    if retained_manifest["split"] != "retained":
        raise NextStudyRuntimeError("unmask requires retained manifest")
    try:
        validate_phase_schedule(schedule, retained_manifest)
    except ValueError as exc:
        raise NextStudyRuntimeError(str(exc))
    expected_ledger_keys = {
        "schema_version", "protocol_version", "status", "cell_count",
        "schedule_sha256", "mask_key_commitment", "sealed_at", "records",
        "execution_context",
    }
    if not isinstance(masked_ledger, dict) or set(masked_ledger) != expected_ledger_keys:
        raise NextStudyRuntimeError("masked primary ledger has unexpected keys")
    if (
        masked_ledger["schema_version"] != MASKED_LEDGER_SCHEMA
        or masked_ledger["protocol_version"] != PROTOCOL_VERSION
        or masked_ledger["status"] != "sealed_complete_masked"
        or masked_ledger["cell_count"] != 880
        or masked_ledger["schedule_sha256"] != _digest(schedule)
        or not isinstance(masked_ledger["records"], list)
        or len(masked_ledger["records"]) != 880
    ):
        raise NextStudyRuntimeError("primary ledger is not sealed for unmasking")
    if masked_ledger["mask_key_commitment"] != primary_mask_key_commitment(masking_key):
        raise NextStudyRuntimeError("primary mask key commitment drifted")
    context = masked_ledger["execution_context"]
    if (
        not isinstance(context, dict)
        or set(context) != {"schema_version", "value"}
        or context["schema_version"] != EXECUTION_CONTEXT_SCHEMA
        or context["value"] not in ("authorized_research", "synthetic_rehearsal")
    ):
        raise NextStudyRuntimeError("masked ledger execution context drifted")
    _timestamp(masked_ledger["sealed_at"], "masked ledger seal time")
    _timestamp(sealed_at, "unmasked grade-ledger seal time")
    scheduled = _schedule_cells(schedule, "primary", 880)
    masked_record_keys = {
        "masked_cell_id", "repeat", "evidence_commitment",
        "grade_record_commitment", "outcome_origin", "strict_success",
    }
    if resume_queue(schedule, attempts):
        raise NextStudyRuntimeError("unmask requires complete primary attempts")
    by_cell = {}
    for attempt in attempts:
        by_cell.setdefault(attempt["logical_cell_id"], []).append(attempt)
    final_attempts = {
        logical_id: max(values, key=lambda item: item["repeat"])
        for logical_id, values in by_cell.items()
    }
    masked_to_cell = {
        _mask_value(masking_key, "logical-cell", logical_id): cell
        for logical_id, cell in scheduled.items()
    }
    if len(masked_to_cell) != 880:
        raise NextStudyRuntimeError("primary mask produced duplicate cell identifiers")
    records = []
    seen = set()
    for masked in masked_ledger["records"]:
        if not isinstance(masked, dict) or set(masked) != masked_record_keys:
            raise NextStudyRuntimeError("masked primary record drifted")
        cell = masked_to_cell.get(masked["masked_cell_id"])
        logical_id = cell["logical_cell_id"] if cell is not None else None
        if cell is None or logical_id in seen:
            raise NextStudyRuntimeError("masked record is duplicate or unscheduled")
        final = final_attempts.get(logical_id)
        if final is None:
            raise NextStudyRuntimeError("masked record lacks sealed attempt evidence")
        if type(masked["repeat"]) is not int or masked["repeat"] not in (0, 1):
            raise NextStudyRuntimeError("masked recovery repeat is invalid")
        for field in ("masked_cell_id", "evidence_commitment", "grade_record_commitment"):
            _sha256(masked[field], "masked record commitment")
        if masked["outcome_origin"] not in ("completed", "model_terminal_failure"):
            raise NextStudyRuntimeError("masked outcome origin is invalid")
        if type(masked["strict_success"]) is not bool:
            raise NextStudyRuntimeError("masked strict success must be boolean")
        if masked["outcome_origin"] == "model_terminal_failure" and masked["strict_success"]:
            raise NextStudyRuntimeError("model terminal failure cannot succeed")
        expected_origin = (
            "model_terminal_failure" if final["failure_origin"] == "model"
            else "completed"
        )
        if (
            masked["repeat"] != final["repeat"]
            or masked["strict_success"] is not final["strict_success"]
            or masked["outcome_origin"] != expected_origin
            or masked["evidence_commitment"]
            != _mask_value(masking_key, "evidence", final["evidence_sha256"])
            or masked["grade_record_commitment"]
            != _mask_value(masking_key, "grade", final["grade_record_sha256"])
        ):
            raise NextStudyRuntimeError("masked record differs from sealed attempt evidence")
        seen.add(logical_id)
        records.append({
            "instance_id": cell["instance_id"],
            "content_sha256": cell["content_sha256"],
            "family": cell["family"],
            "condition": cell["condition"],
            "trial_index": cell["trial_index"],
            "trial_seed": cell["trial_seed"],
            "attempt_key": {
                "instance_id": cell["instance_id"],
                "condition": cell["condition"],
                "trial_index": cell["trial_index"],
                "repeat": masked["repeat"],
            },
            "evidence_sha256": final["evidence_sha256"],
            "grade_record_sha256": final["grade_record_sha256"],
            "outcome_origin": masked["outcome_origin"],
            "strict_success": masked["strict_success"],
        })
    if seen != set(scheduled):
        raise NextStudyRuntimeError("masked primary ledger is incomplete")
    return {
        "schema_version": GRADE_LEDGER_SCHEMA,
        "execution_context": copy.deepcopy(context),
        "generator_version": retained_manifest["generator_version"],
        "protocol_version": PROTOCOL_VERSION,
        "split": "retained",
        "status": "sealed_complete",
        "cell_count": 880,
        "schedule_sha256": _digest(schedule),
        "sealed_at": sealed_at,
        "records": records,
    }


def build_release_archive_manifest(
    project_root, authorization, archived_commit, artifact_paths,
):
    root = Path(project_root).resolve()
    validate_authorization(authorization)
    required = {
        "authorization",
        "calibration", "sentinel", "masked_primary_ledger",
        "primary_grade_ledger", "primary_analysis", "descriptives",
        "resource_report", "failure_taxonomy", "program_bindings",
        "study_report", "program_state",
    }
    if set(artifact_paths) != required:
        raise NextStudyRuntimeError("release archive paths have unexpected keys")
    if re.fullmatch(r"[0-9a-f]{40}", archived_commit or "") is None:
        raise NextStudyRuntimeError("archived commit is invalid")
    artifacts, bindings = [], {}
    for name, relative in sorted(artifact_paths.items()):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise NextStudyRuntimeError("release archive path escapes project root")
        if not path.is_file():
            raise NextStudyRuntimeError("release archive artifact is missing")
        payload = path.read_bytes()
        try:
            committed = subprocess.run(
                ["git", "show", archived_commit + ":" + str(relative).replace("\\", "/")],
                cwd=str(root), check=True, capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            raise NextStudyRuntimeError(
                "release archive artifact is not present in archived commit"
            )
        if committed != payload:
            raise NextStudyRuntimeError(
                "release archive artifact differs from archived commit"
            )
        digest = sha256_bytes(payload)
        bindings[name] = digest
        artifacts.append({"name": name, "path": str(relative).replace("\\", "/"), "sha256": digest})
    document = {
        "schema_version": RELEASE_ARCHIVE_SCHEMA,
        "execution_context": copy.deepcopy(authorization["execution_context"]),
        "authorization_sha256": authorization["authorization_sha256"],
        "archived_commit": archived_commit,
        "artifacts": artifacts,
        "bindings": bindings,
        "study_report_sha256": bindings["study_report"],
    }
    try:
        archived_authorization = load_canonical_json(
            root / next(
                item["path"] for item in artifacts
                if item["name"] == "authorization"
            )
        )
    except (OSError, ValueError, json.JSONDecodeError, StopIteration):
        raise NextStudyRuntimeError("release archive authorization is invalid")
    if archived_authorization != authorization:
        raise NextStudyRuntimeError(
            "release archive authorization differs from supplied authorization"
        )
    document["archive_sha256"] = _digest(document)
    return document


def verify_release(
    project_root, authorization, program_state, archive_manifest,
    annotated_tag="v0.14.0",
):
    """Verify real archive bytes, authorization bindings, and annotated Git tag."""

    root = Path(project_root).resolve()
    try:
        validate_authorization(authorization)
    except ValueError as exc:
        raise NextStudyRuntimeError(str(exc))
    try:
        validate_program_state(program_state)
    except ValueError as exc:
        raise NextStudyRuntimeError(str(exc))
    if (
        program_state.get("status") != "ready"
        or program_state.get("completed_phases")
        != [
            "calibration", "sentinel", "primary", "primary_analysis",
            "descriptives",
        ]
        or program_state.get("current_phase") != "release"
        or program_state.get("primary_claim_sealed") is not True
    ):
        raise NextStudyRuntimeError("program is not ready for the release gate")
    if program_state["authorization_sha256"] != authorization["authorization_sha256"]:
        raise NextStudyRuntimeError("release state authorization drifted")
    if authorization["execution_context"]["value"] != "authorized_research":
        raise NextStudyRuntimeError("synthetic rehearsal cannot be released")
    if annotated_tag != "v0.14.0":
        raise NextStudyRuntimeError("completed study release must be v0.14.0")
    expected_manifest_keys = {
        "schema_version", "execution_context", "authorization_sha256",
        "archived_commit", "artifacts", "bindings", "study_report_sha256",
        "archive_sha256",
    }
    if not isinstance(archive_manifest, dict) or set(archive_manifest) != expected_manifest_keys:
        raise NextStudyRuntimeError("release archive manifest has unexpected keys")
    unsigned = dict(archive_manifest)
    supplied_archive_digest = unsigned.pop("archive_sha256")
    if supplied_archive_digest != _digest(unsigned):
        raise NextStudyRuntimeError("release archive manifest digest drifted")
    if (
        archive_manifest["schema_version"] != RELEASE_ARCHIVE_SCHEMA
        or archive_manifest["execution_context"] != authorization["execution_context"]
        or archive_manifest["authorization_sha256"] != authorization["authorization_sha256"]
        or re.fullmatch(r"[0-9a-f]{40}", archive_manifest["archived_commit"] or "") is None
    ):
        raise NextStudyRuntimeError("release archive authorization binding drifted")
    required_bindings = {
        "authorization",
        "calibration", "sentinel", "masked_primary_ledger",
        "primary_grade_ledger", "primary_analysis", "descriptives",
        "resource_report", "failure_taxonomy", "program_bindings",
        "study_report", "program_state",
    }
    if not isinstance(archive_manifest["bindings"], dict) or set(archive_manifest["bindings"]) != required_bindings:
        raise NextStudyRuntimeError("release archive cross-bindings drifted")
    artifacts = archive_manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise NextStudyRuntimeError("release archive artifact list is empty")
    actual = {}
    documents = {}
    for item in artifacts:
        if not isinstance(item, dict) or set(item) != {"name", "path", "sha256"}:
            raise NextStudyRuntimeError("release archive artifact entry drifted")
        if item["name"] in actual or item["name"] not in required_bindings:
            raise NextStudyRuntimeError("release archive artifact names drifted")
        path = (root / item["path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise NextStudyRuntimeError("release archive path escapes project root")
        if not path.is_file():
            raise NextStudyRuntimeError("release archive artifact is missing")
        digest = sha256_bytes(path.read_bytes())
        if digest != item["sha256"] or archive_manifest["bindings"][item["name"]] != digest:
            raise NextStudyRuntimeError("release archive artifact bytes drifted")
        actual[item["name"]] = digest
        try:
            committed = subprocess.run(
                [
                    "git", "show",
                    archive_manifest["archived_commit"] + ":" + item["path"],
                ],
                cwd=str(root), check=True, capture_output=True,
            ).stdout
        except (OSError, subprocess.CalledProcessError):
            raise NextStudyRuntimeError(
                "release archive artifact is not present in archived commit"
            )
        if committed != path.read_bytes():
            raise NextStudyRuntimeError(
                "release archive artifact differs from archived commit"
            )
        try:
            documents[item["name"]] = load_canonical_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            raise NextStudyRuntimeError("release archive artifact is not canonical JSON")
    if set(actual) != required_bindings:
        raise NextStudyRuntimeError("release archive artifact set is incomplete")
    if documents["authorization"] != authorization:
        raise NextStudyRuntimeError("archived authorization differs from release input")
    if archive_manifest["study_report_sha256"] != actual["study_report"]:
        raise NextStudyRuntimeError("study report release binding drifted")
    if documents["program_state"] != program_state:
        raise NextStudyRuntimeError("archived program state differs from release state")
    gates = {gate["phase"]: gate for gate in program_state["sealed_phase_gates"]}
    phase_artifacts = {
        "calibration": "calibration",
        "sentinel": "sentinel",
        "primary": "masked_primary_ledger",
        "primary_analysis": "primary_analysis",
        "descriptives": "descriptives",
    }
    if any(
        gates[phase]["sealed_artifact_sha256"] != _digest(documents[name])
        for phase, name in phase_artifacts.items()
    ):
        raise NextStudyRuntimeError("archived artifact differs from sealed phase gate")
    masked = documents["masked_primary_ledger"]
    grade = documents["primary_grade_ledger"]
    analysis = documents["primary_analysis"]
    descriptives = documents["descriptives"]
    if (
        masked.get("schema_version") != MASKED_LEDGER_SCHEMA
        or masked.get("status") != "sealed_complete_masked"
        or masked.get("schedule_sha256")
        != authorization["schedule_digests"]["primary"]
        or grade.get("schema_version") != GRADE_LEDGER_SCHEMA
        or grade.get("status") != "sealed_complete"
        or grade.get("schedule_sha256")
        != authorization["schedule_digests"]["primary"]
        or analysis.get("schema_version") != "brick.next-study.primary-analysis/3"
        or analysis.get("primary_grade_ledger_sha256") != _digest(grade)
        or analysis.get("primary_schedule_sha256")
        != authorization["schedule_digests"]["primary"]
        or descriptives.get("schema_version") != DESCRIPTIVE_REPORT_SCHEMA
        or descriptives.get("status") != "complete"
        or descriptives.get("primary_grade_ledger_sha256") != _digest(grade)
        or descriptives.get("selection_sha256")
        != authorization["descriptive_selection_sha256"]
    ):
        raise NextStudyRuntimeError("release archive semantic bindings drifted")
    descriptive_unsigned = dict(descriptives)
    descriptive_digest = descriptive_unsigned.pop("descriptive_report_sha256", None)
    if descriptive_digest != _digest(descriptive_unsigned):
        raise NextStudyRuntimeError("archived descriptive report digest drifted")
    resource = documents["resource_report"]
    resource_unsigned = dict(resource)
    resource_digest = resource_unsigned.pop("resource_report_sha256", None)
    taxonomy = documents["failure_taxonomy"]
    taxonomy_unsigned = dict(taxonomy)
    taxonomy_digest = taxonomy_unsigned.pop("failure_taxonomy_sha256", None)
    bindings = documents["program_bindings"]
    bindings_unsigned = dict(bindings)
    bindings_digest = bindings_unsigned.pop("program_bindings_sha256", None)
    if (
        resource.get("schema_version") != RESOURCE_REPORT_SCHEMA
        or resource_digest != _digest(resource_unsigned)
        or resource.get("descriptive_report_sha256") != descriptive_digest
        or taxonomy.get("schema_version") != FAILURE_TAXONOMY_SCHEMA
        or taxonomy_digest != _digest(taxonomy_unsigned)
        or taxonomy.get("primary_grade_ledger_sha256") != _digest(grade)
        or bindings.get("schema_version") != PROGRAM_BINDINGS_SCHEMA
        or bindings_digest != _digest(bindings_unsigned)
        or bindings.get("authorization_sha256")
        != authorization["authorization_sha256"]
        or bindings.get("phase_gate_history_sha256")
        != _digest(program_state["sealed_phase_gates"])
    ):
        raise NextStudyRuntimeError("release report support artifacts drifted")
    try:
        study = validate_study_report(documents["study_report"])
    except ValueError as exc:
        raise NextStudyRuntimeError(str(exc))
    if (
        study.get("primary_analysis_sha256") != _digest(analysis)
        or study.get("descriptive_report_sha256") != _digest(descriptives)
        or study.get("manifest_lock_sha256")
        != authorization["artifact_digests"]["manifest_lock"]
        or study.get("resource_report_sha256") != resource_digest
        or study.get("failure_taxonomy", {}).get("failure_taxonomy_sha256")
        != taxonomy_digest
        or study.get("program_bindings", {}).get("program_bindings_sha256")
        != bindings_digest
    ):
        raise NextStudyRuntimeError("study report cross-bindings drifted")
    try:
        instrument_tag_type = subprocess.run(
            ["git", "cat-file", "-t", "refs/tags/" + authorization["tag"]],
            cwd=str(root), check=True, capture_output=True, text=True,
        ).stdout.strip()
        instrument_tag_object = subprocess.run(
            ["git", "rev-parse", "refs/tags/" + authorization["tag"]],
            cwd=str(root), check=True, capture_output=True, text=True,
        ).stdout.strip()
        instrument_peeled = subprocess.run(
            ["git", "rev-parse", authorization["tag"] + "^{}"],
            cwd=str(root), check=True, capture_output=True, text=True,
        ).stdout.strip()
        tag_type = subprocess.run(
            ["git", "cat-file", "-t", "refs/tags/" + annotated_tag],
            cwd=str(root), check=True, capture_output=True, text=True,
        ).stdout.strip()
        peeled = subprocess.run(
            ["git", "rev-parse", annotated_tag + "^{}"],
            cwd=str(root), check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        raise NextStudyRuntimeError("annotated release tag is missing or invalid")
    if (
        instrument_tag_type != "tag"
        or instrument_tag_object != authorization["tag_object_sha"]
        or instrument_peeled != authorization["commit_sha"]
    ):
        raise NextStudyRuntimeError(
            "instrument tag does not match the archived authorization"
        )
    if tag_type != "tag" or peeled != archive_manifest["archived_commit"]:
        raise NextStudyRuntimeError("release tag does not peel to archived commit")
    return {
        "schema_version": RELEASE_ATTESTATION_SCHEMA,
        "status": "verified",
        "annotated_tag": annotated_tag,
        "authorization_sha256": authorization["authorization_sha256"],
        "archived_commit": archive_manifest["archived_commit"],
        "archive_sha256": archive_manifest["archive_sha256"],
        "study_report_sha256": archive_manifest["study_report_sha256"],
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


__all__ = [
    "ATTEMPT_RECORD_SCHEMA", "EXECUTION_CONTEXT_SCHEMA", "MASKED_LEDGER_SCHEMA",
    "RELEASE_ARCHIVE_SCHEMA", "NextStudyRuntimeError",
    "PREFLIGHT_GATE_ARTIFACTS", "PREFLIGHT_GATE_SCHEMA",
    "RECOVERY_ATTESTATION_SCHEMA", "build_masked_grade_ledger",
    "build_release_archive_manifest",
    "extract_attempt_records", "preflight", "resume_queue",
    "seal_recovery_attestation",
    "unmask_primary", "validate_attempt_record", "verify_release",
]
