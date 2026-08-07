# Brick office-v2 prompt audit: consolidated review

Instrument: `office-generators/2.1.0`, 528 cases, 11 families.
Audit scope: the 308 non-retained cases (development 88, calibration 88,
validation 44, sentinel 44, adversarial 44). Retained was never read as a
source; template structure is shared per family, so template-level findings
carry to retained.
Date: 2026-08-06. Every claim below is grounded in raw manifest data plus
generator, oracle, and grader source, not detector opinion alone.

Status: both high-confidence defects in section 3 were addressed in
`office-generators/2.1.1` (commit `94b1c93`), which keeps the 2.1.0 seed
namespace so the suite does not churn. This document records the audit as run
against 2.1.0 and is kept as the pre-fix baseline.

---

## 1. Method

Five independent passes, each blind to the others:

| pass | scope |
|---|---|
| pass 1 | 11 family readers, plus adversarial verification and a source check |
| passes 2-4 | 11 family readers each, no access to prior findings |
| pass 5 | 11 family readers, run as a cross-configuration control |

Each reader applied two lenses per case. Lens A read only what the task agent
sees (prompt, initial state, tool schemas) and listed every decision the prompt
leaves unpinned. Lens B added `required_effects` and `forbidden_effects` and
asked one question: is there a reasonable reading under which a correct agent
fails, or a sloppy agent passes.

Separately, four packet-only reviewers filled the full 44-row reviewer-A
response sheet. They saw only `PACKETS.md` and `TOOL_GUIDE.md`. No grader, no
oracle, no manifests, no prior findings, no answer key. This is the closest
available proxy for what an independent human reviewer would produce.

Why five passes: automated ambiguity detection is unreliable in exactly this
task shape. A single pass over-flags and also misses rare true positives. Only
findings that persist across independent passes, and that survive a check
against source, are treated as real.

---

## 2. Replication result

Flags per family per pass:

| family | p2 | p3 | p4 | p5 |
|---|---:|---:|---:|---:|
| cal_add | 0 | 0 | 0 | 0 |
| cal_brief | 49 | 3 | 56 | 3 |
| cal_freeslot | 19 | 19 | 19 | 0 |
| email_reply | 9 | 10 | 9 | 9 |
| multi_offsite | 38 | 38 | 19 | 10 |
| pptx_basic | 10 | 0 | 10 | 0 |
| pptx_from_email | 3 | 1 | 1 | 5 |
| preference_learning | 28 | 77 | 14 | 14 |
| remind_msg | 56 | 5 | 30 | 28 |
| xlsx_basic | 1 | 0 | 1 | 0 |
| xlsx_from_email | 28 | 28 | 28 | 0 |

Clustered by the exact quoted span:

| cluster | passes | severity |
|---|---|---|
| multi_offsite `latest_issued` | 4/4 | high in every pass |
| preference_learning title prefix | 4/4 | high in every pass |
| email_reply mentions and policy name | 4/4 | medium |
| remind_msg checklist mentions | 4/4 | medium |
| cal_brief start-time format | 4/4 | low |
| cal_freeslot preferred start | 3/4 | medium |
| xlsx_from_email amount unit | 3/4 | medium |
| cal_brief exclusion clause | 3/4 | low to medium |
| multi_offsite `approval_rank` | 2/4 | medium |
| all others | 1-2/4 | low |

Two reading notes. First, only two clusters are high in every pass, and they
are the same two the first pass called high. Second, raw counts are
configuration-dependent: one pass drops cal_freeslot, xlsx_from_email,
pptx_basic and xlsx_basic to zero while the others flag them consistently.
Counts therefore measure detector temperament, not defect severity.
Persistence is the signal.

`cal_add` is clean in all five passes.

---

## 3. Confirmed defects

### 3.1 multi_offsite `latest_issued`: visible evidence contradicts the key

Severity: high. Persistence 4/4. Root cause verified in source.

The prompt says: "Select one detail source using policy latest_issued." The
policy is never defined. The index email supplies `issued_rank` a=3, b=2, c=1.
The oracle and generator both select `max(issued_rank)`, so the answer is A.

But `generators_v2.py` stamps each detail email's date as
`ctx.date(-issued_rank)`, which makes A the **oldest** visible email and C the
newest. Every observable date points at C. The graded answer is A.

Consequence: an agent that grounds "latest issued" in the dates it can actually
see fails all four required effects. The failure is not a reasoning error.

Fixed in 2.1.1: the date is now stamped as `ctx.date(-6 + issued_rank)`, so
the highest rank is also the most recent email. Under an equivalent local fix,
16 of 16 `latest_issued` cases had the canonical pick as the newest visible
email, against 0 of 16 before.

### 3.2 preference_learning title: key requires an oracle-only constant

Severity: high. Persistence 4/4. Root cause verified in source.

The store subepisode saves the winning bundle's facts. When
`workload < 5` the saved facts deliberately exclude `title_prefix`. The use
subepisode then says the winning "start, duration, location, and optional title
prefix are not repeated here."

The graded title is `<prefix> sync with <Full Name>` where the prefix falls
back to the literal string `"Sync:"` (`outcome_oracle_v2.py:542`). That string
appears in no prompt and in no visible state. It exists only inside the oracle.

Consequence: in low-workload cases the task is unanswerable from the
information given. An agent that applies the bundle's real prefix, which is
what the prompt instructs, fails. Even in high-workload cases the exact body
text `sync with` and its lowercase casing are unstated.

Fixed in 2.1.1: the hidden default was removed outright. The oracle now
raises `OracleInputError` when the title prefix is not public, so the answer
key can no longer depend on a constant the agent cannot see. This is a
fail-closed fix rather than a documentation fix, and is stronger than merely
stating the default in the prompt.

### 3.3 xlsx_from_email amount unit

Severity: medium. Persistence 3/4, and 4/4 among blind reviewers.

Receipt bodies give `amount_cents=5048`. The prompt asks for a column headed
"Amount" with no unit stated. The grader accepts a cell only when
`round(value * 100) == cents`, meaning it wants `50.48`. Copying the number the
task literally provides fails.

All four blind reviewers wrote integer cents. Three flagged the unit as
unspecified. Independent readers with no answer key converge on the failing
convention, which is the strongest possible signal that the prompt is at fault
rather than the reader.

### 3.4 cal_freeslot preferred start

Severity: medium. Persistence 3/4, exactly 19 cases in every flagging pass.

The prompt states a policy (`earliest_free` or `latest_free`) and also states
"the preferred start is 13:30". In these worlds 13:30 is genuinely free. The
grader accepts only the policy slot. The preference clause is inert under the
graded reading, which is precisely why a careful reader treats it as an
instruction rather than a distractor.

### 3.5 email_reply strictness

Severity: medium. Persistence 4/4.

Three separate issues. Mention matching normalizes case and spacing but not
format, so writing a confirmation date as "February 5, 2028" instead of
"2028-02-05" fails. The policy name `decision_key_match` is never defined, and
the bridge from the decision email's `selection_key` field is unstated. Benign
extra mutations such as `save_memory` or `set_reminder` fail via
`exact_business_effects` even though the prompt constrains only outgoing email.

### 3.6 cal_brief exclusion clause: leniency, not an unfair fail

Severity: medium as a construct issue. Persistence 3/4.

The prompt says "Exclude every other title and date." No forbidden-content
check exists on the graded message, so an agent that dumps every event still
passes. The grader is weaker than the prompt.

This one matters for a different reason than the others: human reviewers
structurally cannot catch it, because they never see the grader. Only code
review finds it.

---

## 4. Refuted

`source_not_read` on xlsx_basic and pptx_basic, 29 flags in the first pass, was
the largest false alarm. `_sources_observed` only enforces reads that appear in
the required effects. With none listed, the check is inert. It cannot fail a
correct agent. Confirmed refuted in the first pass and only 2/4 in replication.

Everything at 1-2/4 persistence is treated as noise unless independently
corroborated.

---

## 5. Blind reviewer results (RESPONSES-review.csv)

44 of 44 rows filled, all packet ids match the template.

| decision | yes | no |
|---|---:|---:|
| prompt_clear | 43 | 1 |
| enough_information | 41 | 3 |
| single_reasonable_outcome | 32 | **12** |

22 rows carry a defect note, 15 list a reasonable alternative. Self-estimated
254 careful-reviewer minutes.

The 12 packets with a reasonable alternative: preference_learning 4,
xlsx_from_email 3, remind_msg 3, cal_freeslot 1, pptx_from_email 1. Under the
frozen handbook the accepted-alternatives list must be empty, so on these
results the review gate rejects the generator version.

### 5.1 The most important single result

Two blind reviewers received the same `latest_issued` template and answered
**oppositely**, and **both marked the task as having a single reasonable
outcome**.

- Packet 07 (`v2.calibration.multi-offsite.00`) chose `offsite-final-c`,
  reasoning that the emails' own dates confirm c is most recent. Canonical is
  `offsite-final-a`. Noncanonical.
- Packet 32 (`v2.retained.multi-offsite.04`) chose `offsite-final-a` by max
  rank. Canonical. No defect noted.

This is worse than a flagged ambiguity. Neither reviewer saw a problem, so the
defect passes review silently while producing wrong ground truth roughly half
the time. The `consensus_supported` variants (packets 04 and 41) were both
answered canonically with no complaint, which isolates the flaw specifically to
`latest_issued`.

### 5.2 preference_learning titles

| packet | canonical title | blind reviewer's title |
|---|---|---|
| 01 | `Sync: sync with Hale Dovetail...` | no title committed |
| 18 | `Deep: sync with Iris Aster...` | prefix `Deep:` only |
| 29 | `Focus: sync with Iris Aster...` | `Focus: Sync with Iris Aster...` |
| 37 | `Sync: sync with Kavi Kestrel...` | `Focus: sync with Kavi Kestrel...` |

Packet 37 is the clean demonstration: the reviewer applied the bundle's own
prefix, which is what the prompt instructs, while the canonical title uses the
oracle-internal default. Packet 29 differs only by the casing of "Sync" versus
"sync", which exact matching also rejects.

---

## 6. Confirmation that the two fixes work

Both fixes were applied locally and the full 528-case suite regenerated under
`office-generators/2.2.0`. `generate_next_study --write` and `--verify` both
pass. A fresh blind audit pass was then run against the regenerated suite:

| cluster | before | after |
|---|---|---|
| multi_offsite `latest_issued` | high in 4/4 passes | **0 flags** |
| preference_learning title | high in 4/4 passes | **0 flags**, family clean |

No new clusters appeared, which is the check that matters most given that a
seed-namespace change regenerates every case. All other known clusters remain
at their baseline sizes, which shows the change was surgical: cal_freeslot 19,
xlsx_from_email 28, remind_msg 28, email_reply 9, multi_offsite
`approval_rank` 9.

---

## 7. Scope of the fix

The two defects are in the fixture (`domains/office_demo/generators_v2.py` and
`outcome_oracle_v2.py`), not in `harness/`. They calibrate the measuring
instrument. They do not touch the code under test and they do not favour either
arm of the `native_tools` versus `harness_full` contrast: both cap the
achievable score for both arms equally, which is the same class of problem as
the D0-B ceiling flags.

Re-versioning is not free. Changing the generator invalidates the bound digest
chain, since the design JSON pins sha256 of the generator, manifests, oracle
audit, grader conformance, semantic simulation, hybrid validation and the
reviewer handoff. Any exported reviewer bundle is bound to its generator
version and needs re-export after a change.

---

## 8. Recommended order of work

Items 1 and 2 are done in 2.1.1. Items 3 onward remain open.

1. ~~**multi_offsite `latest_issued`.**~~ Done in 2.1.1. Strongest evidence in
   the set: 4/4 high, plus a demonstrated blind-reviewer split with both sides
   confident.
2. ~~**preference_learning title.**~~ Done in 2.1.1. 4/4 high, and 4 of 4 blind
   reviewers produced a noncanonical or uncommitted title.
3. **xlsx_from_email amount unit.** One word in the prompt. All four blind
   reviewers got it wrong in the same direction.
4. **cal_freeslot preferred start.** Either remove the inert preference or make
   the policy explicitly override it.
5. **remind_msg.** 4/4 on the checklist-mention binding, and reviewers
   separately noticed that `depends_on` contradicts the due-date ordering
   (packets 08, 09, 31). Weaker evidence, worth a look.
6. **cal_brief exclusion clause.** Grader is weaker than the prompt. Human
   review cannot surface this one.

Not worth acting on: `source_not_read` on the two basic families, and every
cluster below 3/4 persistence.

---

## 9. Caveats

Cross-pass persistence measures model consistency, not truth. Findings 3.1 and
3.2 do not rest on model agreement: both are grounded in verified generator and
oracle source, and both are corroborated by blind reviewers producing
demonstrably noncanonical answers.

The 44 filled rows are automated output. Under the currently frozen
`office-tiered-human-validation/3.0.0` handbook, reviewers must be human and
must not use AI, so this CSV is advisory analysis. It would need a re-versioned
review protocol before counting as review evidence.

Artifacts: `RESPONSES-review.csv` (44 rows), `review-merged.json`,
`reviewer-a-packet-map.json`, and 44 per-family flag files across the five
passes.
