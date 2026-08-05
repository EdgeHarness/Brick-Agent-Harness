"""Fail-closed authorization and phase controls for the successor program.

The module intentionally provides no implicit authorization and performs no
model calls.  Research catalogs are closed constants and never enumerate Python
entry points; product plugin discovery belongs outside this module.
"""

import copy
from collections import Counter
import datetime
import os
from pathlib import Path
import re
import socket
import tempfile

from harness.evidence import canonical_json_bytes
from harness.instances import sha256_bytes
from domains.office_demo.generators_v2 import FAMILIES

from .next_study_statistics import PROTOCOL_VERSION


AUTHORIZATION_SCHEMA = "brick.next-study.program-authorization/2"
EXECUTION_CONTEXT_SCHEMA = "brick.next-study.execution-context/1"
PROGRAM_STATE_SCHEMA = "brick.next-study.program-state/2"
LEASE_SCHEMA = "brick.next-study.machine-lease/1"
SEALED_GATE_SCHEMA = "brick.next-study.sealed-phase-gate/1"
HOST_FINGERPRINT_SCHEMA = "brick.next-study.host-fingerprint/1"
RUNTIME_FINGERPRINT_SCHEMA = "brick.next-study.runtime-fingerprint/1"
MAXIMUM_LOGICAL_CELLS = 1542
MAXIMUM_PHYSICAL_ATTEMPTS = 3084
PHASES = (
    "calibration", "sentinel", "primary", "primary_analysis",
    "descriptives", "release",
)
RESEARCH_DOMAINS = ("office_demo",)
RESEARCH_CONDITIONS = (
    "native_tools", "harness_full", "raw_json", "harness_no_plan",
    "harness_no_recovery", "harness_no_completion_guard",
    "harness_no_memory", "native_equal_action", "harness_full_equal_action",
)
REQUIRED_ARTIFACT_DIGESTS = frozenset((
    "design", "protocol", "manifest_lock", "claim_contract",
    "construct_contract", "semantic_simulation", "validated_outcomes",
    "grader_implementation", "grader_mutation_audit",
    "grader_machine_conformance", "native_preflight",
    "clean_checkout_reproduction", "linux_ci_reproduction",
    "runtime_implementation", "schedule_implementation",
    "descriptive_selection",
))
PHASE_LOGICAL_CELLS = {
    "calibration": 352, "sentinel": 88, "primary": 880,
    "primary_analysis": 0, "descriptives": None, "release": 0,
}
# The two optional model-size blocks contain 44 cells each.  Every 4B
# descriptive block remains mandatory, so the only lawful realized totals are
# 222 (both pass), 178 (one removed), or 134 (both removed).
DESCRIPTIVE_LOGICAL_COUNTS = frozenset((134, 178, 222))


class NextStudyProgramError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def research_catalog():
    """Return the closed built-in research catalog without plugin discovery."""

    return {
        "domains": list(RESEARCH_DOMAINS),
        "conditions": list(RESEARCH_CONDITIONS),
        "external_entry_point_discovery": False,
    }


def _sha256(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise NextStudyProgramError("%s must be lowercase SHA-256 hex" % label)


def _timestamp(value, label):
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise NextStudyProgramError("%s must be ISO-8601" % label)
    if parsed.utcoffset() is None:
        raise NextStudyProgramError("%s must include a timezone" % label)
    return parsed


def _validate_fingerprint(value, schema, label):
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "details", "fingerprint_sha256",
    }:
        raise NextStudyProgramError("%s has unexpected keys" % label)
    if value["schema_version"] != schema or not isinstance(value["details"], dict) or not value["details"]:
        raise NextStudyProgramError("%s schema or details drifted" % label)
    _sha256(value["fingerprint_sha256"], "%s digest" % label)
    unsigned = {"schema_version": value["schema_version"], "details": value["details"]}
    if value["fingerprint_sha256"] != _digest(unsigned):
        raise NextStudyProgramError("%s digest drifted" % label)
    return value


def build_fingerprint(schema_version, details):
    if schema_version not in (HOST_FINGERPRINT_SCHEMA, RUNTIME_FINGERPRINT_SCHEMA):
        raise NextStudyProgramError("unknown fingerprint schema")
    if not isinstance(details, dict) or not details:
        raise NextStudyProgramError("fingerprint details are empty")
    document = {"schema_version": schema_version, "details": copy.deepcopy(details)}
    canonical_json_bytes(document, allow_float=False)
    document["fingerprint_sha256"] = _digest(document)
    return document


def validate_authorization(document):
    expected = {
        "schema_version", "status", "protocol_version", "tag", "tag_object_sha",
        "commit_sha",
        "artifact_digests", "host_fingerprint", "runtime_fingerprint",
        "schedule_digests", "model_digests", "descriptive_selection_sha256",
        "maximum_logical_cells", "maximum_physical_attempts",
        "same_seed_retry_limit", "auto_advance_on_sealed_pass", "issued_at",
        "issuer", "execution_context", "authorization_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyProgramError("program authorization has unexpected keys")
    unsigned = dict(document)
    supplied_digest = unsigned.pop("authorization_sha256")
    if supplied_digest != _digest(unsigned):
        raise NextStudyProgramError("program authorization digest drifted")
    if document["schema_version"] != AUTHORIZATION_SCHEMA:
        raise NextStudyProgramError("program authorization schema drifted")
    if document["status"] != "authorized":
        raise NextStudyProgramError("program authorization is not active")
    validate_execution_context(document["execution_context"])
    if document["protocol_version"] != PROTOCOL_VERSION:
        raise NextStudyProgramError("program authorization protocol drifted")
    if document["tag"] != "v0.13.0":
        raise NextStudyProgramError("successor instrument authorization must bind v0.13.0")
    if (
        not isinstance(document["tag_object_sha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", document["tag_object_sha"]) is None
    ):
        raise NextStudyProgramError("authorization annotated-tag object SHA is invalid")
    if not isinstance(document["commit_sha"], str) or re.fullmatch(r"[0-9a-f]{40}", document["commit_sha"]) is None:
        raise NextStudyProgramError("authorization commit SHA is invalid")
    if document["maximum_logical_cells"] != MAXIMUM_LOGICAL_CELLS:
        raise NextStudyProgramError("logical-cell ceiling drifted")
    if document["maximum_physical_attempts"] != MAXIMUM_PHYSICAL_ATTEMPTS:
        raise NextStudyProgramError("physical-attempt ceiling drifted")
    if document["same_seed_retry_limit"] != 1:
        raise NextStudyProgramError("retry ceiling drifted")
    if document["auto_advance_on_sealed_pass"] is not True:
        raise NextStudyProgramError("sealed gates must auto-advance")
    for mapping_name in (
        "artifact_digests", "schedule_digests", "model_digests",
    ):
        mapping = document[mapping_name]
        if not isinstance(mapping, dict) or not mapping:
            raise NextStudyProgramError("%s must be a nonempty mapping" % mapping_name)
        for name, digest in mapping.items():
            _sha256(digest, "%s.%s" % (mapping_name, name))
    if set(document["model_digests"]) != {"2b", "4b", "9b"}:
        raise NextStudyProgramError("authorization must bind all 2B/4B/9B models")
    if set(document["schedule_digests"]) != {
        "calibration", "sentinel", "primary", "descriptives",
    }:
        raise NextStudyProgramError("authorization schedule bindings drifted")
    if set(document["artifact_digests"]) != REQUIRED_ARTIFACT_DIGESTS:
        raise NextStudyProgramError("authorization artifact bindings drifted")
    _sha256(document["descriptive_selection_sha256"], "descriptive selection")
    _validate_fingerprint(
        document["host_fingerprint"], HOST_FINGERPRINT_SCHEMA, "host fingerprint"
    )
    _validate_fingerprint(
        document["runtime_fingerprint"], RUNTIME_FINGERPRINT_SCHEMA,
        "runtime fingerprint",
    )
    if not isinstance(document["issuer"], str) or not document["issuer"].strip():
        raise NextStudyProgramError("authorization issuer is empty")
    _timestamp(document["issued_at"], "authorization issue time")
    return document


def build_authorization(
    *, tag, tag_object_sha, commit_sha, artifact_digests, host_fingerprint,
    runtime_fingerprint, schedule_digests, model_digests,
    descriptive_selection_sha256, issued_at, issuer,
    execution_context="authorized_research",
):
    document = {
        "schema_version": AUTHORIZATION_SCHEMA,
        "status": "authorized",
        "protocol_version": PROTOCOL_VERSION,
        "tag": tag,
        "tag_object_sha": tag_object_sha,
        "commit_sha": commit_sha,
        "artifact_digests": copy.deepcopy(artifact_digests),
        "host_fingerprint": copy.deepcopy(host_fingerprint),
        "runtime_fingerprint": copy.deepcopy(runtime_fingerprint),
        "schedule_digests": copy.deepcopy(schedule_digests),
        "model_digests": copy.deepcopy(model_digests),
        "descriptive_selection_sha256": descriptive_selection_sha256,
        "maximum_logical_cells": MAXIMUM_LOGICAL_CELLS,
        "maximum_physical_attempts": MAXIMUM_PHYSICAL_ATTEMPTS,
        "same_seed_retry_limit": 1,
        "auto_advance_on_sealed_pass": True,
        "issued_at": issued_at,
        "issuer": issuer,
        "execution_context": build_execution_context(execution_context),
    }
    document["authorization_sha256"] = _digest(document)
    return validate_authorization(document)


def execution_allowed(authorization, current_fingerprint, schedule_digests):
    try:
        validate_authorization(authorization)
        if authorization["execution_context"]["value"] != "authorized_research":
            return False
        if not isinstance(current_fingerprint, dict) or set(current_fingerprint) != {
            "host_fingerprint", "runtime_fingerprint", "commit_sha", "tag",
            "tag_object_sha",
            "artifact_digests", "model_digests",
            "descriptive_selection_sha256",
        }:
            return False
        _validate_fingerprint(
            current_fingerprint["host_fingerprint"], HOST_FINGERPRINT_SCHEMA,
            "current host fingerprint",
        )
        _validate_fingerprint(
            current_fingerprint["runtime_fingerprint"], RUNTIME_FINGERPRINT_SCHEMA,
            "current runtime fingerprint",
        )
    except NextStudyProgramError:
        return False
    return (
        current_fingerprint == {
            "host_fingerprint": authorization["host_fingerprint"],
            "runtime_fingerprint": authorization["runtime_fingerprint"],
            "commit_sha": authorization["commit_sha"],
            "tag": authorization["tag"],
            "tag_object_sha": authorization["tag_object_sha"],
            "artifact_digests": authorization["artifact_digests"],
            "model_digests": authorization["model_digests"],
            "descriptive_selection_sha256": authorization[
                "descriptive_selection_sha256"
            ],
        }
        and schedule_digests == authorization["schedule_digests"]
    )


def build_execution_context(value):
    if value not in ("authorized_research", "synthetic_rehearsal"):
        raise NextStudyProgramError("execution context is invalid")
    return {"schema_version": EXECUTION_CONTEXT_SCHEMA, "value": value}


def validate_execution_context(document):
    if (
        not isinstance(document, dict)
        or set(document) != {"schema_version", "value"}
        or document["schema_version"] != EXECUTION_CONTEXT_SCHEMA
        or document["value"] not in ("authorized_research", "synthetic_rehearsal")
    ):
        raise NextStudyProgramError("execution context is invalid")
    return document


def _scheduled_cells(schedule, phase, expected_count):
    if (
        not isinstance(schedule, dict) or schedule.get("phase") != phase
        or schedule.get("logical_cell_count") != expected_count
        or not isinstance(schedule.get("records"), list)
        or len(schedule["records"]) != expected_count
    ):
        raise NextStudyProgramError("%s schedule is invalid" % phase)
    cells = {item.get("logical_cell_id"): item for item in schedule["records"]}
    if len(cells) != expected_count or None in cells:
        raise NextStudyProgramError("%s schedule contains duplicate cells" % phase)
    return cells


def calibration_decision(records, schedule):
    expected_keys = {"logical_cell_id", "instrument_valid", "strict_success"}
    scheduled = _scheduled_cells(schedule, "calibration", 352)
    totals = {family: 0 for family in sorted(FAMILIES)}
    counts = Counter()
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != expected_keys:
            raise NextStudyProgramError("calibration record has unexpected keys")
        cell = scheduled.get(record["logical_cell_id"])
        if cell is None or record["logical_cell_id"] in seen:
            raise NextStudyProgramError("calibration result is duplicate or unscheduled")
        seen.add(record["logical_cell_id"])
        family = cell["family"]
        if type(record["instrument_valid"]) is not bool:
            raise NextStudyProgramError("calibration validity must be boolean")
        if type(record["strict_success"]) is not bool:
            raise NextStudyProgramError("calibration success must be boolean")
        counts[family] += 1
        totals[family] += int(record["strict_success"])
    if any(record["instrument_valid"] is not True for record in records):
        return {"status": "retire_generator", "reason": "instrument_invalid"}
    if set(counts.values()) != {32} or len(records) != 352:
        return {"status": "incomplete", "condition_combined_totals": None}
    passed = all(10 <= total <= 22 for total in totals.values())
    return {
        "status": "sealed_pass" if passed else "retire_generator",
        "condition_combined_totals": totals,
        "per_condition_totals_exposed": False,
    }


def sentinel_decision(records, schedule):
    scheduled = _scheduled_cells(schedule, "sentinel", 88)
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "logical_cell_id", "instrument_valid",
        }:
            raise NextStudyProgramError("sentinel record has unexpected keys")
        if record["logical_cell_id"] not in scheduled or record["logical_cell_id"] in seen:
            raise NextStudyProgramError("sentinel result is duplicate or unscheduled")
        if type(record["instrument_valid"]) is not bool:
            raise NextStudyProgramError("sentinel validity must be boolean")
        seen.add(record["logical_cell_id"])
    if len(records) != 88:
        return {"status": "incomplete", "instrument_invalid_cells": None}
    invalid = sum(record["instrument_valid"] is not True for record in records)
    return {
        "status": "sealed_pass" if invalid == 0 else "retire_instrument",
        "instrument_invalid_cells": invalid,
        "efficacy_fields_read": False,
    }


def retry_decision(attempt):
    required = {"repeat", "failure_origin", "retryable", "same_seed_available"}
    if not isinstance(attempt, dict) or set(attempt) != required:
        raise NextStudyProgramError("retry record has unexpected keys")
    if type(attempt["repeat"]) is not int or attempt["repeat"] not in (0, 1):
        raise NextStudyProgramError("retry repeat must be zero or one")
    if attempt["failure_origin"] not in ("none", "model", "environment", "instrument"):
        raise NextStudyProgramError("retry failure origin is invalid")
    if type(attempt["retryable"]) is not bool or type(attempt["same_seed_available"]) is not bool:
        raise NextStudyProgramError("retry flags must be boolean")
    eligible = (
        attempt["repeat"] == 0
        and attempt["failure_origin"] == "environment"
        and attempt["retryable"] is True
        and attempt["same_seed_available"] is True
    )
    return {
        "eligible": eligible,
        "next_repeat": 1 if eligible else None,
        "same_seed_required": eligible,
        "known_parser_rejection_is_model_failure": True,
    }


def initial_program_state(authorization_sha256):
    _sha256(authorization_sha256, "authorization")
    return {
        "schema_version": PROGRAM_STATE_SCHEMA,
        "authorization_sha256": authorization_sha256,
        "status": "ready",
        "current_phase": "calibration",
        "completed_phases": [],
        "sealed_phase_gates": [],
        "logical_cells_completed": 0,
        "physical_attempts_completed": 0,
        "primary_claim_sealed": False,
        "descriptives_may_run": False,
    }


def validate_program_state(state):
    expected = {
        "schema_version", "authorization_sha256", "status", "current_phase",
        "completed_phases", "sealed_phase_gates", "logical_cells_completed",
        "physical_attempts_completed", "primary_claim_sealed",
        "descriptives_may_run",
    }
    if not isinstance(state, dict) or set(state) != expected:
        raise NextStudyProgramError("program state has unexpected keys")
    if state["schema_version"] != PROGRAM_STATE_SCHEMA:
        raise NextStudyProgramError("program state schema drifted")
    _sha256(state["authorization_sha256"], "program-state authorization")
    if not isinstance(state["completed_phases"], list):
        raise NextStudyProgramError("completed phase history is invalid")
    completed = state["completed_phases"]
    if completed != list(PHASES[:len(completed)]):
        raise NextStudyProgramError("completed phases are not a strict prefix")
    expected_current = None if len(completed) == len(PHASES) else PHASES[len(completed)]
    if state["current_phase"] != expected_current:
        raise NextStudyProgramError("program current phase is inconsistent")
    expected_status = "complete" if expected_current is None else "ready"
    if state["status"] != expected_status:
        raise NextStudyProgramError("program status is inconsistent")
    gates = state["sealed_phase_gates"]
    if not isinstance(gates, list) or len(gates) != len(completed):
        raise NextStudyProgramError("sealed phase-gate history is incomplete")
    expected_gate_keys = {
        "schema_version", "authorization_sha256", "phase", "status",
        "logical_cells_completed", "physical_attempts_completed",
        "sealed_artifact_sha256",
    }
    for phase, gate in zip(completed, gates):
        if (
            not isinstance(gate, dict) or set(gate) != expected_gate_keys
            or gate["schema_version"] != SEALED_GATE_SCHEMA
            or gate["authorization_sha256"] != state["authorization_sha256"]
            or gate["phase"] != phase or gate["status"] != "sealed_pass"
        ):
            raise NextStudyProgramError("sealed phase-gate history drifted")
        _sha256(gate["sealed_artifact_sha256"], "sealed phase artifact")
        logical = gate["logical_cells_completed"]
        physical = gate["physical_attempts_completed"]
        expected_logical = PHASE_LOGICAL_CELLS[phase]
        if (
            type(logical) is not int or type(physical) is not int
            or logical < 0 or physical < logical or physical > logical * 2
            or expected_logical is not None and logical != expected_logical
            or phase == "descriptives"
            and logical not in DESCRIPTIVE_LOGICAL_COUNTS
        ):
            raise NextStudyProgramError("sealed phase-gate counters drifted")
    for field, ceiling in (
        ("logical_cells_completed", MAXIMUM_LOGICAL_CELLS),
        ("physical_attempts_completed", MAXIMUM_PHYSICAL_ATTEMPTS),
    ):
        value = state[field]
        if type(value) is not int or not 0 <= value <= ceiling:
            raise NextStudyProgramError("program counter is invalid")
    if state["logical_cells_completed"] != sum(
        gate["logical_cells_completed"] for gate in gates
    ) or state["physical_attempts_completed"] != sum(
        gate["physical_attempts_completed"] for gate in gates
    ):
        raise NextStudyProgramError("program counters are not derived from sealed gates")
    primary_sealed = "primary_analysis" in completed
    if (
        state["primary_claim_sealed"] is not primary_sealed
        or state["descriptives_may_run"] is not primary_sealed
    ):
        raise NextStudyProgramError("primary sealing flags are inconsistent")
    return state


def advance_program(state, sealed_gate):
    validate_program_state(state)
    updated = copy.deepcopy(state)
    phase = updated["current_phase"]
    expected_gate_keys = {
        "schema_version", "authorization_sha256", "phase", "status",
        "logical_cells_completed", "physical_attempts_completed",
        "sealed_artifact_sha256",
    }
    if not isinstance(sealed_gate, dict) or set(sealed_gate) != expected_gate_keys:
        raise NextStudyProgramError("sealed phase gate has unexpected keys")
    if (
        phase not in PHASES
        or sealed_gate["schema_version"] != SEALED_GATE_SCHEMA
        or sealed_gate["status"] != "sealed_pass"
        or sealed_gate["phase"] != phase
        or sealed_gate["authorization_sha256"] != state["authorization_sha256"]
    ):
        raise NextStudyProgramError("program advances only on a sealed pass")
    _sha256(sealed_gate["sealed_artifact_sha256"], "sealed phase artifact")
    logical = sealed_gate["logical_cells_completed"]
    physical = sealed_gate["physical_attempts_completed"]
    if type(logical) is not int or type(physical) is not int or logical < 0 or physical < logical:
        raise NextStudyProgramError("sealed phase counters are invalid")
    expected_logical = PHASE_LOGICAL_CELLS[phase]
    if (
        expected_logical is not None and logical != expected_logical
        or phase == "descriptives"
        and logical not in DESCRIPTIVE_LOGICAL_COUNTS
    ):
        raise NextStudyProgramError("sealed phase logical-cell count drifted")
    if physical > logical * 2:
        raise NextStudyProgramError("sealed phase retry ceiling exceeded")
    updated["logical_cells_completed"] += logical
    updated["physical_attempts_completed"] += physical
    if (
        updated["logical_cells_completed"] > MAXIMUM_LOGICAL_CELLS
        or updated["physical_attempts_completed"] > MAXIMUM_PHYSICAL_ATTEMPTS
    ):
        raise NextStudyProgramError("program ceiling exceeded")
    if phase == "primary":
        next_phase = "primary_analysis"
    elif phase == "primary_analysis":
        updated["primary_claim_sealed"] = True
        updated["descriptives_may_run"] = True
        next_phase = "descriptives"
    else:
        index = PHASES.index(phase)
        next_phase = PHASES[index + 1] if index + 1 < len(PHASES) else None
    updated["completed_phases"].append(phase)
    updated["sealed_phase_gates"].append(copy.deepcopy(sealed_gate))
    updated["current_phase"] = next_phase
    updated["status"] = "complete" if next_phase is None else "ready"
    return validate_program_state(updated)


class BenchmarkLease:
    def __init__(self, path=None):
        program_data = os.environ.get("PROGRAMDATA")
        default_root = Path(program_data) if program_data else Path(tempfile.gettempdir())
        self.path = Path(path) if path is not None else default_root / "Brick" / "benchmark.lease"
        self._owned = False

    def acquire(self, authorization_sha256):
        _sha256(authorization_sha256, "authorization")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": LEASE_SCHEMA,
            "authorization_sha256": authorization_sha256,
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "acquired_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "prohibitions": [
                "agent_lab", "brix", "other_ollama", "builds", "updates",
                "heavy_background_workloads",
            ],
        }
        document["lease_sha256"] = _digest(document)
        try:
            descriptor = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            raise NextStudyProgramError("machine-wide benchmark lease is already held")
        try:
            os.write(descriptor, canonical_json_bytes(document, allow_float=False))
        finally:
            os.close(descriptor)
        self._owned = True
        self._document = copy.deepcopy(document)
        return document

    def release(self):
        if not self._owned:
            raise NextStudyProgramError("cannot release an unowned benchmark lease")
        try:
            import json
            actual = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            raise NextStudyProgramError("owned benchmark lease is missing or corrupt")
        if actual != self._document:
            raise NextStudyProgramError("owned benchmark lease changed before release")
        self.path.unlink()
        self._owned = False

    def validate_held(self, authorization_sha256):
        if not self._owned:
            raise NextStudyProgramError("benchmark lease is not owned by this process")
        try:
            import json
            actual = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            raise NextStudyProgramError("owned benchmark lease is missing or corrupt")
        if actual != self._document:
            raise NextStudyProgramError("owned benchmark lease changed on disk")
        return validate_lease(actual, authorization_sha256, require_current_host=True)


def validate_lease(document, authorization_sha256, require_current_host=True):
    expected = {
        "schema_version", "authorization_sha256", "host", "pid",
        "acquired_at", "prohibitions", "lease_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise NextStudyProgramError("machine lease has unexpected keys")
    unsigned = dict(document)
    supplied = unsigned.pop("lease_sha256")
    _sha256(supplied, "machine lease digest")
    if supplied != _digest(unsigned):
        raise NextStudyProgramError("machine lease digest drifted")
    if document["schema_version"] != LEASE_SCHEMA:
        raise NextStudyProgramError("machine lease schema drifted")
    _sha256(authorization_sha256, "lease authorization")
    if document["authorization_sha256"] != authorization_sha256:
        raise NextStudyProgramError("machine lease authorization drifted")
    if require_current_host and document["host"] != socket.gethostname():
        raise NextStudyProgramError("machine lease belongs to another host")
    if type(document["pid"]) is not int or document["pid"] <= 0:
        raise NextStudyProgramError("machine lease pid is invalid")
    _timestamp(document["acquired_at"], "machine lease acquisition time")
    if document["prohibitions"] != [
        "agent_lab", "brix", "other_ollama", "builds", "updates",
        "heavy_background_workloads",
    ]:
        raise NextStudyProgramError("machine lease prohibitions drifted")
    return document


__all__ = [
    "AUTHORIZATION_SCHEMA", "BenchmarkLease", "EXECUTION_CONTEXT_SCHEMA",
    "HOST_FINGERPRINT_SCHEMA",
    "RUNTIME_FINGERPRINT_SCHEMA", "SEALED_GATE_SCHEMA", "MAXIMUM_LOGICAL_CELLS",
    "MAXIMUM_PHYSICAL_ATTEMPTS", "REQUIRED_ARTIFACT_DIGESTS",
    "NextStudyProgramError", "advance_program",
    "build_authorization", "build_execution_context", "build_fingerprint", "calibration_decision",
    "execution_allowed", "initial_program_state",
    "research_catalog", "retry_decision", "sentinel_decision",
    "validate_authorization", "validate_execution_context", "validate_lease", "validate_program_state",
]
