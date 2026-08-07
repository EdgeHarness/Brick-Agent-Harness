"""Validate and append advisory review rows to the audit response sheet.

Advisory tooling for the prompt audit described in
`docs/office-v2-prompt-audit-runbook.md`.  It is not part of the frozen
instrument, it never reads the grader or oracle, and it cannot authorize a
study.

Usage:

    python docs/office-v2-audit-append.py \
        --run-id r2 --reviewer-id b \
        --bundle reviewer-handoff/brick-office-v2-reviewer-a \
        --csv docs/office-v2-prompt-audit-responses.csv \
        chunk1.json chunk2.json chunk3.json chunk4.json

Reads JSON arrays of row objects, checks them against the bundle's blank
response template, refuses duplicates, and appends.  Prints a summary.
"""

import argparse
import csv
import json
import os
import sys

COLUMNS = [
    "run_id",
    "reviewer_id",
    "packet_number",
    "packet_id",
    "prompt_clear",
    "enough_information",
    "single_reasonable_outcome",
    "expected_actions_and_exact_details",
    "reasonable_alternatives",
    "defect_or_ambiguity",
    "rationale",
    "minutes_spent",
]
DECISIONS = ("prompt_clear", "enough_information", "single_reasonable_outcome")
REQUIRED = DECISIONS + ("packet_number", "packet_id", "expected_actions_and_exact_details")


def _template(bundle):
    path = os.path.join(bundle, "RESPONSES.csv")
    with open(path, newline="", encoding="utf-8") as handle:
        return {row["packet_number"]: row["packet_id"] for row in csv.DictReader(handle)}


def _existing(path):
    if not os.path.exists(path):
        return [], set()
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    seen = {(row.get("run_id", ""), row.get("reviewer_id", ""), row["packet_id"]) for row in rows}
    return rows, seen


def _load(paths):
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise SystemExit("%s does not contain a JSON array" % path)
        rows.extend(payload)
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--expect", type=int, default=44)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    template = _template(args.bundle)
    incoming = _load(args.inputs)
    existing, seen = _existing(args.csv)

    problems = []
    prepared = []
    for row in incoming:
        number = str(row.get("packet_number", "")).zfill(2)
        packet = row.get("packet_id", "")
        if template.get(number) != packet:
            problems.append("packet %s: id does not match the bundle template" % number)
            continue
        for field in REQUIRED:
            if not str(row.get(field, "")).strip():
                problems.append("packet %s: %s is empty" % (number, field))
        for field in DECISIONS:
            if row.get(field) not in ("yes", "no"):
                problems.append("packet %s: %s must be yes or no" % (number, field))
        key = (args.run_id, args.reviewer_id, packet)
        if key in seen:
            problems.append("packet %s: already present for this run and reviewer" % number)
            continue
        seen.add(key)
        record = {column: "" for column in COLUMNS}
        record.update({key_: str(row.get(key_, "")) for key_ in COLUMNS if key_ in row})
        record["run_id"] = args.run_id
        record["reviewer_id"] = args.reviewer_id
        record["packet_number"] = number
        prepared.append(record)

    if len(prepared) != args.expect:
        problems.append("expected %d rows, prepared %d" % (args.expect, len(prepared)))
    if problems:
        for problem in problems[:20]:
            print("REJECTED %s" % problem, file=sys.stderr)
        raise SystemExit("append refused: %d problem(s)" % len(problems))

    if args.dry_run:
        print(json.dumps({"status": "dry_run", "would_append": len(prepared)}))
        return 0

    prepared.sort(key=lambda item: item["packet_number"])
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in existing + prepared:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})
    flagged = sum(1 for row in prepared if row["single_reasonable_outcome"] == "no")
    print(json.dumps({
        "status": "appended",
        "run_id": args.run_id,
        "reviewer_id": args.reviewer_id,
        "appended": len(prepared),
        "total_rows": len(existing) + len(prepared),
        "alternatives_flagged": flagged,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
