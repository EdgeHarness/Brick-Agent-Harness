"""Report benchmark results without pooling domains or domain versions."""
import argparse
from collections import defaultdict
import json
import os


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


def _dataset_key(record):
    return (
        record.get("domain", "office_demo"),
        record.get("domain_version", "unversioned"),
    )


def validate_results(results):
    seen = set()
    for index, record in enumerate(results):
        identity = (
            record.get("domain", "office_demo"),
            record.get("domain_version", "unversioned"),
            record.get("model"),
            record.get("condition"),
            record.get("task"),
        )
        if identity in seen:
            raise ValueError(
                f"duplicate benchmark identity at row {index}: {identity!r}"
            )
        seen.add(identity)


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
        aggregate["invalid_calls"] += record.get("invalid_calls", 0)
        aggregate["tool_errors"] += record["tool_errors"]
        aggregate["calls"] += record["llm_calls"]
        aggregate["wall"] += record["wall_seconds"]
        aggregate["out_tokens"] += record.get("output_tokens", 0)
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
            f"| {model} | {raw_cell} | {harness_cell} | "
            f"{delta_cell} |"
        )

    lines += [
        "",
        "## By capability (mean score)",
        "",
        "| capability | "
        + " | ".join(
            f"{model} raw | {model} harness" for model in models
        )
        + " |",
        "|" + "---|" * (1 + 2 * len(models)),
    ]
    for capability in capabilities:
        cells = [CAP_LABELS.get(capability, capability)]
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
            f"{model} raw | {model} harness" for model in models
        )
        + " |",
        "|" + "---|" * (1 + 2 * len(models)),
    ]
    for task, scores in per_task.items():
        cells = [task]
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
