# Office-v2 prompt audit: reproducible runbook

Hand this file to an agent with a clean checkout. It reproduces the advisory
prompt audit and appends new reviewer rows to
`docs/office-v2-prompt-audit-responses.csv`.

This is advisory tooling. It changes no generator, oracle, grader, manifest or
evidence file, it authorizes nothing, and it makes no model call against the
benchmark. Findings are leads to verify against source, never conclusions.

---

## 0. Before you start

Read these constraints. They are what make the output trustworthy.

1. **Never let a reviewer see the answer key.** A reviewer agent may read only
   `PACKETS.md` and `TOOL_GUIDE.md` from the handoff bundle. Not the grader,
   oracle, manifests, evidence, prior findings, or this runbook's findings
   section. A reviewer that sees the key produces worthless agreement.
2. **Never let an audit reader see prior findings.** Each pass must be blind to
   every earlier pass, otherwise persistence across passes measures nothing.
3. **Retained is not a source.** For audit passes, extract only the five
   non-retained splits. Template structure is shared per family, so findings
   carry to retained without reading it.
4. **Do not modify the worktree while an evidence gate runs.** Gates require
   `git status --short` to print nothing.
5. **A flag is not a finding.** Automated ambiguity detection over-flags and
   also misses rare true positives. Only report what persists across
   independent passes and survives a check against generator or oracle source.

---

## 1. Environment

```bash
cd <repo root>
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-test.txt
```

Use `.venv/bin/python` for anything that imports the domain pack; the office
pack needs `openpyxl` and `python-pptx`. Plain `python3` is fine for the audit
scripts below, which only read JSON and CSV.

---

## 2. Extract the cases (audit passes only)

Writes one JSONL file per family into a scratch directory outside the repo.

```bash
export SCRATCH=/tmp/office-v2-audit && mkdir -p "$SCRATCH"
.venv/bin/python - <<'PY'
import json, os, collections
SCRATCH = os.environ.get("SCRATCH", "/tmp/office-v2-audit")
SPLITS = ["development", "calibration", "validation", "sentinel", "adversarial"]
KEEP = ("id", "family", "split", "prompt", "required_effects", "forbidden_effects",
        "opportunity_budget", "today", "tool_names", "ordered_subepisodes",
        "policy_family", "initial_state")
by_family = collections.defaultdict(list)
for split in SPLITS:
    with open("bench/manifests/office-v2/%s.json" % split) as handle:
        for instance in json.load(handle)["instances"]:
            content = instance["content"]
            by_family[content["family"]].append(
                {key: content[key] for key in KEEP if key in content}
            )
total = 0
for family, rows in by_family.items():
    with open("%s/family-%s.jsonl" % (SCRATCH, family), "w") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    total += len(rows)
print(json.dumps({"families": len(by_family), "cases": total}))
PY
```

Expect `{"families": 11, "cases": 308}`. If the count differs, stop and report
it rather than continuing.

---

## 3. Audit pass (11 readers, one per family)

Spawn one agent per family. They are independent and may run concurrently. Give
each agent exactly this prompt, substituting `FAMILY` and `PASS`:

> You are auditing benchmark task prompts for ambiguity. Read every line (28
> JSON cases) of `SCRATCH/family-FAMILY.jsonl`.
>
> Each case has: id, split, prompt, required_effects (the hidden graded
> outcome), forbidden_effects, opportunity_budget, today, tool_names,
> initial_state (the office world the agent starts in). The task agent sees ONLY
> the prompt, initial_state via tools, and tool schemas. Graded strictly against
> required_effects, all-or-nothing; forbidden_effects also fail it.
>
> For EACH case apply two lenses:
> - Lens A (naive reader, prompt+initial_state only): list any decision a
>   competent agent must make that the prompt does not pin down (which item,
>   which date/time, how many, what order, what exact text/filename, whether to
>   touch existing state).
> - Lens B (grader alignment, now also using required_effects and
>   forbidden_effects): is there a reasonable reading of the prompt under which
>   a CORRECT agent fails the grader, or a sloppy agent passes? Especially: does
>   a materially different but equally valid outcome exist (an "accepted
>   alternative")? Also check prompt-vs-initial_state consistency (references to
>   entities or events that do not exist, date arithmetic errors, overlapping
>   events contradicting instructions).
>
> Be conservative: only flag things a competent human reviewer could genuinely
> read two ways or that mismatch the graded outcome. Do not flag mere
> difficulty, verbosity, or synthetic-looking names.
>
> Write your findings as a JSON array (possibly empty) to
> `SCRATCH/PASS-FAMILY.json`. Each element: `{"id": "...", "lens": "A"|"B",
> "category":
> "referent|quantity|temporal|constraint_conflict|prompt_outcome_mismatch|unstated_action|accepted_alternative|state_inconsistency",
> "quote": "<exact ambiguous span from the prompt>", "reading_1": "...",
> "reading_2": "...", "grader_consequence": "which reading fails or passes
> required_effects and why", "severity": "high|medium|low"}`
>
> Do not read any other files, especially nothing under a git repository and no
> file named REPORT, RUNBOOK, or matching `*-*.json` findings from another pass.
> Then report the number of flags you wrote.

Families: `cal_add`, `cal_brief`, `cal_freeslot`, `email_reply`,
`multi_offsite`, `pptx_basic`, `pptx_from_email`, `preference_learning`,
`remind_msg`, `xlsx_basic`, `xlsx_from_email`.

Run at least three passes with distinct `PASS` prefixes (`p1`, `p2`, `p3`).
More passes give a better persistence estimate. Passes may use different model
configurations; record which, because flag counts are configuration-dependent.

### Cluster the results

```bash
python3 - <<'PY'
import json, glob, os, re, collections
SCRATCH = os.environ.get("SCRATCH", "/tmp/office-v2-audit")
by_cluster = collections.defaultdict(set)
severity = collections.defaultdict(dict)
for path in sorted(glob.glob("%s/p*-*.json" % SCRATCH)):
    match = re.match(r"(p\d+)-(.+)\.json", os.path.basename(path))
    if not match:
        continue
    pass_id, family = match.groups()
    for flag in json.load(open(path)):
        cluster = "%s:%s" % (family, (flag.get("quote") or "")[:40])
        by_cluster[cluster].add(pass_id)
        rank = {"low": 0, "medium": 1, "high": 2}
        current = severity[cluster].get(pass_id, "low")
        severity[cluster][pass_id] = max(current, flag.get("severity", "low"),
                                         key=lambda value: rank.get(value, 0))
for cluster in sorted(by_cluster, key=lambda key: -len(by_cluster[key])):
    passes = sorted(by_cluster[cluster])
    print("%-2d passes  %-8s %s" % (
        len(passes), max(severity[cluster].values(), key=len), cluster))
PY
```

Report only clusters appearing in a majority of passes, and verify each against
generator or oracle source before calling it a defect.

---

## 4. Reviewer pass (appends rows to the CSV)

This is the part that grows the response sheet.

Split the 44 packets across four agents (01-11, 12-22, 23-33, 34-44). Give each
agent exactly this prompt, substituting `LO`, `HI`, `CHUNK`:

> You are an independent reviewer of synthetic office task packets. Your ONLY
> sources are these two files:
> - `reviewer-handoff/brick-office-v2-reviewer-a/PACKETS.md`
> - `reviewer-handoff/brick-office-v2-reviewer-a/TOOL_GUIDE.md`
>
> Review Packets LO through HI inclusive (headers look like `## Packet NN` with
> a `Packet ID:` line). You are reviewing whether each task is clear and has one
> defensible exact answer. You are NOT performing the tasks. Base every judgment
> ONLY on the packet content and tool schemas. Do NOT open any other file, any
> git repository, any manifest, grader, oracle, or report file. You have no
> access to answer keys and must not guess at hidden grading.
>
> For each packet decide:
> - `prompt_clear`: "yes" or "no", is the request unambiguous as written?
> - `enough_information`: "yes" or "no", does prompt plus initial_state plus
>   tools suffice to determine the exact result?
> - `single_reasonable_outcome`: "yes" or "no", is there exactly one defensible
>   outcome? "no" if a materially different outcome is equally valid.
> - `expected_actions_and_exact_details`: your answer: every required read and
>   business change with exact details (recipient, title, date and time,
>   filename, ordering, rows or slides, values, totals, reminder text,
>   remembered facts). If multiple answers are reasonable, put your preferred
>   one here.
> - `reasonable_alternatives`: other materially different but equally valid
>   outcomes, or "" if none.
> - `defect_or_ambiguity`: any ambiguity, contradiction, missing information, or
>   unrealistic rule you noticed, or "" if none. Never force a task to pass.
> - `rationale`: one or two sentences.
> - `minutes_spent`: integer estimate of careful-human-equivalent minutes.
>
> Write a JSON array of row objects to `SCRATCH/review-CHUNK.json`. Each row:
> `{"packet_number": "NN", "packet_id": "<hex id from the packet header>",
> "prompt_clear": "...", "enough_information": "...",
> "single_reasonable_outcome": "...", "expected_actions_and_exact_details":
> "...", "reasonable_alternatives": "...", "defect_or_ambiguity": "...",
> "rationale": "...", "minutes_spent": N}`
>
> Then report how many rows you wrote.

### Append the rows

```bash
python3 docs/office-v2-audit-append.py \
    --run-id r2 --reviewer-id b \
    --bundle reviewer-handoff/brick-office-v2-reviewer-a \
    --csv docs/office-v2-prompt-audit-responses.csv \
    --dry-run \
    "$SCRATCH"/review-*.json
```

Drop `--dry-run` to write. The tool refuses the append unless every row passes:

- `packet_id` matches the bundle's blank `RESPONSES.csv` template
- the three decision fields are exactly `yes` or `no`
- required fields are non-empty
- the `(run_id, reviewer_id, packet_id)` triple is not already present
- the row count equals `--expect` (default 44)

Pick a fresh `--reviewer-id` per independent reviewer and a fresh `--run-id`
per sweep. Existing rows are never rewritten, only appended after.

### Schema

`run_id, reviewer_id, packet_number, packet_id, prompt_clear,
enough_information, single_reasonable_outcome,
expected_actions_and_exact_details, reasonable_alternatives,
defect_or_ambiguity, rationale, minutes_spent`

The first two columns are additions to the official reviewer template so that
several reviewers can accumulate in one file. To export one reviewer in the
official format, filter on those columns and drop them.

---

## 5. What to report

For each candidate defect, give all four or do not report it:

1. the exact quoted span from the prompt
2. the two readings, and which one the answer key accepts
3. the persistence count across passes, plus any blind-reviewer corroboration
4. the root cause in generator or oracle source, with file and line

The strongest evidence is not a flag at all. It is two blind reviewers giving
different answers to the same template while both marking it unambiguous, since
that is a defect the review process cannot catch on its own. Look for it by
grouping reviewer rows by template and comparing
`expected_actions_and_exact_details`.

---

## 6. Cost and scope notes

- A full sweep is 11 audit agents per pass plus 4 reviewer agents. Three passes
  plus one reviewer sweep is roughly 37 agents. Fan them out concurrently.
- Flag counts vary substantially by model configuration. Persistence across
  passes is the signal; raw counts are not.
- Under the frozen `office-tiered-human-validation/3.0.0` handbook, reviewers
  must be human and must not use AI. Rows produced by this runbook are advisory
  analysis and need a re-versioned review protocol before they count as review
  evidence.
- Any generator change invalidates an exported reviewer bundle, since packets
  are bound to their generator version. Re-export before reviewing again.

See `docs/office-v2-prompt-audit.md` for the findings this workflow produced
against `office-generators/2.1.0`.
