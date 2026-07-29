"""Report benchmark results without pooling domains or domain versions."""
import argparse
from collections import defaultdict
import html
import json
import math
import os
import re


CAP_LABELS = {
    "powerpoint": "PowerPoint",
    "excel": "Excel",
    "email": "Email (Gmail-style)",
    "calendar_write": "Calendar: writing",
    "calendar_read": "Calendar: reading",
    "thinking": "Thinking/reasoning",
    "messaging": "Messages",
    "reminders": "Reminders",
    "learning": "Learning (memory)",
}

_DOMAIN_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_TASK_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_TOOL_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-(?:"
    r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*"
    r"))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _dataset_key(record):
    return record["domain"], record["domain_version"]


def validate_results(results):
    if not isinstance(results, list):
        raise TypeError("benchmark results must be a JSON array")
    seen = set()
    for index, record in enumerate(results):
        if not isinstance(record, dict):
            raise TypeError(
                f"benchmark result row {index} must be a JSON object"
            )
        required = {
            "domain",
            "domain_version",
            "model",
            "condition",
            "task",
            "caps",
            "tools",
            "score",
            "checks",
            "finished",
            "parse_failures",
            "invalid_calls",
            "tool_errors",
            "llm_calls",
            "prompt_tokens",
            "output_tokens",
            "wall_seconds",
            "error",
            "max_calls",
        }
        missing = required - set(record)
        if missing:
            raise ValueError(
                f"benchmark result row {index} is missing fields: "
                + ", ".join(sorted(missing))
            )
        if (
            not isinstance(record["domain"], str)
            or not _DOMAIN_ID.fullmatch(record["domain"])
        ):
            raise ValueError(
                f"benchmark result row {index} has an invalid domain"
            )
        if (
            not isinstance(record["domain_version"], str)
            or not _SEMVER.fullmatch(record["domain_version"])
        ):
            raise ValueError(
                f"benchmark result row {index} has an invalid domain_version"
            )
        if not isinstance(record["model"], str) or not record["model"].strip():
            raise ValueError(
                f"benchmark result row {index} has an invalid model"
            )
        if record["condition"] not in {"raw", "harness"}:
            raise ValueError(
                f"benchmark result row {index} has an invalid condition"
            )
        if (
            not isinstance(record["task"], str)
            or not _TASK_ID.fullmatch(record["task"])
        ):
            raise ValueError(
                f"benchmark result row {index} has an invalid task"
            )
        for field, pattern in (
            ("caps", None),
            ("tools", _TOOL_ID),
        ):
            values = record[field]
            if (
                not isinstance(values, list)
                or not all(
                    isinstance(value, str)
                    and bool(value)
                    and (pattern is None or bool(pattern.fullmatch(value)))
                    for value in values
                )
                or len(set(values)) != len(values)
            ):
                raise ValueError(
                    f"benchmark result row {index} has invalid {field}"
                )
        for field in (
            "parse_failures",
            "invalid_calls",
            "tool_errors",
            "llm_calls",
            "prompt_tokens",
            "output_tokens",
            "max_calls",
        ):
            value = record[field]
            minimum = 1 if field == "max_calls" else 0
            if type(value) is not int or value < minimum:
                raise ValueError(
                    f"benchmark result row {index} has an invalid {field}"
                )
        if record["llm_calls"] > record["max_calls"]:
            raise ValueError(
                f"benchmark result row {index} llm_calls exceeds max_calls"
            )
        checks = record["checks"]
        if (
            not isinstance(checks, list)
            or not checks
            or not all(
                isinstance(check, list)
                and len(check) == 2
                and isinstance(check[0], str)
                and bool(check[0])
                and type(check[1]) is bool
                for check in checks
            )
        ):
            raise ValueError(
                f"benchmark result row {index} has invalid checks"
            )
        if type(record["finished"]) is not bool:
            raise ValueError(
                f"benchmark result row {index} has an invalid finished"
            )
        if record["error"] is not None and (
            not isinstance(record["error"], str)
            or not record["error"]
        ):
            raise ValueError(
                f"benchmark result row {index} has an invalid error"
            )
        score = record["score"]
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or not 0 <= score <= 1
        ):
            raise ValueError(
                f"benchmark result row {index} has an invalid score"
            )
        wall = record["wall_seconds"]
        if (
            isinstance(wall, bool)
            or not isinstance(wall, (int, float))
            or not math.isfinite(wall)
            or wall < 0
        ):
            raise ValueError(
                f"benchmark result row {index} has an invalid wall_seconds"
            )
        identity = (
            record["domain"],
            record["domain_version"],
            record["model"],
            record["condition"],
            record["task"],
        )
        if identity in seen:
            raise ValueError(
                f"duplicate benchmark identity at row {index}: {identity!r}"
            )
        seen.add(identity)


def _markdown_cell(value):
    return html.escape(str(value), quote=False).replace(
        "\\", "\\\\"
    ).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _pair_status(model, results):
    by_condition = {"raw": {}, "harness": {}}
    for record in results:
        if (
            record["model"] == model
            and record["condition"] in by_condition
        ):
            by_condition[record["condition"]][record["task"]] = record
    raw = by_condition["raw"]
    harness = by_condition["harness"]
    if not raw or not harness or set(raw) != set(harness):
        return False, "unpaired task sets"
    for task in raw:
        left, right = raw[task], harness[task]
        if (
            "max_calls" not in left
            or "max_calls" not in right
            or "tools" not in left
            or "tools" not in right
            or left["max_calls"] != right["max_calls"]
            or left["tools"] != right["tools"]
            or left["caps"] != right["caps"]
        ):
            return False, "incompatible surfaces"
    return True, ""


def summarize_dataset(domain, version, results):
    models = []
    capabilities = []
    for record in results:
        if record["model"] not in models:
            models.append(record["model"])
        for capability in record.get("caps", []):
            if capability not in capabilities:
                capabilities.append(capability)

    overall = defaultdict(
        lambda: {
            "score": 0.0,
            "n": 0,
            "perfect": 0,
            "parse_failures": 0,
            "invalid_calls": 0,
            "tool_errors": 0,
            "calls": 0,
            "wall": 0.0,
            "out_tokens": 0,
        }
    )
    per_task = defaultdict(dict)
    per_capability = defaultdict(lambda: {"score": 0.0, "n": 0})

    for record in results:
        key = (record["model"], record["condition"])
        aggregate = overall[key]
        aggregate["score"] += record["score"]
        aggregate["n"] += 1
        aggregate["perfect"] += record["score"] >= 0.999
        aggregate["parse_failures"] += record["parse_failures"]
        aggregate["invalid_calls"] += record["invalid_calls"]
        aggregate["tool_errors"] += record["tool_errors"]
        aggregate["calls"] += record["llm_calls"]
        aggregate["wall"] += record["wall_seconds"]
        aggregate["out_tokens"] += record["output_tokens"]
        per_task[record["task"]][key] = record["score"]
        for capability in record.get("caps", []):
            item = per_capability[
                (capability, record["model"], record["condition"])
            ]
            item["score"] += record["score"]
            item["n"] += 1

    lines = [
        f"# Domain dataset: `{domain}@{version}`",
        "",
        "Scores below are comparable only within this domain/version.",
        "",
        "## Overall (mean task score / tasks fully passed)",
        "",
        "| model | raw | harness | delta |",
        "|---|---|---|---|",
    ]
    summary = {
        "domain": domain,
        "domain_version": version,
        "models": models,
        "overall": {},
        "capabilities": {},
        "tasks": {},
    }
    for model in models:
        row = {}
        for condition in ("raw", "harness"):
            aggregate = overall.get((model, condition))
            row[condition] = {
                "mean": (
                    aggregate["score"] / aggregate["n"]
                    if aggregate and aggregate["n"]
                    else None
                ),
                "perfect": aggregate["perfect"] if aggregate else 0,
                "n": aggregate["n"] if aggregate else 0,
                "parse_failures": (
                    aggregate["parse_failures"] if aggregate else 0
                ),
                "invalid_calls": (
                    aggregate["invalid_calls"] if aggregate else 0
                ),
                "tool_errors": (
                    aggregate["tool_errors"] if aggregate else 0
                ),
                "calls": aggregate["calls"] if aggregate else 0,
                "wall": round(aggregate["wall"], 1) if aggregate else 0,
                "out_tokens": (
                    aggregate["out_tokens"] if aggregate else 0
                ),
            }
        summary["overall"][model] = row
        raw_mean = row["raw"]["mean"]
        harness_mean = row["harness"]["mean"]
        paired, pair_note = _pair_status(model, results)
        raw_cell = (
            f"{raw_mean:.2f} "
            f"({row['raw']['perfect']}/{row['raw']['n']})"
            if raw_mean is not None
            else "-"
        )
        harness_cell = (
            f"{harness_mean:.2f} "
            f"({row['harness']['perfect']}/{row['harness']['n']})"
            if harness_mean is not None
            else "-"
        )
        delta_cell = (
            f"{harness_mean - raw_mean:+.2f}"
            if paired
            else f"- ({pair_note})"
        )
        row["comparison"] = {
            "paired": paired,
            "reason": pair_note or None,
            "delta": (
                harness_mean - raw_mean if paired else None
            ),
        }
        lines.append(
            f"| {_markdown_cell(model)} | {raw_cell} | {harness_cell} | "
            f"{delta_cell} |"
        )

    lines += [
        "",
        "## By capability (mean score)",
        "",
        "| capability | "
        + " | ".join(
            f"{_markdown_cell(model)} raw | "
            f"{_markdown_cell(model)} harness"
            for model in models
        )
        + " |",
        "|" + "---|" * (1 + 2 * len(models)),
    ]
    for capability in capabilities:
        cells = [
            _markdown_cell(CAP_LABELS.get(capability, capability))
        ]
        capability_data = {}
        for model in models:
            for condition in ("raw", "harness"):
                item = per_capability.get(
                    (capability, model, condition)
                )
                value = (
                    item["score"] / item["n"]
                    if item and item["n"]
                    else None
                )
                cells.append(f"{value:.2f}" if value is not None else "-")
                capability_data[f"{model}|{condition}"] = value
        summary["capabilities"][capability] = capability_data
        lines.append("| " + " | ".join(cells) + " |")

    lines += [
        "",
        "## By task",
        "",
        "| task | "
        + " | ".join(
            f"{_markdown_cell(model)} raw | "
            f"{_markdown_cell(model)} harness"
            for model in models
        )
        + " |",
        "|" + "---|" * (1 + 2 * len(models)),
    ]
    for task, scores in per_task.items():
        cells = [_markdown_cell(task)]
        task_data = {}
        for model in models:
            for condition in ("raw", "harness"):
                value = scores.get((model, condition))
                cells.append(
                    f"{value:.2f}" if value is not None else "-"
                )
                task_data[f"{model}|{condition}"] = value
        summary["tasks"][task] = task_data
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines), summary


def build_report(results):
    validate_results(results)
    grouped = defaultdict(list)
    for record in results:
        grouped[_dataset_key(record)].append(record)

    markdown_sections = []
    datasets = {}
    for (domain, version), records in grouped.items():
        markdown, summary = summarize_dataset(
            domain, version, records
        )
        markdown_sections.append(markdown)
        datasets[f"{domain}@{version}"] = summary
    return "\n\n---\n\n".join(markdown_sections), {"datasets": datasets}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="results")
    args = parser.parse_args(argv)
    with open(
        os.path.join(args.outdir, "results.json"), encoding="utf-8"
    ) as handle:
        results = json.load(handle)

    markdown, summary = build_report(results)
    print(markdown)
    with open(
        os.path.join(args.outdir, "summary.json"),
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(summary, handle, indent=1)
    with open(
        os.path.join(args.outdir, "SUMMARY.md"),
        "w",
        encoding="utf-8",
    ) as handle:
        handle.write(markdown + "\n")


if __name__ == "__main__":
    main()
