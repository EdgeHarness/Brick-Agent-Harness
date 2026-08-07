# Brick office-v2 benchmark instrument blind audit

## A. Audit identity

- Exact Git commit: `614ef9b4f20b39addf081f8b95bf3213f4f9ee04`
- Generator version: `office-generators/2.1.2`
- Protocol version: `1.4.0`
- Model and model version: `GPT-5.6 (Cursor subagent model: gpt-5.6-sol-medium)`
- Audit date: `2026-08-07`
- Cases actually inspected: `308`
- Splits inspected: development 88; calibration 88; validation 44; sentinel 44; adversarial 44
- Retained cases inspected: `0`
- Per-family counts:
  - `cal_add`: 28
  - `cal_brief`: 28
  - `cal_freeslot`: 28
  - `email_reply`: 28
  - `multi_offsite`: 28
  - `pptx_basic`: 28
  - `pptx_from_email`: 28
  - `preference_learning`: 28
  - `remind_msg`: 28
  - `xlsx_basic`: 28
  - `xlsx_from_email`: 28

The checkout identity was verified before inspection. A final `git status --short` was empty. No repository file was modified, no retained case was read, and no benchmark subject or model call was run.

## B. Executive verdict

**BLOCK**

One high-severity prompt/outcome mismatch survives verification. Every non-retained `preference_learning` case leaves the event-title composition rule unstated while the grader requires one exact, case-sensitive title. A competent agent can apply all selected preference facts and create a semantically correct event with an equally natural title that fails the all-or-nothing grader. Because the 22-cell shakeout includes the `preference_learning` family under both conditions, this defect blocks the shakeout.

## C. Confirmed findings

### B-PL-001 — Exact preference-event title is not specified

- Severity: **high**
- Category: `accepted_alternative`
- Affected family: `preference_learning`
- Scope: all 28 non-retained `preference_learning` cases:
  - `v2.development.preference-learning.00`
  - `v2.development.preference-learning.01`
  - `v2.development.preference-learning.02`
  - `v2.development.preference-learning.03`
  - `v2.development.preference-learning.04`
  - `v2.development.preference-learning.05`
  - `v2.development.preference-learning.06`
  - `v2.development.preference-learning.07`
  - `v2.calibration.preference-learning.00`
  - `v2.calibration.preference-learning.01`
  - `v2.calibration.preference-learning.02`
  - `v2.calibration.preference-learning.03`
  - `v2.calibration.preference-learning.04`
  - `v2.calibration.preference-learning.05`
  - `v2.calibration.preference-learning.06`
  - `v2.calibration.preference-learning.07`
  - `v2.validation.preference-learning.00`
  - `v2.validation.preference-learning.01`
  - `v2.validation.preference-learning.02`
  - `v2.validation.preference-learning.03`
  - `v2.sentinel.preference-learning.00`
  - `v2.sentinel.preference-learning.01`
  - `v2.sentinel.preference-learning.02`
  - `v2.sentinel.preference-learning.03`
  - `v2.adversarial.preference-learning.00`
  - `v2.adversarial.preference-learning.01`
  - `v2.adversarial.preference-learning.02`
  - `v2.adversarial.preference-learning.03`

Exact representative prompt quotation, `v2.development.preference-learning.00`, use subepisode:

> “Schedule exactly one sync with Demi HarborPreferenceLearning0400 on 2028-02-01. The attendee is demi.harborpreferencelearning0400@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here.”

The preceding store subepisode exposes the selected fact `title_prefix=Focus:` but never states a title-construction grammar or an exact final title.

- First reasonable interpretation: apply `title_prefix=Focus:` to the ordinary event title “sync with Demi HarborPreferenceLearning0400”, producing the oracle title `Focus: sync with Demi HarborPreferenceLearning0400`.
- Second reasonable interpretation: apply the same prefix to the equally ordinary title-cased event title “Sync with Demi HarborPreferenceLearning0400”, producing `Focus: Sync with Demi HarborPreferenceLearning0400`. Other semantically equivalent constructions, such as `Focus: Demi HarborPreferenceLearning0400 sync`, are also not excluded.
- Grader consequence: the first title passes. The second title fails even when date, start, end, attendee, location, memory, action count, and all other state are identical. The grader compares the event `title` with direct case-sensitive equality.
- Visible-state evidence: the representative initial state has no events and only the expired distractor memory `subject=demi.harborpreferencelearning0400@office-v2.example status=expired distractor=1 ignore=true`. The public store prompt supplies the prefix as a fact; neither visible state nor either prompt supplies the exact composed title. The `add_event` tool accepts an arbitrary required string for `title` and does not supply a naming convention.
- Persistence: the concern survived the prompt-only reading, the prompt/state-versus-required-outcome sweep across all 28 cases, and source/grader verification. These are three analytic stages in one independent audit, not three independent reviewers; no blind-human corroboration was available.
- Generator/oracle/grader/tool source locations:
  - `domains/office_demo/generators_v2.py:840-925`: family construction.
  - `domains/office_demo/generators_v2.py:876`: generator silently composes `"%s sync with %s"`.
  - `domains/office_demo/generators_v2.py:916-919`: public use prompt omits the composition rule and exact title.
  - `domains/office_demo/outcome_oracle_v2.py:505-575`: oracle reconstructs the task.
  - `domains/office_demo/outcome_oracle_v2.py:554-568`: oracle silently applies the same composition and emits the exact title.
  - `domains/office_demo/reviewed_grader_v2.py:251-256`: event matching requires direct equality for `title`, date, start, end, and attendees.
  - `domains/office_demo/tools.py:52-79`: `add_event.title` is only specified as a required string.
  - `domains/office_demo/world.py:161-178`: world validation strips and stores the supplied title but imposes no naming grammar.
  - Non-retained manifests: `bench/manifests/office-v2/{development,calibration,validation,sentinel,adversarial}.json`.
- Deterministic reproduction:
  1. Load `v2.development.preference-learning.00`.
  2. Select bundle A under `most_recent`; save the five required facts, including `title_prefix=Focus:`.
  3. Construct two otherwise identical added events:
     - A: `title="Focus: sync with Demi HarborPreferenceLearning0400"`
     - B: `title="Focus: Sync with Demi HarborPreferenceLearning0400"`
  4. Hold date `2028-02-01`, time `10:00-10:20`, attendee, location `Video`, action counts, and all preserved state constant.
  5. Apply the grader predicate at `reviewed_grader_v2.py:251-256`. A matches the oracle title; B does not. The audit script reproduced `True` for A and `False` for B.
- Recommended regression test: for every generated `preference_learning` case, require the public use prompt to contain either the exact final title or an explicit, deterministic composition rule including capitalization and spacing. Add a test that constructs the oracle event and at least one semantically valid title variant; before accepting the instrument, the prompt contract must make the variant unambiguously incorrect rather than merely grader-incompatible.
- Blocks the 22-cell shakeout: **yes**. It directly contaminates both `preference_learning` condition cells and violates the zero-confirmed-prompt-defect gate for the instrument as a whole.

## D. Refuted flags

1. **`cal_freeslot` latest-slot start is not printed.** Refuted. `16:30` is uniquely derived from a 30-minute slot wholly inside the explicit `09:00`–`17:00` window. Other-date events are explicitly ignored, and all 28 cases have a unique policy-selected slot.

2. **Calendar feasibility at event boundaries is ambiguous.** Refuted for the generated cases. Existing events that end exactly when a candidate starts do not overlap under ordinary calendar semantics, and no case depends on a nonstandard interpretation to choose among equal candidates.

3. **Policy tie-breaking is missing in several families.** Refuted for this 308-case corpus. A systematic criterion-uniqueness check found no outcome-changing tie in `cal_add`, `email_reply`, `multi_offsite`, `pptx_basic`, `pptx_from_email`, `preference_learning`, `remind_msg`, `xlsx_basic`, or `xlsx_from_email`. Policies with explicit tie rules were also checked against them. Missing hypothetical tie rules therefore do not create two outcomes in any audited case.

4. **`earliest_start` in `preference_learning` might be a lower bound rather than the exact start.** Refuted. The use prompt calls it the “winning start,” singular, and requires application of the selected bundle. The selected start and duration uniquely determine the event interval. The surviving defect is the title grammar, not time selection.

5. **`xlsx_basic` costs may be cents rather than dollars.** Refuted. The prompt supplies literal spreadsheet row values, and the grader compares each `ordered_rows` numeric cell directly to those literals. Its `total_cents` field is an internal normalized representation: `reviewed_grader_v2.py:200-229` checks the sheet total after multiplying the displayed numeric total by 100. The public task has one spreadsheet result.

6. **`xlsx_from_email` amount conversion may be underspecified.** Refuted. Every prompt explicitly says to convert `amount_cents=N` to `N/100` USD dollar values, and all source values, row orders, and totals were consistent.

7. **Source references may point to absent or duplicate emails.** Refuted. Across all 308 cases, every required source ID exists in visible initial state; no initial email ID was duplicated. Prefix-selected source sets matched the required source effects.

8. **`cal_brief` may permit unrelated titles or dates in the first message.** Refuted. The prompt explicitly says “only” priority titles and start times and excludes every other title and date. Visible-state filtering, required ordered mentions, forbidden mentions, and the grader's date-token exclusion align.

9. **Exact oracle reconstruction establishes prompt clarity.** Refuted as a validity argument. The independent oracle reconstructed all 308 recorded outcomes exactly, but for B-PL-001 it duplicates the generator's unstated title-composition convention. Oracle agreement proves internal implementation consistency, not that a reader can infer the convention from the public prompt.

## E. Coverage

- Total: 308/308 non-retained cases.
- Per family: 28/28 in each of the 11 families listed in section A.
- Per split: development 88/88; calibration 88/88; validation 44/44; sentinel 44/44; adversarial 44/44.
- Checks performed:
  - Prompt-only ambiguity lens for referents, quantities, dates/times, ordering, exact text, filenames, and preservation instructions.
  - Prompt plus visible-initial-state consistency checks.
  - Required- and forbidden-effect alignment checks.
  - Source-ID existence and duplicate-state checks.
  - Policy-selection and criterion-uniqueness checks.
  - Calendar overlap, slot arithmetic, date validity, message ordering/count, spreadsheet conversion/total, presentation slide order, and multi-source selection checks.
  - Independent prompt-oracle reconstruction: 308/308 exact matches to recorded required effects.
  - Surviving concern verification against generator, oracle, reviewed grader, world behavior, and tool schema.
  - Final repository-pristine and commit-identity check.
- Cases or files that could not be inspected: none within the authorized non-retained audit scope. Retained cases were deliberately not inspected.
- Remaining uncertainty:
  - This was one independent model audit. There was no blind-human packet review or independent reviewer-corroboration count available.
  - No benchmark subject was run, so this report makes no model-performance claim.
  - The deterministic grader consequence was established from the exact grader predicate and an in-memory equality reproduction; no benchmark execution was needed.

## F. Machine-readable findings

```json
[
  {
    "finding_id": "B-PL-001",
    "severity": "high",
    "family": "preference_learning",
    "case_ids": [
      "v2.development.preference-learning.00",
      "v2.development.preference-learning.01",
      "v2.development.preference-learning.02",
      "v2.development.preference-learning.03",
      "v2.development.preference-learning.04",
      "v2.development.preference-learning.05",
      "v2.development.preference-learning.06",
      "v2.development.preference-learning.07",
      "v2.calibration.preference-learning.00",
      "v2.calibration.preference-learning.01",
      "v2.calibration.preference-learning.02",
      "v2.calibration.preference-learning.03",
      "v2.calibration.preference-learning.04",
      "v2.calibration.preference-learning.05",
      "v2.calibration.preference-learning.06",
      "v2.calibration.preference-learning.07",
      "v2.validation.preference-learning.00",
      "v2.validation.preference-learning.01",
      "v2.validation.preference-learning.02",
      "v2.validation.preference-learning.03",
      "v2.sentinel.preference-learning.00",
      "v2.sentinel.preference-learning.01",
      "v2.sentinel.preference-learning.02",
      "v2.sentinel.preference-learning.03",
      "v2.adversarial.preference-learning.00",
      "v2.adversarial.preference-learning.01",
      "v2.adversarial.preference-learning.02",
      "v2.adversarial.preference-learning.03"
    ],
    "category": "accepted_alternative",
    "prompt_quote": "Schedule exactly one sync with Demi HarborPreferenceLearning0400 on 2028-02-01. The attendee is demi.harborpreferencelearning0400@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here.",
    "reading_1": "Compose the selected prefix and a lower-case descriptive base title: Focus: sync with Demi HarborPreferenceLearning0400.",
    "reading_2": "Compose the same selected prefix and an equally natural title-cased base title: Focus: Sync with Demi HarborPreferenceLearning0400.",
    "grader_consequence": "Reading 1 matches the oracle and passes. Reading 2 fails because event titles are compared by direct case-sensitive equality, despite identical required memory, date, interval, attendee, location, action count, and preserved state.",
    "source_locations": [
      "domains/office_demo/generators_v2.py:840-925",
      "domains/office_demo/generators_v2.py:876",
      "domains/office_demo/generators_v2.py:916-919",
      "domains/office_demo/outcome_oracle_v2.py:505-575",
      "domains/office_demo/outcome_oracle_v2.py:554-568",
      "domains/office_demo/reviewed_grader_v2.py:251-256",
      "domains/office_demo/tools.py:52-79",
      "domains/office_demo/world.py:161-178",
      "bench/manifests/office-v2/development.json",
      "bench/manifests/office-v2/calibration.json",
      "bench/manifests/office-v2/validation.json",
      "bench/manifests/office-v2/sentinel.json",
      "bench/manifests/office-v2/adversarial.json"
    ],
    "deterministic_reproduction": "Load v2.development.preference-learning.00; select bundle A; save the required facts; compare two otherwise identical events titled 'Focus: sync with Demi HarborPreferenceLearning0400' and 'Focus: Sync with Demi HarborPreferenceLearning0400' against reviewed_grader_v2.py:251-256. The former matches the required event title and the latter does not.",
    "recommended_regression": "For every preference_learning case, assert that the public use prompt contains the exact final event title or a complete deterministic title-composition grammar, including capitalization and spacing; add a negative title-variant test whose rejection follows from that public grammar.",
    "disposition": "confirmed_blocks_22_cell_shakeout"
  }
]
```
