"""Materialize the advisory human-review handoff for office-v2.

The distributable bundle contains only public task material.  Challenge truth,
generator metadata, oracle outcomes, graders, model outputs, split labels, and
condition labels are deliberately absent.  This module performs no model call
and its output cannot authorize research execution.
"""

import argparse
import copy
import csv
import io
import json
from pathlib import Path
import re
import shutil
import zipfile

from bench.next_study_construct import POLICIES
from bench.next_study_review import review_packet
from domains.office_demo.generators_v2 import _BUILDERS, _Context, SPLIT_ORDINALS
from domains.office_demo.outcome_oracle_v2 import derive_outcome
from harness.evidence import canonical_json_bytes
from harness.instances import load_canonical_json, replace_canonical_json, sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIRECTORY = ROOT / "bench" / "manifests" / "office-v2"
SELECTION_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2-review-selection.json"
)
BLUEPRINT_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2-hybrid-challenge-blueprint.json"
)
CHALLENGE_SET_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2-hybrid-challenge-set.json"
)
CHALLENGE_KEY_PATH = (
    ROOT / "evidence" / "next-study" / "office-v2-hybrid-challenge-key.json"
)
DEFAULT_HANDOFF = ROOT / "reviewer-handoff" / "brick-office-v2-reviewer-a"

CHALLENGE_SET_SCHEMA = "brick.next-study.hybrid-challenge-set/1"
CHALLENGE_KEY_SCHEMA = "brick.next-study.hybrid-challenge-key/1"
HANDOFF_MANIFEST_SCHEMA = "brick.next-study.reviewer-handoff-manifest/1"
RESPONSE_COLUMNS = (
    "packet_number", "packet_id", "prompt_clear", "enough_information",
    "single_reasonable_outcome", "expected_actions_and_exact_details",
    "reasonable_alternatives", "defect_or_ambiguity", "rationale",
    "minutes_spent",
)
_YES_NO = frozenset(("yes", "no"))
_PROHIBITED_DISTRIBUTABLE_TERMS = (
    "required_effects", "source_split", "base_instance_id", "expected_valid",
    "sealed_answer", "oracle_outcome", "condition_name", "strict_success",
)


class ReviewerHandoffError(ValueError):
    pass


def _digest(value):
    return sha256_bytes(canonical_json_bytes(value, allow_float=False))


def _manifests():
    return [
        load_canonical_json(MANIFEST_DIRECTORY / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def _instances(manifests):
    result = {}
    for manifest in manifests:
        for instance in manifest["instances"]:
            instance_id = instance["content"]["id"]
            if instance_id in result:
                raise ReviewerHandoffError("duplicate instance in manifests")
            result[instance_id] = instance
    if len(result) != 528:
        raise ReviewerHandoffError("review handoff requires 528 frozen cases")
    return result


def _derive(packet):
    return derive_outcome(
        packet["family"], packet["prompt"], packet["subepisode_prompts"],
        packet["initial_state"], packet["today"],
    )


def _alternate_policy_candidate(instance, packet):
    family = instance["content"]["family"]
    current = instance["content"]["structure"]["decision_policy"]
    policies = POLICIES[family]
    alternate = policies[(policies.index(current) + 1) % len(policies)]
    content = instance["content"]
    try:
        index = int(content["id"].rsplit(".", 1)[1])
        ordinal = SPLIT_ORDINALS[content["split"]][index]
    except (KeyError, ValueError, IndexError):
        raise ReviewerHandoffError("alternate-policy base identity is invalid")
    context = _Context(
        content["split"], family, index, ordinal, content["seed"],
    )
    context.axes["decision_policy"] = alternate
    alternate_prompt, alternate_episodes, alternate_state, candidate, _difficulty = (
        _BUILDERS[family](context)
    )
    alternate_packet = {
        "family": family,
        "prompt": alternate_prompt,
        "subepisode_prompts": [item["prompt"] for item in alternate_episodes],
        "initial_state": alternate_state,
        "today": context.today.isoformat(),
    }
    if _derive(alternate_packet) != candidate:
        raise ReviewerHandoffError("alternate-policy candidate is not oracle-valid")
    # Only the candidate outcome is exposed beside the original public packet.
    # The alternate prompt and policy label remain internal challenge evidence.
    if candidate == _derive(packet):
        raise ReviewerHandoffError("alternate policy did not change the outcome")
    return candidate


def _business_effect(outcome):
    for effect in reversed(outcome):
        if effect.get("type") not in ("sources_read", "calendar_read"):
            return effect
    raise ReviewerHandoffError("outcome has no business effect")


def _omitted_candidate(outcome):
    changed = copy.deepcopy(outcome)
    effect = _business_effect(changed)
    preferred = (
        "required_values_by_slide", "ordered_rows_cents", "ordered_rows",
        "ordered_titles", "required_facts", "attendees", "body", "message",
        "title", "filename", "recipient", "date", "start", "end",
    )
    key = next((name for name in preferred if name in effect), None)
    if key is None:
        key = next((name for name in sorted(effect) if name != "type"), None)
    if key is None:
        raise ReviewerHandoffError("business effect has no omittable fact")
    del effect[key]
    return changed


def _corrupt_value(value):
    if isinstance(value, bool):
        return not value
    if type(value) is int:
        return value + 1
    if isinstance(value, str):
        return value + " [changed]"
    if isinstance(value, list) and value:
        changed = copy.deepcopy(value)
        for index, item in enumerate(changed):
            try:
                changed[index] = _corrupt_value(item)
                return changed
            except ReviewerHandoffError:
                continue
        raise ReviewerHandoffError("list has no corruptible fact")
    if isinstance(value, dict) and value:
        changed = copy.deepcopy(value)
        for key in sorted(changed):
            if key == "type":
                continue
            try:
                changed[key] = _corrupt_value(changed[key])
                return changed
            except ReviewerHandoffError:
                continue
        raise ReviewerHandoffError("nested value has no corruptible fact")
    raise ReviewerHandoffError("value has no deterministic corruption")


def _corrupted_candidate(outcome):
    changed = copy.deepcopy(outcome)
    effect = _business_effect(changed)
    preferred = (
        "required_values_by_slide", "ordered_rows_cents", "ordered_rows",
        "ordered_titles", "required_facts", "attendees", "body", "message",
        "title", "filename", "recipient", "date", "start", "end",
        "total_cents", "amount_cents",
    )
    candidates = [name for name in preferred if name in effect]
    candidates.extend(
        name for name in sorted(effect)
        if name != "type" and name not in candidates
    )
    for key in candidates:
        try:
            effect[key] = _corrupt_value(effect[key])
            return changed
        except ReviewerHandoffError:
            continue
    raise ReviewerHandoffError("business effect has no corruptible fact")


def _record_order_packet(packet):
    changed = copy.deepcopy(packet)
    for key, value in changed["initial_state"].items():
        if isinstance(value, list):
            changed["initial_state"][key] = list(reversed(value))
    return changed


def _irrelevant_state_packet(packet, challenge_id):
    changed = copy.deepcopy(packet)
    changed["initial_state"]["emails"].append({
        "id": "unrelated-" + challenge_id[:12],
        "from": "unrelated@office-v2.example",
        "date": "2027-01-01 00:00",
        "subject": "Unrelated archived notice",
        "body": "This archived notice is unrelated to the requested work.",
    })
    return changed


def materialize_challenges(manifests=None, blueprint=None):
    manifests = _manifests() if manifests is None else manifests
    blueprint = load_canonical_json(BLUEPRINT_PATH) if blueprint is None else blueprint
    by_id = _instances(manifests)
    public_records, key_records = [], []
    for record in blueprint["records"]:
        instance = by_id.get(record["base_instance_id"])
        if instance is None or instance["content_sha256"] != record["base_content_sha256"]:
            raise ReviewerHandoffError("challenge base binding drifted")
        packet = review_packet(instance)
        canonical = _derive(packet)
        challenge_type = record["challenge_type"]
        if challenge_type == "canonical_control":
            public_packet, candidate = packet, canonical
        elif challenge_type == "record_order_control":
            public_packet = _record_order_packet(packet)
            candidate = canonical
        elif challenge_type == "irrelevant_state_control":
            public_packet = _irrelevant_state_packet(packet, record["challenge_id"])
            candidate = canonical
        elif challenge_type == "alternate_policy_outcome":
            public_packet = packet
            candidate = _alternate_policy_candidate(instance, packet)
        elif challenge_type == "required_fact_omission":
            public_packet = packet
            candidate = _omitted_candidate(canonical)
        elif challenge_type == "business_fact_corruption":
            public_packet = packet
            candidate = _corrupted_candidate(canonical)
        else:
            raise ReviewerHandoffError("unknown challenge type")
        derived = _derive(public_packet)
        is_valid = candidate == derived
        if is_valid is not record["expected_valid"]:
            raise ReviewerHandoffError("materialized challenge truth drifted")
        public = {
            "schema_version": "brick.next-study.blind-challenge-packet/1",
            "challenge_id": record["challenge_id"],
            "task": public_packet,
            "candidate_outcome": candidate,
            "review_question": (
                "Does the candidate outcome completely and exactly satisfy the "
                "task using only the visible information?"
            ),
        }
        public["challenge_packet_sha256"] = _digest(public)
        public_records.append(public)
        key_records.append({
            "challenge_id": record["challenge_id"],
            "challenge_packet_sha256": public["challenge_packet_sha256"],
            "challenge_type": challenge_type,
            "expected_valid": record["expected_valid"],
            "canonical_outcome_sha256": _digest(derived),
            "candidate_outcome_sha256": _digest(candidate),
        })
    public_records.sort(key=lambda item: item["challenge_id"])
    key_records.sort(key=lambda item: item["challenge_id"])
    challenge_set = {
        "schema_version": CHALLENGE_SET_SCHEMA,
        "blueprint_sha256": blueprint["blueprint_sha256"],
        "status": "materialized_public_packets",
        "case_count": 66,
        "records": public_records,
    }
    challenge_set["challenge_set_sha256"] = _digest(challenge_set)
    key = {
        "schema_version": CHALLENGE_KEY_SCHEMA,
        "blueprint_sha256": blueprint["blueprint_sha256"],
        "challenge_set_sha256": challenge_set["challenge_set_sha256"],
        "status": "sealed_internal_do_not_distribute",
        "valid_controls": 33,
        "invalid_challenges": 33,
        "records": key_records,
    }
    key["challenge_key_sha256"] = _digest(key)
    return challenge_set, key


def validate_challenges(challenge_set, key, manifests=None, blueprint=None):
    rebuilt_set, rebuilt_key = materialize_challenges(manifests, blueprint)
    if challenge_set != rebuilt_set or key != rebuilt_key:
        raise ReviewerHandoffError("materialized challenge artifacts drifted")
    if len(challenge_set["records"]) != 66:
        raise ReviewerHandoffError("challenge set is incomplete")
    return challenge_set, key


def _pilot_packets(manifests=None, selection=None):
    manifests = _manifests() if manifests is None else manifests
    selection = load_canonical_json(SELECTION_PATH) if selection is None else selection
    by_id = _instances(manifests)
    records = [item for item in selection["records"] if item["pilot"]]
    if len(records) != 44:
        raise ReviewerHandoffError("reviewer handoff requires the frozen 44-case pilot")
    counts = {}
    packets = []
    for record in records:
        instance = by_id[record["instance_id"]]
        packet = review_packet(instance)
        counts[packet["family"]] = counts.get(packet["family"], 0) + 1
        packets.append(packet)
    if set(counts.values()) != {4} or len(counts) != 11:
        raise ReviewerHandoffError("pilot is not four cases per family")
    return sorted(packets, key=lambda item: item["packet_id"])


def _tool_guide(packets):
    schemas = {}
    for packet in packets:
        for tool in packet["tool_schemas"]:
            prior = schemas.setdefault(tool["name"], tool)
            if prior != tool:
                raise ReviewerHandoffError("tool schema drifted across packets")
    lines = [
        "# Available tools", "",
        "These descriptions define what the office assistant can inspect or change.",
        "You do not need to simulate every API call; use them to decide whether the",
        "requested result is possible and what exact result is required.", "",
    ]
    for name in sorted(schemas):
        tool = schemas[name]
        lines.extend((
            "## `" + name + "`", "", tool["description"], "",
            "Parameters:", "", "```json",
            json.dumps(tool["parameters"], ensure_ascii=False, indent=2, sort_keys=True),
            "```", "",
        ))
    return "\n".join(lines)


def _packets_markdown(packets):
    lines = [
        "# Brick office-task review packets", "",
        "Review each task independently. Do not use generative AI and do not discuss",
        "an unfinished case with another reviewer. Record your answer in",
        "`RESPONSES.csv`; do not edit this packet file.", "",
    ]
    for index, packet in enumerate(packets, start=1):
        visible = {
            "today": packet["today"],
            "prompt": packet["prompt"],
            "subepisode_prompts": packet["subepisode_prompts"],
            "initial_state": packet["initial_state"],
            "available_tools": [tool["name"] for tool in packet["tool_schemas"]],
        }
        lines.extend((
            "## Packet %02d" % index, "",
            "Packet ID: `%s`" % packet["packet_id"], "",
            "```json", json.dumps(visible, ensure_ascii=False, indent=2, sort_keys=True),
            "```", "",
        ))
    return "\n".join(lines)


def _start_here():
    return """# Start here — independent Brick task review

You are reviewing whether synthetic office tasks are clear and have a defensible
exact answer. You are **not** evaluating an AI model and you are not being asked
to perform the tasks in real software.

1. Read `DECLARATION.md` and `TOOL_GUIDE.md`.
2. Open `PACKETS.md` and review packets in numeric order.
3. For every packet, fill one row in `RESPONSES.csv`.
4. Base your answer only on the packet. Do not use generative AI, source code,
   answer keys, model outputs, or another reviewer's work.
5. Return the completed `RESPONSES.csv` and signed `DECLARATION.md`.

This package is a 44-case advisory content audit for one reviewer. It is not a
model evaluation and it does not estimate agreement between reviewers. Please
do not open any Brick repository files outside this folder.

For `expected_actions_and_exact_details`, describe every required read or
business change and all exact details that matter: recipient, title, date/time,
filename, ordering, rows/slides, values, totals, reminder text, or remembered
facts as applicable. If more than one answer is reasonable, put your preferred
answer here and list the alternatives separately.

Use only `yes` or `no` in the three decision columns. Never force a task to pass:
record any ambiguity, contradiction, missing information, unrealistic rule, or
reasonable alternative in `defect_or_ambiguity`.
"""


def _declaration():
    return """# Reviewer declaration

Reviewer name or opaque ID: ______________________________

Review started (date/time/time zone): _____________________

Review completed (date/time/time zone): ___________________

I attest that:

- I reviewed the supplied packets independently.
- I did not use generative AI or inspect Brick source code, graders, or answers.
- I did not inspect model outputs or another reviewer's answers.
- I reported uncertainty and alternatives instead of guessing.
- I have disclosed any conflict of interest below.

Conflicts or relevant expertise (write “none” if none):

________________________________________________________________________

Signature: ______________________________  Date: ________________________
"""


def _submission_checklist():
    return """# Submission checklist

- All 44 rows are present; no row was added, deleted, or reordered.
- `prompt_clear`, `enough_information`, and `single_reasonable_outcome` use only
  `yes` or `no`.
- Every row contains an expected answer, rationale, and minutes spent.
- Uncertainty, alternatives, and suspected defects are written explicitly.
- `DECLARATION.md` is completed and signed.

Return only the completed `RESPONSES.csv` and `DECLARATION.md` to the study owner.
Do not send the packet to another reviewer; each reviewer receives a separately
identified copy from the study owner.
"""


def _response_csv(packets):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=RESPONSE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for index, packet in enumerate(packets, start=1):
        writer.writerow({
            "packet_number": "%02d" % index,
            "packet_id": packet["packet_id"],
            **{name: "" for name in RESPONSE_COLUMNS[2:]},
        })
    return stream.getvalue()


def _file_digest(path):
    return sha256_bytes(Path(path).read_bytes())


def build_handoff_manifest(directory, packets):
    directory = Path(directory)
    files = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name not in ("MANIFEST.json",):
            files.append({
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": _file_digest(path),
            })
    document = {
        "schema_version": HANDOFF_MANIFEST_SCHEMA,
        "status": "advisory_outcome_blind_reviewer_a_ready",
        "authorization_gate": False,
        "packet_count": len(packets),
        "packet_ids": [item["packet_id"] for item in packets],
        "files": files,
        "prohibited_contents_absent": True,
    }
    document["manifest_sha256"] = _digest(document)
    return document


def export_handoff(directory=DEFAULT_HANDOFF, *, overwrite=False):
    directory = Path(directory)
    if directory.exists():
        if not overwrite:
            raise ReviewerHandoffError("handoff directory already exists")
        resolved = directory.resolve()
        allowed = (ROOT / "reviewer-handoff").resolve()
        if resolved.parent != allowed:
            raise ReviewerHandoffError("refusing to replace a non-handoff directory")
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    packets = _pilot_packets()
    files = {
        "START_HERE.md": _start_here(),
        "DECLARATION.md": _declaration(),
        "TOOL_GUIDE.md": _tool_guide(packets),
        "PACKETS.md": _packets_markdown(packets),
        "RESPONSES.csv": _response_csv(packets),
        "SUBMISSION_CHECKLIST.md": _submission_checklist(),
    }
    for name, content in files.items():
        with (directory / name).open(
            "w", encoding="utf-8", newline="\n"
        ) as target:
            target.write(content.replace("\r\n", "\n"))
    manifest = build_handoff_manifest(directory, packets)
    replace_canonical_json(directory / "MANIFEST.json", manifest)
    validate_handoff(directory)
    archive = directory.with_suffix(".zip")
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    return directory, archive


def validate_handoff(directory=DEFAULT_HANDOFF):
    directory = Path(directory)
    packets = _pilot_packets()
    expected_names = {
        "START_HERE.md", "DECLARATION.md", "TOOL_GUIDE.md", "PACKETS.md",
        "RESPONSES.csv", "SUBMISSION_CHECKLIST.md", "MANIFEST.json",
    }
    if not directory.is_dir() or {item.name for item in directory.iterdir()} != expected_names:
        raise ReviewerHandoffError("handoff file set drifted")
    manifest = load_canonical_json(directory / "MANIFEST.json")
    if manifest != build_handoff_manifest(directory, packets):
        raise ReviewerHandoffError("handoff manifest or file digest drifted")
    distributable = "\n".join(
        path.read_text(encoding="utf-8", errors="strict")
        for path in directory.iterdir() if path.is_file()
    ).casefold()
    leaked = [term for term in _PROHIBITED_DISTRIBUTABLE_TERMS if term in distributable]
    if leaked:
        raise ReviewerHandoffError("handoff leaks prohibited terms: %r" % leaked)
    with (directory / "RESPONSES.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    if (
        len(rows) != 44 or tuple(rows[0]) != RESPONSE_COLUMNS
        or [row["packet_id"] for row in rows] != [item["packet_id"] for item in packets]
    ):
        raise ReviewerHandoffError("response worksheet binding drifted")
    return manifest


def validate_submission(path, handoff_directory=DEFAULT_HANDOFF):
    manifest = validate_handoff(handoff_directory)
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or tuple(rows[0]) != RESPONSE_COLUMNS or len(rows) != 44:
        raise ReviewerHandoffError("submission must contain the exact 44-row schema")
    if [row["packet_id"] for row in rows] != manifest["packet_ids"]:
        raise ReviewerHandoffError("submission packet order or identity drifted")
    for row in rows:
        for field in ("prompt_clear", "enough_information", "single_reasonable_outcome"):
            if row[field].strip().casefold() not in _YES_NO:
                raise ReviewerHandoffError("submission %s must be yes or no" % field)
        for field in ("expected_actions_and_exact_details", "rationale"):
            if not row[field].strip():
                raise ReviewerHandoffError("submission %s is empty" % field)
        try:
            minutes = float(row["minutes_spent"])
        except ValueError:
            raise ReviewerHandoffError("submission minutes_spent is not numeric")
        if not 0 < minutes <= 240:
            raise ReviewerHandoffError("submission minutes_spent is out of range")
    return {
        "schema_version": "brick.next-study.reviewer-submission-receipt/1",
        "status": "structurally_valid_advisory_submission",
        "authorization_gate": False,
        "packet_count": 44,
        "handoff_manifest_sha256": manifest["manifest_sha256"],
        "submission_sha256": _file_digest(path),
        "flagged_packets": sum(
            row["prompt_clear"].strip().casefold() == "no"
            or row["enough_information"].strip().casefold() == "no"
            or row["single_reasonable_outcome"].strip().casefold() == "no"
            for row in rows
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    materialize = commands.add_parser("materialize-challenges")
    materialize.add_argument("--verify", action="store_true")
    export = commands.add_parser("export-reviewer-a")
    export.add_argument("--output", type=Path, default=DEFAULT_HANDOFF)
    export.add_argument("--overwrite", action="store_true")
    verify = commands.add_parser("verify-reviewer-a")
    verify.add_argument("--input", type=Path, default=DEFAULT_HANDOFF)
    submission = commands.add_parser("validate-submission")
    submission.add_argument("--input", type=Path, required=True)
    submission.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    args = parser.parse_args(argv)
    if args.command == "materialize-challenges":
        challenge_set, key = materialize_challenges()
        if args.verify:
            validate_challenges(
                load_canonical_json(CHALLENGE_SET_PATH),
                load_canonical_json(CHALLENGE_KEY_PATH),
            )
            status = "verified"
        else:
            replace_canonical_json(CHALLENGE_SET_PATH, challenge_set)
            replace_canonical_json(CHALLENGE_KEY_PATH, key)
            status = "written"
        result = {"status": status, "challenge_cases": 66, "live_model_calls": 0}
    elif args.command == "export-reviewer-a":
        directory, archive = export_handoff(args.output, overwrite=args.overwrite)
        result = {
            "status": "ready", "packet_count": 44,
            "directory": str(directory), "archive": str(archive),
            "live_model_calls": 0,
        }
    elif args.command == "verify-reviewer-a":
        manifest = validate_handoff(args.input)
        result = {
            "status": "verified", "packet_count": manifest["packet_count"],
            "manifest_sha256": manifest["manifest_sha256"], "live_model_calls": 0,
        }
    else:
        result = validate_submission(args.input, args.handoff)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CHALLENGE_KEY_PATH", "CHALLENGE_SET_PATH", "DEFAULT_HANDOFF",
    "ReviewerHandoffError", "export_handoff", "materialize_challenges",
    "validate_challenges", "validate_handoff", "validate_submission",
]
