# Brick successor review handbook

Protocol: `office-tiered-human-validation/3.0.0`

This handbook governs human validity and ground-truth review of the 308
calibration and retained structures that support the research claim. The other
220 development, validation, sentinel, and adversarial structures are full-suite
machine-conformance evidence; they are never described as human adjudicated.
This handbook is part of the frozen review protocol. Any change to
this file, the packet schema, the qualification set, or the generator after the
pilot is exported invalidates the pilot and requires a new review-protocol
version. A prompt or oracle defect retires the complete generator version.

## Independence and secrecy

Before receiving packets, each reviewer must attest that they are a real human,
have disclosed conflicts, have the required availability and access, and have
completed compensation arrangements. Reviewers must not:

- inspect generator, oracle, grader, qualification-answer, or assignment source;
- use generative AI or another person to answer a case;
- discuss an assigned case before sealing its response;
- inspect another review, an adjudication, or the oracle before sealing; or
- attempt to infer split membership. Packets intentionally omit split and
  internal instance identities.

An adjudicator is a qualified roster member who was not assigned either review
slot for that case. The adjudicator must independently seal an answer without
seeing either review or the oracle. Only then may the operator resolve the
disagreement.

## What to decide

For each packet, determine:

1. `prompt_valid`: whether the request and supplied initial state define an
   executable, internally consistent office task under the listed tool schemas.
2. `outcome`: the exact canonical list of required observations and business
   effects. Preserve required order and exact values. Do not add a `done` call,
   planning call, or harmless read to the business outcome.
3. `accepted_alternatives`: any materially different outcome that is equally
   valid under the prompt. The successor gate requires this list to be empty;
   identifying a real alternative therefore rejects the generator rather than
   silently broadening the grader.
4. `rationale`: a short explanation sufficient to audit the judgment.

Source reads are required when the answer depends on an email or calendar.
Mutations must be exact: recipient, dates, times, attendees, filenames, rows,
slide order, message content, counts, and ordering all matter. Existing state
must remain unchanged unless the prompt explicitly requests a mutation.

## Qualification

Every active and backup reviewer completes the out-of-suite
`office-review-practice/1.0.0` set. It covers all 11 families plus one seeded
ambiguity case and one accepted-alternative case. Qualification requires:

- at least 12 of 13 exact decisions;
- correct identification of both seeded control cases; and
- a sealed submission for every practice packet.

Qualification cases never count toward the 308 human-validity structures.

## Pilot and full review

Assignments freeze a primary reviewer, a different secondary reviewer, and an
independent adjudicator for every one of the 308 cases before export. The
outcome-blind selection freezes 88 double-review cases: four calibration and
four retained cases per family. Its nested pilot contains two cases from each
split per family. Factor coverage is maximized over constraint profile, workload,
and distractor count before a hash tie-break. No model outcome enters selection.

The planned workload is 308 primary judgments plus 88 secondary judgments, or
396 total. With four reviewers that is exactly 99 planned judgments each; with
three it is exactly 132 each. If review expands to all cases, the workload is
616 judgments, balanced within one judgment per reviewer.

The pilot contains exactly four cases per family: 44 cases and 88 reviews. The
operator reports median and P90 review time, entry errors, exact agreement,
disputes, and adjudication time. It counts toward full completion only when the
generator, handbook, packet schema, and assignments remain unchanged.

Every case requires a valid independently sealed primary response. A secondary
response is required for the frozen 88-case sample and for any case whose
primary response differs from the canonical prompt-derived outcome. A unique
case is a reliability event when its primary differs from that outcome or its
two reviewers disagree. Two reliability events expand secondary review to all
308 cases; this rule is automatic and cannot be waived after seeing results.

Two noncanonical agreeing reviews and every reviewer disagreement require an
independent, cold adjudication. A final noncanonical response, invalid prompt,
or accepted alternative rejects the generator version. The final gate requires
all derived primary, secondary, and adjudication obligations; exact canonical
outcomes; zero accepted alternatives; and no missing or duplicate submissions.

Each qualification, review, adjudication, roster, and staffing publication is
immutable and marker-last: the JSON is created exclusively and its empty
`.complete` marker is created only after the bytes are flushed. Intake rejects
missing, nonempty, orphaned, or non-regular markers and never accepts a changed
sealed response under the same path.

## Operational safety

Use only `python -m bench.next_study_review_ops` commands. Keep packet bundles
and response directories access-controlled. Do not edit the canonical ledger by
hand. Intake never overwrites the checked-in pristine pending ledger; it derives
a separate materialized ledger and refuses to replace any previously sealed
submission. The intake command validates identities, roles, packet hashes, timestamps,
attestations, duplicates, and assignment bindings before deriving a new ledger.
Software cannot create reviewer identities, judgments, attestations, or a live
authorization.
