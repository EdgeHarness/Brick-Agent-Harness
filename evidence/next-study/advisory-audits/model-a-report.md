# Brick office-v2 prompt audit — Model A (independent blind pass)

## A. Audit identity

- **Exact Git commit:** `614ef9b4f20b39addf081f8b95bf3213f4f9ee04` (verified by `git rev-parse HEAD` in the audit clone as the first action; `git status --short` empty at start and at end of the audit)
- **Generator version:** `office-generators/2.1.2` (`domains/office_demo/generators_v2.py:28`, `GENERATOR_VERSION`; `FAMILY_VERSION = "2.1.2"` line 30)
- **Protocol:** 1.4.0 (as instructed)
- **Oracle:** `office-prompt-oracle/2.1.0` (`domains/office_demo/outcome_oracle_v2.py:16`)
- **Graders in scope:** `generated_grader.py` `GRADER_VERSION = "2.0.0"` (line 13; bound to `required_effects`, used by `bench/s6_run.py:294`, `bench/s7_floor_audit.py:51`, `bench/next_study_quality.py:156`) and `reviewed_grader_v2.py` `GRADER_VERSION = "3.2.0"` / `office-strict-grader/3.2.0` (lines 18–19; bound by the live runner for every non-sentinel cell, `bench/next_study_live.py:993–998`, with machine-compiled outcomes per `bench/next_study_validated_outcomes.py:37–67`). Both are all-or-nothing over their fixed check sets (`harness/grading.py:305`, `candidate_decision = all(values.values())`).
- **Model and model version:** Kimi K3 Max (Cursor subagent model: kimi-k3-max)
- **Audit date:** 2026-08-07
- **Number of cases actually inspected:** 308 (all five non-retained splits: development, calibration, validation, sentinel, adversarial; extracted per runbook §2, count verified `{"families": 11, "cases": 308}`)
- **Per-family case counts:** every family has 28 cases = development 8, calibration 8, validation 4, sentinel 4, adversarial 4:
  - cal_add 28, cal_brief 28, cal_freeslot 28, email_reply 28, multi_offsite 28, pptx_basic 28, pptx_from_email 28, preference_learning 28, remind_msg 28, xlsx_basic 28, xlsx_from_email 28
- **Passes:** three audit passes (p1 per-family Lens A/B with per-case recomputation; p2 state/temporal/tie/envelope battery; p3 grader-alignment and matcher reproductions), all with the same model configuration (recorded per runbook §3: flag counts are configuration-dependent; a single-session audit cannot supply independent configurations — see E.4).
- **Blindness:** `docs/office-v2-prompt-audit.md`, `docs/office-v2-prompt-audit-responses.csv`, `evidence/next-study/office-v2-fable-reconciliation.json`, the retained split, and all prior/other-model reports were never read. No benchmark subject was run (no Ollama / llama.cpp / hosted calls); all grading evidence below is produced by executing the repository's own grader code on synthetic, hand-constructed evidence.

## B. Executive verdict

**BLOCK.**

Two family-wide, deterministically reproduced defects cause an agent that follows the public prompt exactly to fail the grader: FND-01 fails under **both** shipped graders (any Total-row formula other than a bare single-column `=SUM(aN:aM)`), and FND-02 fails under the reviewed grader 3.2.0 that the 22-cell development shakeout actually binds (natural confirmation phrasings rejected by an undisclosed phrase allowlist). FND-03, FND-04 and FND-06 add further correct-agent-fails readings under the live grading path. Because the shakeout draws one development case per family per condition (`bench/next_study_schedule.py:157–213`, 22 unique cells), every family-level finding below lands inside the shakeout envelope.

## C. Confirmed findings

### FND-01 — high — xlsx_basic + xlsx_from_email — Total-row formula must be a bare single-column `=SUM(...)`; prompt says only "using a formula"

- **Affected cases (56):** all 28 xlsx_basic cases — `v2.{development,calibration}.xlsx-basic.{00..07}`, `v2.{validation,sentinel,adversarial}.xlsx-basic.{00..03}` — and all 28 xlsx_from_email cases — `v2.{development,calibration}.xlsx-from-email.{00..07}`, `v2.{validation,sentinel,adversarial}.xlsx-from-email.{00..03}`.
- **Exact prompt quotation:** xlsx_basic: "Add exactly one final Total row using a formula." (e.g. `v2.development.xlsx-basic.00`); xlsx_from_email: "Add one final Total row using a formula." (e.g. `v2.development.xlsx-from-email.00`).
- **First reasonable interpretation:** any spreadsheet formula that computes the column total satisfies "using a formula" — e.g. `=C2+C3+C4`, `=SUM(C2,C3,C4)`, `=SUM(C:C)`, `=SUBTOTAL(9,C2:C4)`.
- **Second reasonable interpretation:** only a single-column range formula of the exact shape `=SUM(C2:C4)` is acceptable.
- **Grader consequence:** the key accepts only reading 2, under **both** graders. The shared numeric evaluator parses only `=SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)` (same column, explicit rows) and otherwise returns `None`; the spreadsheet matcher then fails (`total is None` → `required_outcome` False → whole-case fail, all-or-nothing). A literal precomputed total also fails (`formula_required: True` demands a string starting with `=`). Verified live: `=SUM(C2:C4)` → PASS; `=C2+C3+C4` → FAIL (`failed=required_outcome`) on `v2.development.xlsx-basic.00` with the repository's own `generated_grader.build_grader`.
- **Visible-state evidence:** nothing in the prompt, the initial state, or the agent-visible tool surface discloses the restriction. The native contract description shown to the model is only "A cell string starting with '=' becomes a formula." (`domains/office_demo/tools.py:140–142`, exposed via `bench/next_study_review.py:86–93` using `desc` + `contracts.py` SCHEMAS only); the `=SUM(B2:B3)` example exists solely in the legacy spec's `example` field (`tools.py:152–161`), which the typed-contract path does not transmit.
- **Source locations:** prompts `domains/office_demo/generators_v2.py:361–369` (xlsx_basic) and `:423–430` (xlsx_from_email); effect `formula_required` at `:370–377` and `:431–441`; oracle `domains/office_demo/outcome_oracle_v2.py:165–172`, `:203–214`; shared evaluator `domains/office_demo/strict_graders.py:164–189` (SUM-only regex at line 170); consumers `generated_grader.py:199–209` and `reviewed_grader_v2.py:221–229`.
- **Deterministic reproduction:** `strict_graders._number("=C2+C3+C4", rows) -> None`; `._number("=SUM(C:C)", rows) -> None`; `._number("=SUM(C2,C3,C4)", rows) -> None`; `._number("=SUBTOTAL(9,C2:C4)", rows) -> None`; `._number("=SUM(C2:C4)", rows) -> 4650.0`. End-to-end: synthetic evidence with Total row `["Total","","=C2+C3+C4"]` grades `candidate_decision=False`; with `=SUM(C2:C4)` grades `True`.
- **Recommended regression test:** for one case of each xlsx family, grade synthetic evidence whose Total row uses `=C2+C3+C4` and assert the intended disposition; plus a prompt-level assertion that the string "using a formula" is either tightened to name the accepted shape or the grader accepts arbitrary formulas that evaluate to the total.
- **Blocks the 22-cell shakeout:** YES — both families contribute development cells, and the restriction binds under both grader versions regardless of which outcome compiler is used.

### FND-02 — high — email_reply + multi_offsite — "confirm attendance" is enforced by an undisclosed phrase allowlist (reviewed grader) and is nearly vacuous (generated grader)

- **Affected cases (56):** all 28 email_reply cases — `v2.{development,calibration}.email-reply.{00..07}`, `v2.{validation,sentinel,adversarial}.email-reply.{00..03}` — and all 28 multi_offsite cases — `v2.{development,calibration}.multi-offsite.{00..07}`, `v2.{validation,sentinel,adversarial}.multi-offsite.{00..03}`.
- **Exact prompt quotation:** email_reply: "Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown." multi_offsite: "reply to its sender confirming attendance".
- **First reasonable interpretation:** any body that a reasonable reader would take as confirming attendance satisfies the requirement ("I confirm my attendance.", "Confirming my attendance.", "Attendance confirmed.", "I'll be there.", "I accept and will attend.").
- **Second reasonable interpretation:** only bodies matching the hidden allowlist — `i confirm (that) i will attend`, `i will attend`, `i'll attend`, `i will be there`, `count me in`, with a negation guard — satisfy it.
- **Grader consequence:** under the reviewed grader 3.2.0 (the grader bound for every non-sentinel live cell, `bench/next_study_live.py:993–998`, outcomes machine-compiled with `accepted_alternatives: []` forced by `reviewed_grader_v2.py:67–72` and `next_study_validated_outcomes.py:50–58`), only reading 2 passes. Reproduced end-to-end on `v2.development.email-reply.03`: body "I confirm my attendance. confirmation_code=CONF-17; confirmation_date=2028-05-06; request_id=attendance-1." → generated **PASS**, reviewed **FAIL** (`required_outcome`); "I will attend." control → PASS/PASS. Under the generated grader 2.0.0 the check is a plain substring search for "confirm"/"will attend"/... (`generated_grader.py:111–123`), so a *declining* body "I cannot confirm my attendance. ..." **passes** (reproduced: generated=True) — a wrong-pass — and any body containing the substring "confirm" (e.g. the word "confirmation_code" the prompt itself mandates) satisfies the intent vacuously.
- **Visible-state evidence:** the decision email supplies only `selection_key`, `confirmation_code`, `confirmation_date`; no phrasing guidance exists anywhere the agent can see.
- **Source locations:** prompts `generators_v2.py:494–507` (email_reply), `:986–997` (multi_offsite); oracle `outcome_oracle_v2.py:264–274`, `:636–641` (sets only `body_intent: confirm_attendance`); generated intent `generated_grader.py:111–123`; reviewed intent `reviewed_grader_v2.py:139–152`.
- **Deterministic reproduction:** matcher-level and end-to-end results quoted above; additionally "Yes, I'll be there." fails **both** graders (neither allowlist contains it), and "I am pleased to confirm my attendance at the summit." fails reviewed.
- **Recommended regression test:** a phrase matrix over both graders: at minimum "I confirm my attendance.", "Attendance confirmed.", "I'll be there.", and the declining control "I cannot confirm my attendance."; assert intended dispositions and pin the accepted set in the prompt or in a published rubric.
- **Blocks the 22-cell shakeout:** YES — email_reply and multi_offsite development cells are graded by the reviewed grader in the live runner.

### FND-03 — medium — pptx_basic + pptx_from_email + multi_offsite — reviewed grader requires slide bullet lists to equal the required values exactly; prompts say "include"/"containing"

- **Affected cases (84):** all 28 cases of each of pptx_basic (`v2.{development,calibration}.pptx-basic.{00..07}`, `v2.{validation,sentinel,adversarial}.pptx-basic.{00..03}`), pptx_from_email (`v2.{development,calibration}.pptx-from-email.{00..07}`, `v2.{validation,sentinel,adversarial}.pptx-from-email.{00..03}`), multi_offsite (scope as in FND-02).
- **Exact prompt quotation:** pptx_basic: "Use each section name as its slide title and include that section's exact fact as a bullet."; pptx_from_email: "Use Region as each slide title and include the exact Revenue cents value."; multi_offsite: "bullets containing every listed fact in order".
- **First reasonable interpretation:** "include"/"containing" is at-least semantics — a bullet may carry a label ("Revenue cents: 12538750", "Date: 2028-02-10") and a slide may add further faithful bullets; a title slide may carry a subtitle.
- **Second reasonable interpretation:** each slide's bullet list must be exactly the required values, one normalized bullet per value, nothing else (title slide: zero bullets).
- **Grader consequence:** the reviewed grader accepts only reading 2: `normalized_bullets != normalized_required` fails (`reviewed_grader_v2.py:179–191`). The generated grader implements reading 1 (substring containment, `generated_grader.py:146–158`, plus `minimum_bullets_by_slide`). Reproduced end-to-end on `v2.development.multi-offsite.00`: bullets `["Date: 2028-02-10", "Time: 09:00-15:30", "Location: <hall>"]` (the exact facts with labels) → generated **PASS**, reviewed **FAIL**; bullets equal to the bare facts → PASS/PASS.
- **Visible-state evidence:** source emails present labelled key=value fields ("Region: North; Revenue cents: 12504300; ...", "FINAL OFFSITE: event=...; date=...; ..."), so echoing labels into bullets is the natural agent behavior.
- **Source locations:** prompts `generators_v2.py:251–266`, `:322–328`, `:986–997`; effects `ordered_titles`/`required_values_by_slide` at `:267–274`, `:329–342`, `:1017–1024`; oracle `outcome_oracle_v2.py:87–94`, `:131–142`, `:642–649`; graders as above.
- **Deterministic reproduction:** as above; matcher-level: reviewed `_presentation_matches` compares normalized bullet **lists** for equality; generated checks membership.
- **Recommended regression test:** one packet per pptx family graded with labelled bullets and with an extra faithful bullet; assert intended disposition; align prompt wording ("the slide's only bullets must be exactly …") or relax the reviewed matcher.
- **Blocks the 22-cell shakeout:** YES (reviewed grader path; all three families contribute development cells).

### FND-04 — medium — preference_learning — stored memory must be the facts joined by ";" in listed order; the prompt itself displays them " | "-separated

- **Affected cases (28):** all preference_learning cases — `v2.{development,calibration}.preference-learning.{00..07}`, `v2.{validation,sentinel,adversarial}.preference-learning.{00..03}`.
- **Exact prompt quotation:** "save exactly one memory containing only the selected bundle's applicable facts: subject=… | duration_minutes=20 | earliest_start=10:00 | location=Video | title_prefix=Focus:." (store subepisode of e.g. `v2.development.preference-learning.00`).
- **First reasonable interpretation:** store the listed facts in one memory using any clear separator — most naturally the same " | " separator the prompt itself uses, or ", ".
- **Second reasonable interpretation:** the memory string must be exactly the facts joined by ";" (optionally "; "), in the listed order, with no other content.
- **Grader consequence:** the reviewed grader accepts only reading 2: `added[0].split(";")` (after whitespace/case normalization) must equal the required fact sequence (`reviewed_grader_v2.py:299–305`). The generated grader accepts any in-order substring layout (`generated_grader.py:280–285`). Reproduced end-to-end on `v2.development.preference-learning.00`: memory "subject=… | duration_minutes=20 | …" (the prompt's own format) → generated **PASS**, reviewed **FAIL**; "…;…;…" → PASS/PASS. Note the generated grader also fails to enforce "only" (extra facts in the same memory pass it), see FND-05.
- **Visible-state evidence:** the initial memory distractors are space-separated key=value strings ("subject=… status=expired distractor=1 ignore=true"), so no ";" convention is visible anywhere.
- **Source locations:** prompt `generators_v2.py:895–909` (facts join at `:908`); effect `:877–881`; oracle `outcome_oracle_v2.py:505–576` (`facts = _pipe(fact_text)`, `:542`); graders as above.
- **Deterministic reproduction:** `observed == required` holds only for ";" separators: `" | ".join(facts)` → reviewed FAIL (reproduced), `", ".join(facts)` → FAIL, `";".join(facts)` / `"; ".join(facts)` → PASS.
- **Recommended regression test:** grade one store-episode evidence per separator class (" | ", ", ", ";", newline) and assert intended disposition; or pin the separator in the prompt.
- **Blocks the 22-cell shakeout:** YES (reviewed grader path).

### FND-05 — medium — cal_brief, remind_msg, email_reply, multi_offsite, preference_learning, pptx_from_email, xlsx_from_email — explicit prompt prohibitions are unenforced (or vacuous) under the generated grader 2.0.0: a sloppy agent passes

- **Affected cases (family-wide, 28 each):** cal_brief (`forbidden_mentions`, `forbid_date_tokens` never checked); remind_msg (`exact_mentions` on reminder and message, and the `deadline` mention, never checked); email_reply and multi_offsite (declining bodies pass `confirm_attendance`, see FND-02); preference_learning ("containing **only** the … facts" never enforced — extra facts pass); pptx_from_email, xlsx_from_email, multi_offsite, email_reply (`list_required: True` never enforced — the mandated "List the inbox" step can be skipped and source emails read by guessed ids).
- **Exact prompt quotations:** "Exclude every other title and date." (cal_brief); "Mention every ordered ID exactly once and do not mention any other checkpoint ID." and "committing that the full checklist will be complete by 2028-08-18" (remind_msg); "List the inbox and read every email whose subject begins '…'" (four email-sourcing families); "containing only the selected bundle's applicable facts" (preference_learning).
- **First reasonable interpretation:** the grader enforces what the prompt explicitly forbids or requires.
- **Second reasonable interpretation:** the grader accepts outcomes violating those clauses.
- **Grader consequence:** under generated grader 2.0.0, reading 2 holds. Reproduced end-to-end: `v2.development.cal-brief.00` brief message that also contains "Routine: unrelated 1 at 11:30" → generated **PASS**; same message prefixed "Brief for 2028-02-03: " → generated **PASS**; `v2.development.remind-msg.06` message without the deadline date → generated **PASS**; with an extra "checkpoint-9" mention → generated **PASS**; preference memory with extra facts → generated PASS (matcher: `generated_grader.py:248–270` message, `:271–279` reminder, `:280–285` memory, `:289–313` sources — none consult `forbidden_mentions`, `forbid_date_tokens`, `exact_mentions`, `deadline`, or `list_required`). The reviewed grader 3.2.0 enforces all of these (`reviewed_grader_v2.py:257–290`, `:291–298`, `:299–305`, `:309–331`) — reproduced FAIL for each scenario above — so the two shipped graders disagree on the same prompt clauses.
- **Visible-state evidence:** excluded titles and other dates are visible in `list_events` output; nothing signals they are ungraded.
- **Source locations:** as listed per clause above; oracle emits the fields (`outcome_oracle_v2.py:415–437`, `:484–502`, `:560–565`, `:131–133`, `:203–207`, `:260–264`, `:623–625`).
- **Deterministic reproduction:** quoted e2e results.
- **Recommended regression test:** for each clause, a synthetic evidence violating it must fail under whichever grader is declared authoritative; add a grader-parity test asserting both graders agree on the same evidence corpus.
- **Blocks the 22-cell shakeout:** NO for the live (reviewed) path — but the generated grader is the instrument's offline gate (`bench/s6_run.py:294`, `bench/s7_floor_audit.py:51`, `bench/next_study_quality.py:156`), so every offline gate at this commit under-enforces the prompts.

### FND-06 — medium — pptx_basic — policy `brief_sequence` is named but never defined, and the records' presented order differs materially from the key order

- **Affected cases (10):** `v2.development.pptx-basic.00`, `v2.development.pptx-basic.01`, `v2.development.pptx-basic.02`, `v2.calibration.pptx-basic.00`, `v2.calibration.pptx-basic.01`, `v2.calibration.pptx-basic.02`, `v2.validation.pptx-basic.00`, `v2.validation.pptx-basic.01`, `v2.sentinel.pptx-basic.00`, `v2.adversarial.pptx-basic.00`.
- **Exact prompt quotation:** "Order section slides by policy brief_sequence." (records are presented in canonical section order Context, Evidence, Options, … with shuffled `sequence` values, e.g. `section=Context,sequence=3 | section=Evidence,sequence=1 | section=Options,sequence=2 | …`).
- **First reasonable interpretation:** sort section slides ascending by the `sequence` field (the key's reading).
- **Second reasonable interpretation:** "brief sequence" denotes the canonical brief order — the exact order in which the approved records are presented in the prompt (Context, Evidence, Options, Decision, …).
- **Grader consequence:** reading 2 yields a materially different slide order (e.g. key: Evidence, Options, Context, Decision vs presented: Context, Evidence, Options, Decision) and fails `ordered_titles` equality under **both** graders. Five other families define their policies inline ("Policy definitions: …", e.g. `generators_v2.py:635–645`, `:794–806`); pptx_basic's sibling policies in the same template are self-describing (`risk_descending`, `owner_alphabetical`), making `brief_sequence` the lone opaque policy name in the suite.
- **Visible-state evidence:** none needed (prompt-only family); the prompt supplies both orderings and never says which the policy name means.
- **Source locations:** prompt and selection `generators_v2.py:251–266` (sort at `:242–247`); oracle `outcome_oracle_v2.py:78–83`.
- **Deterministic reproduction:** recompute both orders from the prompt records of any listed case and compare against `required_effects[0]["ordered_titles"]` — done for all 10; key = `sequence`-ascending in every one.
- **Recommended regression test:** a prompt-lint asserting every policy token used in a prompt also appears in a "Policy definitions:" clause within the same prompt.
- **Blocks the 22-cell shakeout:** YES — three of pptx_basic's eight development cases carry `brief_sequence`, so the digest-selected development cell (`next_study_schedule.py:172–178`) can land on it.

### FND-07 — low — cal_add — the "feasible" constraint is undefined in the prompt and never binds in any of the 28 cases

- **Affected cases (28):** all cal_add cases — `v2.{development,calibration}.cal-add.{00..07}`, `v2.{validation,sentinel,adversarial}.cal-add.{00..03}`.
- **Exact prompt quotation:** "Select one feasible request using policy earliest_feasible and add exactly one event…" (and the `highest_priority_feasible` / `shortest_duration_feasible` variants).
- **First reasonable interpretation:** "feasible" excludes candidates overlapping existing calendar events on the inspected date (the key's reading).
- **Second reasonable interpretation:** "feasible" could additionally exclude back-to-back adjacency, attendee conflicts, or other practical constraints.
- **Grader consequence:** none today — verified computationally that in all 28 cases all three candidates are feasible under any overlap convention: the only existing events on the target date are "Existing block N" at 08:00–09:30 (`generators_v2.py:537–545`), while all candidates start at 10:00 or later (`:546–550`), so feasibility can never change the selection; the graded answer equals the policy applied to all three candidates. The defect is instrument validity: the prompt's central instruction is vacuous and the calendar distractors are decorative (though `calendar_read` is still enforced via `source_observed`, so the inspection call itself is not optional).
- **Visible-state evidence:** `list_events` for the target date shows only early-morning blocks; reproduced for all 28 cases (`feas=3` everywhere; selections matched `required_effects` everywhere).
- **Source locations:** `generators_v2.py:529–607`; oracle `outcome_oracle_v2.py:277–329`.
- **Deterministic reproduction:** per-case overlap computation over `initial_state.events` (script output: `feas=3` for every case, all selections match).
- **Recommended regression test:** a generator property test asserting at least one infeasible candidate exists in some cal_add cases (or removing the feasibility language), plus an assertion that the feasibility filter can change the selection for at least one ordinal.
- **Blocks the 22-cell shakeout:** NO (no outcome impact at this commit).

### FND-08 — low — preference_learning — "optional title prefix" reads as omissible, but the key requires it

- **Affected cases (28):** all preference_learning cases (scope as in FND-04).
- **Exact prompt quotation:** "Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here." (use subepisode).
- **First reasonable interpretation:** apply every stored fact, including the title prefix → event titled e.g. "Focus: sync with Demi HarborPreferenceLearning0400".
- **Second reasonable interpretation:** the title prefix is optional and may be omitted → "sync with Demi HarborPreferenceLearning0400".
- **Grader consequence:** reading 2 fails `event_created.title` exact equality under **both** graders (`generated_grader.py:236–247`, `reviewed_grader_v2.py:251–256`); every bundle does carry a `title_prefix`, and the oracle always builds the prefixed title (`outcome_oracle_v2.py:554–557`).
- **Visible-state evidence:** the store episode's bundle list shows `title_prefix=` on every bundle, which mitigates but does not remove the "optional" misreading.
- **Source locations:** prompt `generators_v2.py:913–921`; title construction `:876`; oracle above.
- **Deterministic reproduction:** compare the two candidate titles against `required_effects[1]["title"]` for any case (done for all 28: only the prefixed form matches).
- **Recommended regression test:** none strictly required if FND-04 is fixed; otherwise a prompt-lint forbidding the word "optional" for key-required fields.
- **Blocks the 22-cell shakeout:** NO (the natural primary reading matches the key; residual risk is phrasing-level).

### FND-09 — low — cal_brief + email_reply — required mention order is enforced though the prompts use enumerative phrasing

- **Affected cases (56):** all 28 cal_brief cases (`v2.{development,calibration}.cal-brief.{00..07}`, `v2.{validation,sentinel,adversarial}.cal-brief.{00..03}`) and all 28 email_reply cases (scope as in FND-02).
- **Exact prompt quotation:** cal_brief: "containing '2028-02-03' and 'priority-count=3'"; email_reply: "include the decision's confirmation_code, confirmation_date, and the selected request_id".
- **First reasonable interpretation:** "containing A and B" / "include A, B, and C" are unordered requirements; any order mentioning all items complies.
- **Second reasonable interpretation:** the items must appear in the prompt's listed order.
- **Grader consequence:** cal_brief's auditor message is checked with in-order containment under **both** graders (`generated_grader.py:254–256` via `_contains_in_order`; `reviewed_grader_v2.py:262–264` word-boundary variant), so "priority-count=3 for 2028-02-03" fails both. email_reply mentions are order-free under the generated grader (`generated_grader.py:230–233`, `all(... in ...)`) but in-order under the reviewed grader (`reviewed_grader_v2.py:247–249`); reproduced end-to-end: reordered body → generated **PASS**, reviewed **FAIL**.
- **Visible-state evidence:** none — order sensitivity is invisible to the agent.
- **Source locations:** prompts `generators_v2.py:726–733`, `:500–504`; oracle `outcome_oracle_v2.py:431–436`, `:264–274`; grader lines above.
- **Deterministic reproduction:** quoted e2e results plus `_contains_in_order("priority-count=3 for 2028-02-03", ["2028-02-03","priority-count=3"]) -> False`.
- **Recommended regression test:** reversed-order mention evidence for both message types under both graders; assert intended disposition or make the prompts say "in this order".
- **Blocks the 22-cell shakeout:** YES for email_reply under the reviewed path (development cells exist); cal_brief affects both paths. Severity kept low because agents typically echo the prompt's own order.

### FND-10 — low — cal_brief — "Exclude every other title and date" is selection language, but the reviewed grader bans any ISO date token in the brief message

- **Affected cases (28):** all cal_brief cases (scope as in FND-09).
- **Exact prompt quotation:** "Include, in policy chronological order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. Exclude every other title and date."
- **First reasonable interpretation:** exclude other-dated events and non-priority titles from the briefing (an event-selection rule); a header line naming the brief's own date is harmless context.
- **Second reasonable interpretation:** the message must contain no `YYYY-MM-DD` token whatsoever, including the inspected date itself.
- **Grader consequence:** the reviewed grader implements reading 2 (`forbid_date_tokens`, `reviewed_grader_v2.py:274–277`); the generated grader does not check. Reproduced end-to-end on `v2.development.cal-brief.00`: message "Brief for 2028-02-03: Priority: session 1 at 09:00 | …" → generated **PASS**, reviewed **FAIL**. Mitigating language: "Include … only event titles … and each start time" already narrows message content, hence low severity.
- **Visible-state evidence:** the date is the task's own anchor, repeatedly visible; nothing suggests that mentioning it is fatal.
- **Source locations:** prompt `generators_v2.py:726–733`; effect `forbid_date_tokens` at `:743` and oracle `outcome_oracle_v2.py:428`; graders above.
- **Deterministic reproduction:** quoted e2e result.
- **Recommended regression test:** a brief message containing the inspected date in a preamble, graded under both graders; assert intended disposition.
- **Blocks the 22-cell shakeout:** YES under the reviewed path, but only for agents that add an unprompted date header; low.

## D. Refuted flags

1. **"cal_brief `severity`/`owner` fields are invisible, making `severity_descending`/`owner_alphabetical` uncomputable."** Refuted: the world is seeded verbatim from `initial_state` (`bench/s6_run.py:188–196`), and `list_events` returns the full event dicts including the extra `severity` and `owner` keys (`domains/office_demo/world.py:154–159`); verified present in all 28 cases' state. Both sort keys are distinct within every case (checked all 28).
2. **"Prompt dates may mismatch `today` arithmetic or the key."** Refuted: every prompt uses absolute ISO dates; the oracle re-derives `required_effects` from prompt+state for all 308/308 cases with zero mismatches at this commit, and each family's date offset was independently re-verified (cal_add `today+4`, cal_brief `today+3`, cal_freeslot `today+5`, remind_msg dues `today+3+i` with the commitment date equal to the first ordered due in all 28, preference use-date `today+1` = Tuesday consistent with the `weekday=Tuesday` fact whenever present, multi_offsite event dates `today+10+i`). `today` is a Monday for every ordinal as the generator claims (`generators_v2.py:147–149`).
3. **"remind_msg `dependency_order` prose definition could diverge from the key."** Refuted: the prompt's own algorithm ("repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID") was re-implemented literally and reproduces the key's ordered ID list and reminder date for all 28 cases (e.g. workload ≥2 always yields checkpoint-2 before checkpoint-1 because priority 9 > 5 — the key agrees).
4. **"Email subject-prefix collisions with distractors."** Refuted for all four email-sourcing families and all 112 cases: no DRAFT/unrelated subject starts with the required prefix; matching-source counts equal `sources_read.ids` counts everywhere (`APPROVED REGION … /`, `FINAL PAID RECEIPT CASE NN /`, `… / REQUIRED /`, `OFFSITE SOURCE INDEX …` exact-match).
5. **"Tie risk in policy sort keys."** Refuted: within every case, all sort keys are distinct — email_reply request dates and priorities; pptx_from_email revenues and sequences; xlsx amounts, dates, vendors, costs, items; cal_brief severities and owners; multi_offsite issued/approval/consensus ranks; preference bundle timestamp/priority/scope. No tie-break clause in any prompt ever binds; the verified selections match the key in all 308 cases.
6. **"Adversarial-split cases have different agent-visible wording."** Refuted: templates are identical across splits (split membership exists only in the hidden envelope, `generators_v2.py:8–9`); verified the adversarial envelope label `office-adversarial-ambiguity-v2` and uniform `opportunity_budget`/`forbidden_effects` across all 308 cases; prompt text varies only by ordinal-driven values.
7. **"Reading emails/events mutates state and trips `no_unrequested_state`."** Refuted: `read_email` and `list_emails`/`list_events` perform no mutation (`world.py:134–159`); `state["emails"]` equality with initial state is therefore compatible with required reads.
8. **"multi_offsite 'add the offsite event exactly' leaves attendees unspecified while the key demands `attendees: []`."** Refuted as a practical ambiguity: no attendee is mentioned anywhere in the sources, the world contains no self-identity address, and `add_event` defaults attendees to `[]` (`world.py:169–170`); the only reasonable reading matches the key.
9. **"cal_freeslot `closest_to_preferred` tie-break or preferred-slot occupancy could bind."** Refuted: preferred start 13:30 is free in all 28 cases (busy blocks occupy only 09:00–14:30 half-hour marks), so each policy's answer is constant per policy (earliest 09:30, latest 16:30, closest 13:30) and always matches the key; noted as a uniformity observation, not a defect.
10. **"The xlsx 'Total' row label is unpinned."** Substantially refuted: the prompt says "Total row", and both graders accept any casefolded exact "total" (`_text(total_row[0]) != "total"` fails); only embellished labels ("Grand Total") fail, which is not a reasonable reading of the prompt. Related sub-flag also narrowed: every row including the Total row must span exactly 3 columns (`any(len(row) != columns ...)` fails otherwise) — the prompt's table shape implies this, so it is not reported as a finding.
11. **"xlsx_basic Cost units are ambiguous (dollars vs cents)."** Refuted: the prompt never mentions units; the key's `total_cents = sum * 100` is exactly consistent with entering the given integers and a plain-sum total; verified arithmetically for all 28 cases (and for xlsx_from_email the cents→dollars conversion is explicitly dictated and round-trips exactly).
12. **"Transparent-but-undefined policy names elsewhere (`source_order`, `earliest_feasible`, `sequence_ascending`, `date_ascending`, `chronological`, `most_recent`, etc.) are ambiguous."** Refuted case by case: each name maps to exactly one visible field and direction; the only non-transparent name in the suite is `brief_sequence` (reported as FND-06).
13. **"The reviewed grader might bind outcomes with accepted alternatives."** Refuted: the validated-outcomes compiler hard-codes `accepted_alternatives: []` and `prompt_valid: True` (`bench/next_study_validated_outcomes.py:50–58`), and the reviewed grader refuses construction otherwise (`reviewed_grader_v2.py:67–72`) — which is precisely why FND-01/02/03/04/06 surface as hard failures instead of adjudicated alternatives.

## E. Coverage

1. **Cases reviewed per family:** 28/28 in each of the 11 families (308/308 total; 100 per split: development 88, calibration 88, validation 44, sentinel 44, adversarial 44). Every case's public prompt (both subepisode prompts for preference_learning), visible initial state, required effects, forbidden effects, and envelope fields were extracted and examined.
2. **Checks performed:**
   - Oracle re-derivation (`outcome_oracle_v2.derive_outcome`, `office-prompt-oracle/2.1.0`) vs manifest `required_effects`: 308/308 exact match, 0 errors.
   - Independent per-family recomputation of the policy selection from prompt+state vs `required_effects` (selection, order, dates, times, titles, mentions, totals, slide/row structure): 308/308 match.
   - State-consistency battery: `today` Monday anchor and ordinal arithmetic; no future-dated emails; unique email/event ids; empty preexisting `sent_emails`/`messages`/`artifacts`; prompt date offsets; attendee counts vs workload; memory-distractor subject alignment: 0 issues.
   - Tie-risk battery across all sort keys in all cases: 0 ties.
   - Envelope uniformity: `opportunity_budget`, `forbidden_effects`, `policy_family` (incl. adversarial identity): 0 deviations.
   - Deterministic grader reproductions with the repository's own code (scratch venv outside the repo; bytecode writing disabled; `git status --short` empty afterwards): end-to-end grading of hand-built evidence for xlsx_basic, email_reply, preference_learning, multi_offsite, cal_brief, remind_msg under both graders, plus matcher-level reproductions of `_number`, `_intent`, `_contains_in_order`, `_contains_exact_identifier_sequence`, and the memory split. Tool-contract surface checked via `domains/office_demo/contracts.py`, `tools.py`, `world.py`, `office_files.py`, `normalize.py`, `bench/s6_run.py`, `bench/next_study_live.py`, `bench/next_study_review.py`, `bench/next_study_validated_outcomes.py`, `bench/next_study_schedule.py`, `harness/grading.py`.
   - Prompt-template review of all 33 (family × policy-branch) variants; three audit passes (p1/p2/p3) as recorded in section A.
3. **Cases or files that could not be inspected:** the retained split (220 cases) — prohibited by the audit instruction and runbook §0.3; findings here are family/template-level and carry to retained structurally, but no retained case was opened. The reviewer-handoff bundle (runbook §4) was out of scope per the orchestrator (sections 0, 2, 3, 5 only). No model was run, so no empirical pass-rate evidence exists; all "agent fails/passes" statements are deterministic grader outputs on constructed evidence.
4. **Remaining uncertainty:** (a) all three passes used one model configuration, so cross-configuration persistence (runbook §3) could not be measured; (b) which grader is declared authoritative for any future offline gate is a governance question — findings FND-02/03/04/10 are stated against the reviewed grader that the live runner binds, FND-05 against the generated grader that the offline gates bind, FND-01/06/09 (cal_brief part) against both; (c) the digest-selected development instance per shakeout family depends on the model digest (`next_study_schedule.py:172–178`), so family-level findings are reported for all eight development cases per family.

## F. Machine-readable findings

```json
[
  {
    "finding_id": "FND-01",
    "severity": "high",
    "family": ["xlsx_basic", "xlsx_from_email"],
    "case_ids": "all 28 xlsx_basic cases (v2.{development,calibration}.xlsx-basic.{00..07}, v2.{validation,sentinel,adversarial}.xlsx-basic.{00..03}); all 28 xlsx_from_email cases (v2.{development,calibration}.xlsx-from-email.{00..07}, v2.{validation,sentinel,adversarial}.xlsx-from-email.{00..03})",
    "category": "accepted_alternative",
    "prompt_quote": "Add exactly one final Total row using a formula. / Add one final Total row using a formula.",
    "reading_1": "Any formula computing the column total is acceptable (=C2+C3+C4, =SUM(C2,C3,C4), =SUM(C:C), =SUBTOTAL(9,C2:C4)).",
    "reading_2": "Only a bare single-column range formula =SUM(<col><row>:<col><row>) is acceptable.",
    "grader_consequence": "Reading 2 only, under BOTH graders: shared evaluator strict_graders._number parses only the SUM-range regex and returns None otherwise, so total is None and required_outcome fails (all-or-nothing). A literal precomputed total also fails formula_required. Reproduced end-to-end on v2.development.xlsx-basic.00 (=SUM(C2:C4) PASS; =C2+C3+C4 FAIL).",
    "source_locations": "domains/office_demo/generators_v2.py:361-369,423-430 (prompts), 370-377,431-441 (effects); domains/office_demo/outcome_oracle_v2.py:165-172,203-214; domains/office_demo/strict_graders.py:164-189; domains/office_demo/generated_grader.py:199-209; domains/office_demo/reviewed_grader_v2.py:221-229; agent-visible contract domains/office_demo/tools.py:140-142 via bench/next_study_review.py:86-93 (no SUM example transmitted)",
    "deterministic_reproduction": "_number('=C2+C3+C4', rows) -> None; _number('=SUM(C:C)', rows) -> None; _number('=SUM(C2,C3,C4)', rows) -> None; _number('=SUBTOTAL(9,C2:C4)', rows) -> None; _number('=SUM(C2:C4)', rows) -> 4650.0; e2e generated grader candidate_decision False for the plus-formula evidence, True for SUM-range",
    "recommended_regression": "Grade synthetic evidence whose Total row uses =C2+C3+C4 for one case of each xlsx family and assert intended disposition; add a prompt-lint that 'using a formula' either names the accepted =SUM range shape or the grader accepts any formula evaluating to the total",
    "disposition": "confirmed; blocks the 22-cell shakeout (both families, both graders)"
  },
  {
    "finding_id": "FND-02",
    "severity": "high",
    "family": ["email_reply", "multi_offsite"],
    "case_ids": "all 28 email_reply cases (v2.{development,calibration}.email-reply.{00..07}, v2.{validation,sentinel,adversarial}.email-reply.{00..03}); all 28 multi_offsite cases (v2.{development,calibration}.multi-offsite.{00..07}, v2.{validation,sentinel,adversarial}.multi-offsite.{00..03})",
    "category": "prompt_outcome_mismatch",
    "prompt_quote": "Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. / reply to its sender confirming attendance",
    "reading_1": "Any body a reasonable reader would take as confirming attendance satisfies the requirement (e.g. 'I confirm my attendance.', 'Attendance confirmed.', 'I'll be there.').",
    "reading_2": "Only the hidden allowlist passes: 'i confirm (that) i will attend', 'i will attend', \"i'll attend\", 'i will be there', 'count me in', with a negation guard.",
    "grader_consequence": "Reviewed grader 3.2.0 (bound for every non-sentinel live cell) accepts reading 2 only: 'I confirm my attendance.' FAILS (reproduced on v2.development.email-reply.03). Generated grader 2.0.0 is nearly vacuous: a DECLINING body 'I cannot confirm my attendance.' PASSES (reproduced). 'I'll be there.' fails both graders.",
    "source_locations": "domains/office_demo/generators_v2.py:494-507,986-997 (prompts); domains/office_demo/outcome_oracle_v2.py:264-274,636-641; domains/office_demo/generated_grader.py:111-123; domains/office_demo/reviewed_grader_v2.py:139-152; live binding bench/next_study_live.py:993-998; outcomes bench/next_study_validated_outcomes.py:37-67",
    "deterministic_reproduction": "e2e on v2.development.email-reply.03: strict-phrase body -> PASS/PASS; 'I confirm my attendance.' -> generated PASS, reviewed FAIL; reordered mentions -> generated PASS, reviewed FAIL; declining body -> generated PASS, reviewed FAIL",
    "recommended_regression": "Phrase matrix over both graders including 'I confirm my attendance.', 'Attendance confirmed.', 'I'll be there.', and declining control 'I cannot confirm my attendance.'; pin the accepted phrase set in the prompt or published rubric",
    "disposition": "confirmed; blocks the 22-cell shakeout (reviewed path); generated path has a wrong-pass hole"
  },
  {
    "finding_id": "FND-03",
    "severity": "medium",
    "family": ["pptx_basic", "pptx_from_email", "multi_offsite"],
    "case_ids": "all 28 cases of each family: pptx_basic (v2.{development,calibration}.pptx-basic.{00..07}, v2.{validation,sentinel,adversarial}.pptx-basic.{00..03}); pptx_from_email (v2.{development,calibration}.pptx-from-email.{00..07}, v2.{validation,sentinel,adversarial}.pptx-from-email.{00..03}); multi_offsite (as FND-02)",
    "category": "accepted_alternative",
    "prompt_quote": "include that section's exact fact as a bullet / include the exact Revenue cents value / bullets containing every listed fact in order",
    "reading_1": "At-least semantics: bullets may carry labels ('Revenue cents: 12538750') and slides may add further faithful bullets or a title-slide subtitle.",
    "reading_2": "Each slide's bullet list must equal the required values exactly, one normalized bullet per value; title slide zero bullets.",
    "grader_consequence": "Reviewed grader accepts reading 2 only (normalized bullet-list equality); generated grader implements reading 1 (substring containment). Reproduced end-to-end on v2.development.multi-offsite.00: labelled bullets -> generated PASS, reviewed FAIL; bare facts -> PASS/PASS.",
    "source_locations": "domains/office_demo/generators_v2.py:251-266,322-328,986-997 (prompts), 267-274,329-342,1017-1024 (effects); domains/office_demo/outcome_oracle_v2.py:87-94,131-142,642-649; domains/office_demo/reviewed_grader_v2.py:179-191; domains/office_demo/generated_grader.py:146-158",
    "deterministic_reproduction": "e2e quoted above; matcher: reviewed normalized_bullets != normalized_required -> False; generated membership check passes labelled bullets",
    "recommended_regression": "Grade one packet per pptx family with labelled bullets and with an extra faithful bullet under both graders; align prompt wording ('the slide's only bullets must be exactly ...') or relax the reviewed matcher",
    "disposition": "confirmed; blocks the 22-cell shakeout under the reviewed path"
  },
  {
    "finding_id": "FND-04",
    "severity": "medium",
    "family": ["preference_learning"],
    "case_ids": "all 28 preference_learning cases (v2.{development,calibration}.preference-learning.{00..07}, v2.{validation,sentinel,adversarial}.preference-learning.{00..03})",
    "category": "prompt_outcome_mismatch",
    "prompt_quote": "save exactly one memory containing only the selected bundle's applicable facts: subject=... | duration_minutes=20 | earliest_start=10:00 | location=Video | title_prefix=Focus:.",
    "reading_1": "Store the listed facts in one memory with any clear separator, most naturally the prompt's own ' | ' separator.",
    "reading_2": "The memory must be exactly the facts joined by ';' ('; ' tolerated), in listed order, nothing else.",
    "grader_consequence": "Reviewed grader accepts reading 2 only (split(';') exact sequence equality); generated grader accepts any in-order substring layout. Reproduced end-to-end on v2.development.preference-learning.00: pipe-separated (the prompt's own format) -> generated PASS, reviewed FAIL; semicolon -> PASS/PASS. Generated grader additionally never enforces 'only' (extra facts pass).",
    "source_locations": "domains/office_demo/generators_v2.py:895-909 (prompt), 877-881 (effect); domains/office_demo/outcome_oracle_v2.py:505-576; domains/office_demo/reviewed_grader_v2.py:299-305; domains/office_demo/generated_grader.py:280-285",
    "deterministic_reproduction": "e2e quoted above; matcher: ' | '.join(facts) and ', '.join(facts) fail reviewed equality; ';'.join and '; '.join pass",
    "recommended_regression": "Grade one store-episode evidence per separator class (' | ', ', ', ';', newline) and assert intended disposition; or pin the separator in the prompt",
    "disposition": "confirmed; blocks the 22-cell shakeout under the reviewed path"
  },
  {
    "finding_id": "FND-05",
    "severity": "medium",
    "family": ["cal_brief", "remind_msg", "email_reply", "multi_offsite", "preference_learning", "pptx_from_email", "xlsx_from_email"],
    "case_ids": "all 28 cases of each listed family: cal_brief (forbidden_mentions, forbid_date_tokens unenforced); remind_msg (exact_mentions on reminder and message, deadline mention unenforced); email_reply and multi_offsite (declining bodies pass confirm_attendance; email mention order unenforced); preference_learning ('only' unenforced); pptx_from_email, xlsx_from_email, multi_offsite, email_reply (list_required unenforced)",
    "category": "prompt_outcome_mismatch",
    "prompt_quote": "Exclude every other title and date. / Mention every ordered ID exactly once and do not mention any other checkpoint ID. / committing that the full checklist will be complete by 2028-08-18 / List the inbox and read every email whose subject begins '...' / containing only the selected bundle's applicable facts",
    "reading_1": "The grader enforces the prompt's explicit prohibitions and required steps.",
    "reading_2": "The generated grader 2.0.0 does not check forbidden_mentions, forbid_date_tokens, exact_mentions, deadline, list_required, or the 'only' clause, and its intent check passes declining bodies.",
    "grader_consequence": "Under generated grader 2.0.0 (the offline gate grader) a sloppy agent passes: reproduced end-to-end — cal_brief message containing 'Routine: unrelated 1 at 11:30' PASS; same with an ISO date preamble PASS; remind_msg message without the deadline date PASS; with an extra 'checkpoint-9' PASS; declining confirm body PASS. The reviewed grader 3.2.0 enforces every one of these clauses (all reproduced FAIL), so the two shipped graders disagree on identical evidence.",
    "source_locations": "domains/office_demo/generated_grader.py:248-270 (message), 271-279 (reminder), 280-285 (memory), 289-313 (sources), 111-123 (intent); domains/office_demo/reviewed_grader_v2.py:257-290, 291-298, 299-305, 309-331, 139-164; offline binding bench/s6_run.py:294, bench/s7_floor_audit.py:51, bench/next_study_quality.py:156",
    "deterministic_reproduction": "e2e table in section C (generated PASS / reviewed FAIL for each scenario)",
    "recommended_regression": "For each clause, synthetic violating evidence must fail under the declared authoritative grader; add a grader-parity test over a shared evidence corpus",
    "disposition": "confirmed; does not block the 22-cell shakeout under the reviewed path, but every offline generated-grader gate at this commit under-enforces the prompts"
  },
  {
    "finding_id": "FND-06",
    "severity": "medium",
    "family": ["pptx_basic"],
    "case_ids": ["v2.development.pptx-basic.00", "v2.development.pptx-basic.01", "v2.development.pptx-basic.02", "v2.calibration.pptx-basic.00", "v2.calibration.pptx-basic.01", "v2.calibration.pptx-basic.02", "v2.validation.pptx-basic.00", "v2.validation.pptx-basic.01", "v2.sentinel.pptx-basic.00", "v2.adversarial.pptx-basic.00"],
    "category": "referent",
    "prompt_quote": "Order section slides by policy brief_sequence.",
    "reading_1": "Sort section slides ascending by the records' sequence field (the key's reading).",
    "reading_2": "'brief sequence' denotes the canonical brief order — the exact order in which the approved records are presented in the prompt (Context, Evidence, Options, Decision, ...).",
    "grader_consequence": "Reading 2 yields a materially different ordered_titles list and fails under BOTH graders. The policy is never defined in the prompt, unlike five sibling families that carry 'Policy definitions:' clauses; brief_sequence is the only non-self-describing policy name in the suite.",
    "source_locations": "domains/office_demo/generators_v2.py:251-266 (prompt; sort at 242-247); domains/office_demo/outcome_oracle_v2.py:78-83; contrast policy definitions at generators_v2.py:635-645,794-806,986-997,494-507",
    "deterministic_reproduction": "For all 10 listed cases, presented record order (Context,Evidence,Options,...) differs from key order (sequence-ascending, e.g. Evidence,Options,Context,Decision); key matches sequence-ascending in every case",
    "recommended_regression": "Prompt-lint asserting every policy token used in a prompt also appears in a 'Policy definitions:' clause within the same prompt",
    "disposition": "confirmed; can block the 22-cell shakeout (3 of 8 development pptx_basic cases carry brief_sequence)"
  },
  {
    "finding_id": "FND-07",
    "severity": "low",
    "family": ["cal_add"],
    "case_ids": "all 28 cal_add cases (v2.{development,calibration}.cal-add.{00..07}, v2.{validation,sentinel,adversarial}.cal-add.{00..03})",
    "category": "constraint_conflict",
    "prompt_quote": "Select one feasible request using policy earliest_feasible and add exactly one event...",
    "reading_1": "'feasible' excludes candidates overlapping existing events on the inspected date (key's reading).",
    "reading_2": "'feasible' could additionally exclude back-to-back adjacency or attendee conflicts; the term is never defined in the prompt.",
    "grader_consequence": "None at this commit: in all 28 cases every candidate is feasible under any overlap convention (existing blocks end by 09:30; candidates start at 10:00+), so the feasibility instruction never changes the selection. Instrument-validity defect: the prompt's central constraint is vacuous and the calendar distractors are decorative (calendar_read is still enforced via source_observed).",
    "source_locations": "domains/office_demo/generators_v2.py:529-607 (distractors 537-545, candidates 546-550); domains/office_demo/outcome_oracle_v2.py:277-329",
    "deterministic_reproduction": "Per-case overlap computation over initial_state.events: feas=3/3 for every case; all 28 selections match required_effects",
    "recommended_regression": "Generator property test: at least one infeasible candidate exists in some cal_add ordinal, or the feasibility language is removed; assert the feasibility filter can change the selection for at least one ordinal",
    "disposition": "confirmed as a validity observation; no outcome impact; does not block the 22-cell shakeout"
  },
  {
    "finding_id": "FND-08",
    "severity": "low",
    "family": ["preference_learning"],
    "case_ids": "all 28 preference_learning cases (scope as FND-04)",
    "category": "referent",
    "prompt_quote": "Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here.",
    "reading_1": "Apply every stored fact, including the title prefix (event title 'Focus: sync with <name>').",
    "reading_2": "The title prefix is optional and may be omitted (event title 'sync with <name>').",
    "grader_consequence": "Reading 2 fails event_created title equality under BOTH graders; every bundle carries title_prefix and the oracle always builds the prefixed title.",
    "source_locations": "domains/office_demo/generators_v2.py:913-921 (use prompt), 876 (title); domains/office_demo/outcome_oracle_v2.py:554-557; domains/office_demo/generated_grader.py:236-247; domains/office_demo/reviewed_grader_v2.py:251-256",
    "deterministic_reproduction": "For all 28 cases only the prefixed title equals required_effects[1].title",
    "recommended_regression": "Prompt-lint forbidding the word 'optional' for key-required fields",
    "disposition": "confirmed, low; does not by itself block the 22-cell shakeout"
  },
  {
    "finding_id": "FND-09",
    "severity": "low",
    "family": ["cal_brief", "email_reply"],
    "case_ids": "all 28 cal_brief cases (v2.{development,calibration}.cal-brief.{00..07}, v2.{validation,sentinel,adversarial}.cal-brief.{00..03}); all 28 email_reply cases (scope as FND-02)",
    "category": "accepted_alternative",
    "prompt_quote": "containing '2028-02-03' and 'priority-count=3' / include the decision's confirmation_code, confirmation_date, and the selected request_id",
    "reading_1": "Enumerative: the items may appear in any order as long as all are present.",
    "reading_2": "The items must appear in the prompt's listed order.",
    "grader_consequence": "cal_brief auditor message is order-checked under BOTH graders ('priority-count=3 for 2028-02-03' fails both). email_reply mentions are order-free under the generated grader but in-order under the reviewed grader (reordered body reproduced: generated PASS, reviewed FAIL).",
    "source_locations": "domains/office_demo/generators_v2.py:726-733,500-504 (prompts); domains/office_demo/outcome_oracle_v2.py:431-436,264-274; domains/office_demo/generated_grader.py:254-256,230-233; domains/office_demo/reviewed_grader_v2.py:262-264,247-249",
    "deterministic_reproduction": "_contains_in_order('priority-count=3 for 2028-02-03', ['2028-02-03','priority-count=3']) -> False; e2e reordered email body -> generated PASS, reviewed FAIL",
    "recommended_regression": "Reversed-order mention evidence for both message types under both graders; assert intended disposition or make prompts say 'in this order'",
    "disposition": "confirmed, low; blocks shakeout cells only for agents that reorder (email_reply under reviewed path; cal_brief under both)"
  },
  {
    "finding_id": "FND-10",
    "severity": "low",
    "family": ["cal_brief"],
    "case_ids": "all 28 cal_brief cases (scope as FND-09)",
    "category": "prompt_outcome_mismatch",
    "prompt_quote": "Exclude every other title and date.",
    "reading_1": "Event-selection rule: exclude other-dated events and non-priority titles; a header naming the brief's own inspected date is harmless.",
    "reading_2": "The brief message must contain no YYYY-MM-DD token at all, including the inspected date itself.",
    "grader_consequence": "Reviewed grader implements reading 2 via forbid_date_tokens; generated grader does not check. Reproduced end-to-end on v2.development.cal-brief.00: message prefixed 'Brief for 2028-02-03: ' -> generated PASS, reviewed FAIL. Mitigated by the 'Include ... only event titles ... and each start time' clause.",
    "source_locations": "domains/office_demo/generators_v2.py:726-733 (prompt), 743 (forbid_date_tokens); domains/office_demo/outcome_oracle_v2.py:428; domains/office_demo/reviewed_grader_v2.py:274-277; domains/office_demo/generated_grader.py:248-270",
    "deterministic_reproduction": "e2e quoted above",
    "recommended_regression": "Brief message containing the inspected date in a preamble, graded under both graders; assert intended disposition",
    "disposition": "confirmed, low; blocks shakeout only under the reviewed path and only for agents adding an unprompted date header"
  }
]
```

---

*Audit performed blind per the runbook's constraints: no prior findings, no retained split, no answer-key leakage into the review lens beyond the prescribed Lens-B grader-alignment check, no repository modification, no benchmark subject executed. The scratch extraction and evidence construction lived outside the repo (/tmp); the worktree remained pristine (`git status --short` empty before and after).*
