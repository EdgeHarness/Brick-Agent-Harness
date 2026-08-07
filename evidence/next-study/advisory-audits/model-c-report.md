# Brick office-v2 Benchmark Instrument — Blind Audit Report (Model C)

## A. Audit identity

- **Git commit:** `614ef9b4f20b39addf081f8b95bf3213f4f9ee04` (verified via `git rev-parse HEAD`; `git status --short` empty before and after the audit; no repository file was modified)
- **Generator version:** `office-generators/2.1.2` (verified in `bench/manifests/office-v2/manifest-lock.json` and every split manifest)
- **Oracle version:** `office-prompt-oracle/2.1.0`; **live grader identity:** `office-strict-grader/3.2.0` (`domains/office_demo/reviewed_grader_v2.py`)
- **Protocol:** `1.4.0` (verified in `bench/next_study_protocol.json`, `"version":"1.4.0"`)
- **Model and model version:** Claude Fable 5 (Cursor subagent model: claude-fable-5-thinking-high)
- **Audit date:** 2026-08-07
- **Number of cases actually inspected:** 308 of 308 non-retained cases (100%). Every case's public prompt, subepisode prompts, visible initial_state, required_effects, and forbidden_effects were programmatically extracted and checked; the independent oracle was re-executed on all 308 cases; at least one complete case per family was additionally read verbatim, sampled across all five splits.
- **Per-family case counts (all inspected):** cal_add 28, cal_brief 28, cal_freeslot 28, email_reply 28, multi_offsite 28, pptx_basic 28, pptx_from_email 28, preference_learning 28, remind_msg 28, xlsx_basic 28, xlsx_from_email 28. Per split: development 88, calibration 88, validation 44, sentinel 44, adversarial 44. The 220 retained cases were not opened (blindness rule 2); template structure is shared per family, so template-level findings carry to retained.

## B. Executive verdict

**NEEDS_REVIEW.**

The generative core is sound: for all 308 cases the independent prompt-to-outcome oracle (`derive_outcome`) reproduces `required_effects` exactly from the public prompt and visible initial state; all 308 `content_sha256` bindings verify; there are no sorting ties, no infeasible-candidate traps, no free-slot ties, no distractor collisions, no date-arithmetic errors, and every prompt is split-neutral. No case is unsolvable and no case has a nondeterministic answer key.

However, the audit confirms multiple template-level gaps between what the prompt pins down and what the live grader (`reviewed_grader_v2`, used by `bench/next_study_live.py` for every non-sentinel cell including the development shakeout) actually accepts. In 8 of 11 families a prompt-correct agent can fail strict grading on conventions it cannot discover from the prompt, initial state, or tool schemas: an unstated attendance-phrasing whitelist, exact bullet-list equality where the prompt says "include"/"containing", an unstated semicolon memory-separator, an unstated constructed event-title format compared case-sensitively, unstated mention ordering, a total date-token ban behind the ambiguous sentence "Exclude every other title and date", and an undefined priority direction in `cal_add`. The grading pipeline structurally rejects accepted alternatives (`accepted_alternatives` must be `[]`), so none of these can be absorbed at adjudication time. None of these mechanically invalidates the score-masked 22-cell shakeout (they cause strict failures, not instrument-invalid cells), but proceeding to shakeout and calibration before adjudicating the HIGH findings risks committing the frozen instrument with known construct defects; the calibration band (10–22 of 32 per family) could retire the entire generator over grader-convention artifacts rather than genuine task difficulty.

## C. Confirmed findings

Scope shorthand: "all 28 <family> cases" means `v2.development.<fam>.00–07`, `v2.calibration.<fam>.00–07`, `v2.validation.<fam>.00–03`, `v2.sentinel.<fam>.00–03`, `v2.adversarial.<fam>.00–03` (family token with hyphens). Findings carry to the 20 retained cases per family by shared template. Note: sentinel cells are run score-masked without a grader (`next_study_live.py` builds `grader = None` for the sentinel phase), so grader consequences bind on development/calibration/validation/retained cells.

---

### OV2-C-001 — Attendance-confirmation phrasing whitelist (email_reply)
- **Severity:** HIGH
- **Family:** email_reply
- **Affected cases:** all 28 email_reply cases (every decision policy)
- **Prompt quotation:** "Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown."
- **Reading 1 (natural):** any clear confirmation of attendance satisfies "confirm attendance" — e.g. "I confirm attendance.", "I confirm my attendance for attendance-2.", "Happy to confirm I can attend."
- **Reading 2 (grader's):** the body must match one of five regex formulas: "i confirm (that) i will attend", "i will attend", "i'll attend", "i will be there", "count me in".
- **Grader consequence:** `reviewed_grader_v2._intent("confirm_attendance")` implements reading 2 only. Executed reproduction of the exact grader logic: "I confirm attendance." → False; "I confirm my attendance for attendance-2" → False; "Happy to confirm I can attend." → False; "I confirm that I will attend." → True. A reading-1 agent fails `required_outcome`, a strict all-or-nothing failure. Additional robustness defect in the same code: the negation guard (`\b(?:cannot|can't|don't|…)\b[^.!;]{0,40}\b(?:confirm|attend|…)\b`) rejects the affirmative body "I don't want to miss it — I will attend."
- **Visible-state evidence:** neither the prompt, the initial emails, nor the tool schemas disclose any phrasing constraint; the packet an agent sees contains no accepted-phrase list.
- **Source locations:** prompt template `domains/office_demo/generators_v2.py` L494–506; grader `domains/office_demo/reviewed_grader_v2.py` L139–152 (`_intent`), applied at L242–250 (`email_sent`); oracle effect `body_intent: confirm_attendance` `domains/office_demo/outcome_oracle_v2.py` L264–273. The model-free solvability evidence hard-codes the passing sentence "I confirm that I will attend. Count me in." (`bench/next_study_semantic_simulation.py` L213), so it structurally cannot detect this gap.
- **Deterministic reproduction:** run `_intent` (verbatim regexes from `reviewed_grader_v2.py` L139–152) on "I confirm attendance." → False, versus "I will attend" → True; or grade a synthetic evidence record whose sent email body is "I confirm attendance. CONF-04 2028-02-05 attendance-2" against any email_reply case's validated outcome.
- **Recommended regression:** grader unit test asserting a curated list of natural confirmations ("I confirm attendance", "I am confirming my attendance", "I can attend", "I don't want to miss it — I will attend") passes `confirm_attendance`; or amend the prompt to dictate an exact required sentence.
- **Blocks 22-cell shakeout:** yes (interpretive). email_reply contributes 2 of the 22 cells; success there hinges on undisclosed phrasing. It does not mechanically invalidate cells.

---

### OV2-C-002 — Attendance-confirmation phrasing whitelist (multi_offsite)
- **Severity:** HIGH
- **Family:** multi_offsite
- **Affected cases:** all 28 multi_offsite cases
- **Prompt quotation:** "reply to its sender confirming attendance"
- **Reading 1:** any reply that clearly confirms attendance.
- **Reading 2:** only the five whitelisted first-person formulas (same `_intent` as OV2-C-001); here there are no required mentions, so the intent regex is the *only* content check on the reply body.
- **Grader consequence:** identical to OV2-C-001; a reply "Confirming attendance for the Summit." fails `required_outcome`.
- **Visible-state evidence:** no phrasing guidance anywhere in the packet.
- **Source locations:** prompt `generators_v2.py` L986–997; grader `reviewed_grader_v2.py` L139–152, L242–250; oracle `outcome_oracle_v2.py` L636–641.
- **Deterministic reproduction:** as OV2-C-001 with body "Confirming attendance." → `_intent` False.
- **Recommended regression:** shared with OV2-C-001.
- **Blocks shakeout:** yes (interpretive), same rationale.

---

### OV2-C-003 — "include the exact Revenue cents value" graded as exact one-bullet equality (pptx_from_email)
- **Severity:** HIGH
- **Family:** pptx_from_email
- **Affected cases:** all 28 pptx_from_email cases
- **Prompt quotation:** "Use Region as each slide title and include the exact Revenue cents value."
- **Reading 1:** each region slide contains the value somewhere, plausibly labeled — bullet "Revenue cents: 12500000".
- **Reading 2:** each region slide has exactly one bullet whose entire text, after stripping spaces/commas/$, equals the bare integer (e.g. "12500000"), and the title slide has zero body text.
- **Grader consequence:** `reviewed_grader_v2._presentation_matches` enforces `normalized_bullets != normalized_required → fail` per slide — exact list equality, not containment. Executed reproduction: bullets `["12500000"]` → pass; `["Revenue cents: 12500000"]` → fail; `["12,500,000"]` → pass. A reading-1 agent fails `required_outcome`. The superseded `generated_grader.py` used per-slide substring containment (L146–158), i.e. reading 1; the semantics were tightened in the reviewed grader without any prompt change.
- **Visible-state evidence:** source emails give "Revenue cents: 12500000; …", inviting the labeled rendering that fails.
- **Source locations:** prompt `generators_v2.py` L322–328; grader `reviewed_grader_v2.py` L179–191; oracle `outcome_oracle_v2.py` L131–142; lenient predecessor `generated_grader.py` L146–158.
- **Deterministic reproduction:** normalize per `reviewed_grader_v2.py` L184–191 and compare `["revenuecents:12500000"] != ["12500000"]`.
- **Recommended regression:** grader test that a slide bullet "Revenue cents: <N>" (and an extra annotation bullet) passes; or prompt amended to "one bullet containing only the number".
- **Blocks shakeout:** yes (interpretive).

---

### OV2-C-004 — "bullets containing every listed fact in order" graded as exact bullet-list equality (multi_offsite)
- **Severity:** HIGH
- **Family:** multi_offsite
- **Affected cases:** all 28 multi_offsite cases
- **Prompt quotation:** "create office_NN_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order."
- **Reading 1 ("containing"):** bullets may embed the facts with labels or connective text ("Location: JuniperMultiOffsite0300 Collaboration Hall"), and extra bullets are permitted.
- **Reading 2:** exactly len(facts) bullets, where the i-th bullet's entire normalized text equals the i-th fact verbatim.
- **Grader consequence:** `required_values_by_slide=[facts]` goes through the same exact-equality path as OV2-C-003; labeled or annotated bullets fail `required_outcome` even though every fact is present in order.
- **Visible-state evidence:** the detail email lists facts as "facts=2028-02-03 | 09:00-15:30 | …"; copying each pipe segment verbatim as a bullet passes, any decoration fails — nothing in the prompt distinguishes these.
- **Source locations:** prompt `generators_v2.py` L986–997; effect `outcome_oracle_v2.py` L642–649; grader `reviewed_grader_v2.py` L179–191.
- **Deterministic reproduction:** as OV2-C-003 with fact strings.
- **Recommended regression:** grader test with labeled bullets containing all facts in order → must pass, or prompt reworded to "one bullet per fact, containing exactly that fact".
- **Blocks shakeout:** yes (interpretive).

---

### OV2-C-005 — "include that section's exact fact as a bullet" graded as exactly-one-bullet equality (pptx_basic)
- **Severity:** MEDIUM
- **Family:** pptx_basic
- **Affected cases:** all 28 pptx_basic cases
- **Prompt quotation:** "Use each section name as its slide title and include that section's exact fact as a bullet. Do not create any other artifact."
- **Reading 1:** each section slide includes at least that fact as a bullet; additional bullets (owner, risk) are not forbidden; the title slide may carry a subtitle. This reading is corroborated by the effect's own `minimum_bullets_by_slide: [0,1,1,…]` field ("minimum").
- **Reading 2:** each section slide has exactly one bullet equal to the fact, and the title slide has exactly zero body texts.
- **Grader consequence:** the reviewed grader's exact-equality path (L179–191) enforces reading 2 and renders `minimum_bullets_by_slide` vacuous — internal evidence that the tightening was unintended. An agent adding an "Owner: Owner-A" bullet fails `required_outcome`.
- **Visible-state evidence:** prompt supplies section records with owner/risk fields that invite inclusion.
- **Source locations:** prompt `generators_v2.py` L251–266; effect L267–274; grader `reviewed_grader_v2.py` L174–191; lenient predecessor `generated_grader.py` L140–158.
- **Deterministic reproduction:** bullets `["fact", "Owner: Owner-A"]` vs required `["fact"]` → list inequality → fail.
- **Recommended regression:** grader test that extra bullets beyond the required fact pass (honoring `minimum_bullets_by_slide`), or prompt states "exactly one bullet per section slide".
- **Blocks shakeout:** recommend resolving first; not mechanical.

---

### OV2-C-006 — Memory separator convention unstated (preference_learning)
- **Severity:** HIGH
- **Family:** preference_learning
- **Affected cases:** all 28 preference_learning cases
- **Prompt quotation (store subepisode):** "save exactly one memory containing only the selected bundle's applicable facts: subject=… | duration_minutes=20 | earliest_start=10:00 | location=Video | title_prefix=Focus: | weekday=Tuesday."
- **Reading 1:** save one memory string containing those facts — most naturally copying the prompt's own pipe-separated rendering.
- **Reading 2:** save one string whose **semicolon**-separated fields, after trim/casefold, equal the fact list exactly.
- **Grader consequence:** `reviewed_grader_v2` memory check does `added[0].split(";")` and requires field-list equality. Executed reproduction: `"; ".join(facts)` → pass; `" | ".join(facts)` → fail; newline-joined → fail. A reading-1 agent fails `required_outcome` on the store effect. The superseded `generated_grader.py` (L280–285) used in-order containment, which the pipe rendering passes — tightened without prompt change. The solvability simulation hard-codes `"; ".join(effect["required_facts"])` (`next_study_semantic_simulation.py` L250–251), so it cannot detect the gap.
- **Visible-state evidence:** the only separator the agent ever sees for these facts is " | " (in the prompt itself).
- **Source locations:** prompt `generators_v2.py` L895–909; grader `reviewed_grader_v2.py` L299–305; oracle `outcome_oracle_v2.py` L560–565.
- **Deterministic reproduction:** split-comparison shown above, verbatim grader logic.
- **Recommended regression:** grader accepts any unambiguous separator (";", "|", newline) or the prompt states "semicolon-separated".
- **Blocks shakeout:** yes (interpretive).

---

### OV2-C-007 — Constructed event title format unstated and compared case-sensitively (preference_learning)
- **Severity:** HIGH
- **Family:** preference_learning
- **Affected cases:** all 28 preference_learning cases
- **Prompt quotation (use subepisode):** "Schedule exactly one sync with Niko BirchPreferenceLearning1000 on 2028-03-14. The attendee is niko.birchpreferencelearning1000@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
- **Reading 1:** any reasonable title that applies the stored prefix — e.g. "Focus: Sync with Niko BirchPreferenceLearning1000", "Focus: sync", "Focus: 1:1 sync with Niko…".
- **Reading 2:** the title must be exactly `"<title_prefix> sync with <full name>"` with lowercase "sync with", single spaces, and the full name as printed — e.g. "Focus: sync with Niko BirchPreferenceLearning1000".
- **Grader consequence:** `event_created` compares `title` by raw `==` (case-sensitive, no normalization; only `location` is normalized). Executed reproduction: "Focus: Sync with Niko X" ≠ "Focus: sync with Niko X". A reading-1 agent fails `required_outcome`. This is the only family where the graded title is *constructed* by the agent rather than copied verbatim from prompt/email/state.
- **Visible-state evidence:** neither subepisode states the title format; the composition rule (prefix + " " + the prompt phrase "sync with <Name>") must be guessed.
- **Source locations:** title construction `generators_v2.py` L876 (`"%s sync with %s"`); prompt L913–921; grader `reviewed_grader_v2.py` L251–256; oracle `outcome_oracle_v2.py` L554–559.
- **Deterministic reproduction:** string comparison above; or grade evidence with the capitalized-"Sync" title against any preference_learning validated outcome.
- **Recommended regression:** compare titles via `_text` normalization at minimum, and state the exact title format in the use-subepisode prompt.
- **Blocks shakeout:** yes (interpretive).

---

### OV2-C-008 — "Exclude every other title and date" vs total date-token ban (cal_brief)
- **Severity:** MEDIUM
- **Family:** cal_brief
- **Affected cases:** all 28 cal_brief cases
- **Prompt quotation:** "Include, in policy <policy> order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. Exclude every other title and date."
- **Reading 1:** "other" distributes to both nouns — exclude *other* titles and *other* dates; mentioning the briefing date itself (e.g. header "Briefing for 2028-02-24:") in message 1 is allowed.
- **Reading 2:** exclude every other title, and exclude date tokens entirely.
- **Grader consequence:** the effect sets `forbid_date_tokens: true`; `reviewed_grader_v2.py` L274–277 rejects message 1 if it contains *any* `YYYY-MM-DD` token — including the briefing date. Executed reproduction: "Briefing for 2028-02-24: Priority: session 1 at 09:00; …" → date-token regex matches → message rejected → `required_outcome` fails. A reading-1 agent with a dated header fails.
- **Visible-state evidence:** the second message is *required* to contain the same date, sharpening the inference that the date is not globally forbidden.
- **Source locations:** prompt `generators_v2.py` L726–733; effect L742–744; grader `reviewed_grader_v2.py` L274–277.
- **Deterministic reproduction:** regex `(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)` on the header message.
- **Recommended regression:** reword to "Do not include any calendar date in this message", or drop `forbid_date_tokens` for the briefing date itself.
- **Blocks shakeout:** review recommended; not mechanical.

---

### OV2-C-009 — Unstated ordering of the three required mentions (email_reply)
- **Severity:** MEDIUM
- **Family:** email_reply
- **Affected cases:** all 28 email_reply cases
- **Prompt quotation:** "include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown."
- **Reading 1:** all three values present, any order.
- **Reading 2:** the three values must appear in the listed order (code, then date, then request_id).
- **Grader consequence:** `required_mentions` is order-enforced by `_contains_in_order` (`reviewed_grader_v2.py` L109–120 via L247–249). Executed reproduction: "code CONF-04, date 2028-02-05, request attendance-2" → pass; "For request attendance-2: I will attend on 2028-02-05, code CONF-04" → fail. A reading-1 agent fails `required_outcome`.
- **Visible-state evidence:** "include" does not connote ordering; the only mitigation is that the prompt happens to list the fields in the graded order.
- **Source locations:** prompt `generators_v2.py` L500–503; effect L515–522; grader `reviewed_grader_v2.py` L109–120, L247–249.
- **Deterministic reproduction:** shown above with verbatim grader logic.
- **Recommended regression:** grader accepts any order for `email_sent.required_mentions`, or prompt says "in this order".
- **Blocks shakeout:** review recommended; not mechanical.

---

### OV2-C-010 — Unstated ordering in the auditor message (cal_brief)
- **Severity:** MEDIUM
- **Family:** cal_brief
- **Affected cases:** all 28 cal_brief cases
- **Prompt quotation:** "Then send exactly one separate chat message to <auditor> containing '2028-02-24' and 'priority-count=6'."
- **Reading 1:** both tokens present in any order ("priority-count=6 for 2028-02-24").
- **Reading 2:** the date must precede the count.
- **Grader consequence:** `required_mentions: [date, "priority-count=N"]` is order-enforced by `_contains_in_order`. Executed reproduction: "2028-02-24 priority-count=6" → pass; "priority-count=6 for 2028-02-24" → fail.
- **Visible-state evidence:** "containing X and Y" carries no ordering semantics.
- **Source locations:** prompt `generators_v2.py` L730–732; effect L746–751; grader `reviewed_grader_v2.py` L109–120, L262–263.
- **Deterministic reproduction:** shown above.
- **Recommended regression:** unordered matching for this effect, or prompt "in this order".
- **Blocks shakeout:** review recommended; not mechanical.

---

### OV2-C-011 — `highest_priority_feasible` direction undefined; cal_add is the only policy family without a "Policy definitions:" clause
- **Severity:** MEDIUM
- **Family:** cal_add
- **Affected cases (9, exact):** `v2.development.cal-add.03`, `v2.development.cal-add.04`, `v2.development.cal-add.05`, `v2.calibration.cal-add.03`, `v2.calibration.cal-add.04`, `v2.validation.cal-add.02`, `v2.sentinel.cal-add.01`, `v2.sentinel.cal-add.02`, `v2.adversarial.cal-add.01` (all cal_add cases whose policy is `highest_priority_feasible`; priorities are always {5, 9, 4})
- **Prompt quotation:** "Select one feasible request using policy highest_priority_feasible and add exactly one event with that candidate's exact title, time, location, and these attendees: …"
- **Reading 1:** highest priority = largest numeric value → candidate-B (priority=9). This is what the oracle/grader expect.
- **Reading 2:** the widespread P1-is-highest convention → smallest number is highest priority → candidate-C (priority=4).
- **Grader consequence:** the grader requires exactly the candidate-B event (exact title/date/start/end/attendees); a reading-2 agent fails `required_outcome`. Notably, `email_reply` and `remind_msg` prompts explicitly define the same concept ("highest_priority selects the largest priority value"; "priority_descending sorts by largest priority") — demonstrating the authors deemed the definition necessary — but every cal_add prompt omits any "Policy definitions:" clause (verified 0 of 28).
- **Visible-state evidence:** candidate records show bare integers `priority=5|9|4` with no direction hint.
- **Source locations:** prompt `generators_v2.py` L577–591 (no definitions clause); selection L567–573; oracle `outcome_oracle_v2.py` L311–316; grader `reviewed_grader_v2.py` L251–256.
- **Deterministic reproduction:** for any listed case, apply reading 2 to the three candidates → candidate-C event → grade → `required_outcome` False.
- **Recommended regression:** add the same "Policy definitions:" sentence used by email_reply to the cal_add template; regenerate; assert prompt contains "largest priority value".
- **Blocks shakeout:** review recommended. 3 of the 8 development cal_add cases (from which the shakeout draws its single cal_add instance deterministically) are affected.

---

### OV2-C-012 — "earliest_start" fact label vs exact-start grading (preference_learning)
- **Severity:** LOW
- **Family:** preference_learning
- **Affected cases:** all 28 preference_learning cases
- **Prompt quotation:** "earliest_start=10:00" (stored fact) and "the winning start, duration, location, and optional title prefix are not repeated here" (use subepisode).
- **Reading 1:** "earliest_start" is a lower bound; scheduling the sync at 10:30 also honors the preference.
- **Reading 2:** the sync must start exactly at the stored time.
- **Grader consequence:** `event_created` requires `start == "10:00"` and `end == start + duration` exactly; a reading-1 agent fails. Mitigated because the use prompt calls it "the winning start", implying it is *the* start; severity LOW.
- **Source locations:** fact naming `generators_v2.py` L861–867; oracle `outcome_oracle_v2.py` L558–559; grader `reviewed_grader_v2.py` L251–256.
- **Deterministic reproduction:** event at 10:30–10:50 vs expected 10:00–10:20 → equality fails.
- **Recommended regression:** rename the fact to `start=` or state "start exactly at the stored earliest_start".
- **Blocks shakeout:** no.

---

### OV2-C-013 — "one slide titled for the event" vs exact title equality (multi_offsite)
- **Severity:** LOW
- **Family:** multi_offsite
- **Affected cases:** all 28 multi_offsite cases
- **Prompt quotation:** "with exactly one slide titled for the event"
- **Reading 1:** a title that references the event ("Offsite: Initiative … Summit A").
- **Reading 2:** the slide title equals the event name exactly (after casefold/whitespace normalization).
- **Grader consequence:** `ordered_titles` equality via `_text`; decorated titles fail `required_outcome`.
- **Source locations:** prompt `generators_v2.py` L994; grader `reviewed_grader_v2.py` L170–173.
- **Deterministic reproduction:** `_text("Offsite: X Summit A") != _text("X Summit A")`.
- **Recommended regression:** prompt "titled exactly with the event name".
- **Blocks shakeout:** no.

---

### OV2-C-014 — Offsite event must have exactly zero attendees, unstated (multi_offsite)
- **Severity:** LOW
- **Family:** multi_offsite
- **Affected cases:** all 28 multi_offsite cases
- **Prompt quotation:** "Use only the selected detail to add the offsite event exactly"
- **Reading 1:** add the event with the detail-email fields; since no attendees are listed, add none. (Intended.)
- **Reading 2:** an offsite plausibly includes the sender/self as attendee.
- **Grader consequence:** `attendees` must equal `[]` exactly; adding anyone fails `required_outcome`. Contrast: `cal_freeslot` says "with no attendees" explicitly; multi_offsite does not.
- **Source locations:** effect `generators_v2.py` L1002–1010; grader `reviewed_grader_v2.py` L251–256.
- **Deterministic reproduction:** event with `attendees=[sender]` → equality fails.
- **Recommended regression:** add "with no attendees" to the prompt.
- **Blocks shakeout:** no.

---

### OV2-C-015 — Deadline-commitment phrasing whitelist (remind_msg)
- **Severity:** LOW
- **Family:** remind_msg
- **Affected cases:** all 28 remind_msg cases
- **Prompt quotation:** "committing that the full checklist will be complete by 2028-01-27, which is the first ordered item's due date."
- **Reading 1:** any clear commitment ("I'll have everything done by 2028-01-27").
- **Reading 2:** one of four regex families ("i will complete … by", "will be complete by", "i will finish … by", "i commit … deadline").
- **Grader consequence:** executed reproduction: "The full checklist will be complete by 2028-01-27." → pass; "I'll have everything done by 2028-01-27." → fail; "I commit to finishing all items by the 2028-01-27 deadline." → pass. LOW because the prompt itself supplies the canonical passing phrase and echoing it is the path of least resistance.
- **Source locations:** prompt `generators_v2.py` L794–806; grader `reviewed_grader_v2.py` L153–164, L283–288.
- **Deterministic reproduction:** shown above.
- **Recommended regression:** broaden `deadline_commitment` regexes or keep prompt-echo canonical phrasing documented.
- **Blocks shakeout:** no.

---

### OV2-C-016 — Pipeline cannot represent accepted alternatives (systemic)
- **Severity:** MEDIUM
- **Family:** all 11 families (instrument-level)
- **Affected cases:** all 308 (and retained by extension)
- **Prompt quotation:** n/a (grader contract): `if adjudicated_outcome["accepted_alternatives"] != []: raise AdjudicatedGraderError("accepted alternatives must be empty")`.
- **Reading 1 (review workflow's own vocabulary):** review can record "accepted alternatives" for materially-equivalent outcomes.
- **Reading 2 (executable reality):** the reviewed grader hard-rejects any non-empty `accepted_alternatives`, so no alternative can ever be honored at grading time.
- **Grader consequence:** every ambiguity in findings OV2-C-001…015 is structurally forced to single-outcome grading; adjudication cannot repair them without code change.
- **Source locations:** `domains/office_demo/reviewed_grader_v2.py` L69–70; validated outcomes always emit `accepted_alternatives: []` (`bench/next_study_validated_outcomes.py`).
- **Deterministic reproduction:** construct an adjudicated outcome with one alternative → `build_grader` raises.
- **Recommended regression:** either implement alternative-outcome grading or document that prompts must be unambiguous to single-string conventions (and fix the findings above).
- **Blocks shakeout:** no mechanically; it is the reason the HIGH findings cannot be absorbed downstream.

## D. Refuted flags

1. **"cal_brief severity/owner are hidden answer-key fields."** Refuted. The live runner seeds the world verbatim from `initial_state` (`bench/next_study_live.py` L911–917) and `list_events` returns full event dicts (`domains/office_demo/world.py` L154–159), so `severity` and `owner` are agent-visible through the calendar tool. Verified present and pairwise-distinct on all 28 cal_brief cases.
2. **"Using save_memory in non-memory families fails grading."** Refuted for the live instrument. `reviewed_grader_v2` removes `save_memory` from business-effect counting when no memory effect is expected (L370–374) and permits memory growth (L349–352). The stricter behavior exists only in the superseded `generated_grader.py`, which on the v2 path is not used for live grading (it backs office-v1 quality probes, `bench/next_study_quality.py` L23 targets `bench/manifests/office-v1`).
3. **"cal_add feasibility is ambiguous (overlap semantics, other-date events)."** Refuted as consequence-free: verified computationally that in all 28 cal_add cases every distractor block ends by 09:30 while every candidate starts at 10:00 or later, so all three candidates are always feasible under any reasonable overlap reading; the policy alone determines the answer. (The remaining genuine issue is the priority-direction gap, OV2-C-011.)
4. **"cal_freeslot has boundary/tie hazards."** Refuted. Verified in all 28 cases: the preferred slot 13:30 is always free (no equal-distance tie can arise), no closest-tie exists anywhere, the tie-break is defined in the prompt anyway, and "Between 09:00 and 17:00" inclusive-end matches the oracle's slot range (last slot 16:30–17:00).
5. **"remind_msg dependency_order is underspecified."** Refuted. The prompt fully defines the greedy rule and all three tie-break levels ("breaking multiple-eligible ties by larger priority, then earlier due date, then ID"), matching the oracle exactly; priorities and due dates verified pairwise-distinct in all 28 cases.
6. **"Generator, oracle, or manifests may disagree."** Refuted. Re-executed the independent oracle on all 308 cases: `derive_outcome(prompt, initial_state, today) == required_effects` for 308/308; all 308 `content_sha256` bindings recomputed and verified; 308 unique ids and 308 unique prompts.
7. **"The adversarial split hides different/trapped templates."** Refuted. The builders never branch on split; adversarial cases differ only by the `policy_family` label `office-adversarial-ambiguity-v2` and their factorial ordinals (7, 28, 33, 42). Sampled adversarial prompts are structurally identical to other splits. (Cosmetic observation: the label promises "ambiguity" the content does not specially contain.)
8. **"Date arithmetic or weekday traps."** Refuted. Every case's `today` is a Monday (verified 308/308); all prompt dates are absolute ISO dates; the optional `weekday=Tuesday` preference fact is consistent with the scheduled date in every case that includes it.
9. **"Distractors can collide with required selections."** Refuted. Draft/distractor email subjects can never match the required prefixes or the unique index subject; distractor events sit outside candidate windows or on other dates; distractor reminders/memories are inert and protected only by preserve rules the prompts state.
10. **"Spreadsheet type coercion could corrupt grading."** Refuted. `create_spreadsheet` writes values verbatim (`office_files.py` L58–70); `_number` parses numerics, `$`/comma-stripped strings, and `=SUM` ranges; ISO date strings compare as text. The graded conventions (Total label, formula-required, header text) are all stated in the prompts.
11. **"cal_brief policies severity_descending / owner_alphabetical are undefined like cal_add's."** Refuted as harmless: the direction is embedded in the policy names themselves ("descending", "alphabetical"), the keyed fields are visible on the events, and all key values are pairwise-distinct (verified), so no tie-break knowledge is needed. This differs from "highest priority", where numeric direction is a genuine real-world convention conflict (OV2-C-011).
12. **"preference_learning selection policies are undefined in the store prompt."** Refuted as consequence-free: the store prompt *prints the selected bundle's facts verbatim* ("…applicable facts: …"), so the graded memory content and the downstream event parameters are fully determined without interpreting the policy at all.

## E. Coverage

- **Cases reviewed per family:** 28/28 in every one of the 11 families (308/308 non-retained; 100%). Full-field programmatic inspection of every case (prompt, subepisode prompts, initial_state, required_effects, forbidden_effects, today, tool_names, budget) plus verbatim manual reads of at least one complete case per family, sampled across all five splits (development, calibration, validation, sentinel, adversarial).
- **Checks performed:**
  1. Commit, generator (2.1.2), oracle (2.1.0), protocol (1.4.0), and grader (3.2.0) identity verification; manifest-lock cross-check.
  2. Independent oracle re-execution on all 308 cases with equality against `required_effects` (308/308 match; this also proves every prompt parses under the frozen grammar, i.e. is template-conformant and split-neutral).
  3. `content_sha256` recomputation for all 308 instances (308/308 match).
  4. Per-family edge-condition sweep over all 308 cases: sort-key tie detection for every decision policy (none), cal_add candidate feasibility vs distractors (all feasible always), cal_freeslot free-slot enumeration/tie detection (no ties; preferred slot always free), cal_brief severity/owner presence and distinctness plus priority-count agreement, remind_msg priority/due distinctness, email_reply date/priority distinctness and key uniqueness, preference weekday-fact consistency, Monday-anchor verification, id/prompt uniqueness.
  5. Lens A/B template review of all 11 builders in `generators_v2.py` against the oracle (`outcome_oracle_v2.py`), the live grader (`reviewed_grader_v2.py`), the legacy grader (`generated_grader.py`), tool contracts (`tools.py`, `office_files.py`, `world.py`, `pack.py`), and the live runner (`next_study_live.py`: world seeding, grader binding, shakeout schedule).
  6. Executed deterministic reproductions of every reported grader consequence using the verbatim text-matching logic of the reviewed grader (`_text`, `_contains_in_order`, `_intent`, date-token regex, memory split, bullet normalization, title equality).
  7. Verification that the 22-cell shakeout (one development case per family × 2 conditions, score-masked) is graded by `reviewed_grader_v2` bound to oracle-compiled validated outcomes equal to `required_effects`.
- **Cases or files not inspected:** the 220 retained instances (`bench/manifests/office-v2/retained.json` — only its envelope counts were listed; no instance content was opened, per blindness rule 2); `docs/office-v2-prompt-audit.md`, `docs/office-v2-prompt-audit-responses.csv`, `evidence/next-study/office-v2-fable-reconciliation.json`, and any other model's report (blindness rule 1); files under `Brick-Audit-Model-A`, `Brick-Audit-Model-B`, and `audit-outputs/` (confinement).
- **Remaining uncertainty:**
  1. Single-reader session: the runbook's multi-pass persistence statistic (three independent passes per family) could not be produced by one blind agent; in its place, every reported finding was verified directly against generator/oracle/grader source with an executed reproduction, and every refuted flag is documented. Persistence counts are reported as N/A (single pass).
  2. `openpyxl`/`python-pptx` were not installed and the runbook's venv step was skipped to keep the clone pristine; therefore the binary artifact parsers (`_slides`, `_rows`) and the end-to-end grader were verified by close code reading and standalone re-execution of their pure-text logic, not by running the compiled graders on real .pptx/.xlsx payloads.
  3. Harness condition mechanisms (native vs harness prompt scaffolding, budget enforcement) were audited only where they touch prompt/grading surfaces; a full harness audit was out of scope.
  4. No benchmark subject was executed; no Ollama/llama.cpp/hosted call was made; model-behavior likelihoods stated in severity judgments are analytic, not measured.

## F. Machine-readable findings

```json
[
  {
    "finding_id": "OV2-C-001",
    "severity": "high",
    "family": "email_reply",
    "case_ids": ["all 28 non-retained email_reply cases: v2.development.email-reply.00-07, v2.calibration.email-reply.00-07, v2.validation.email-reply.00-03, v2.sentinel.email-reply.00-03, v2.adversarial.email-reply.00-03"],
    "category": "accepted_alternative",
    "prompt_quote": "Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown.",
    "reading_1": "Any clear confirmation of attendance satisfies 'confirm attendance' (e.g. 'I confirm attendance.', 'I confirm my attendance', 'Happy to confirm I can attend').",
    "reading_2": "The body must match one of five whitelisted regex formulas: 'i confirm (that) i will attend', 'i will attend', \"i'll attend\", 'i will be there', 'count me in'.",
    "grader_consequence": "reviewed_grader_v2._intent('confirm_attendance') implements reading 2 only; reading-1 bodies fail required_outcome (strict all-or-nothing). Verified: 'I confirm attendance.' -> False; 'I confirm that I will attend.' -> True. Negation guard also rejects the affirmative 'I don't want to miss it - I will attend'.",
    "source_locations": ["domains/office_demo/generators_v2.py:494-506", "domains/office_demo/reviewed_grader_v2.py:139-152", "domains/office_demo/reviewed_grader_v2.py:242-250", "domains/office_demo/outcome_oracle_v2.py:264-273", "bench/next_study_semantic_simulation.py:213"],
    "deterministic_reproduction": "Run the verbatim _intent regexes (reviewed_grader_v2.py L139-152) on body 'I confirm attendance. CONF-04 2028-02-05 attendance-2' -> False; on 'I will attend ...' -> True.",
    "recommended_regression": "Grader unit test asserting natural confirmations ('I confirm attendance', 'I can attend', 'I am confirming my attendance') pass confirm_attendance, or prompt amended to dictate the exact required sentence.",
    "disposition": "confirmed; blocks shakeout interpretively (no mechanical cell invalidation)"
  },
  {
    "finding_id": "OV2-C-002",
    "severity": "high",
    "family": "multi_offsite",
    "case_ids": ["all 28 non-retained multi_offsite cases: v2.development.multi-offsite.00-07, v2.calibration.multi-offsite.00-07, v2.validation.multi-offsite.00-03, v2.sentinel.multi-offsite.00-03, v2.adversarial.multi-offsite.00-03"],
    "category": "accepted_alternative",
    "prompt_quote": "reply to its sender confirming attendance",
    "reading_1": "Any reply clearly confirming attendance.",
    "reading_2": "Only the five whitelisted first-person formulas; the intent regex is the only content check on this reply.",
    "grader_consequence": "'Confirming attendance for the Summit.' fails _intent -> required_outcome False for the whole case.",
    "source_locations": ["domains/office_demo/generators_v2.py:986-997", "domains/office_demo/reviewed_grader_v2.py:139-152", "domains/office_demo/reviewed_grader_v2.py:242-250", "domains/office_demo/outcome_oracle_v2.py:636-641"],
    "deterministic_reproduction": "_intent('Confirming attendance.', 'confirm_attendance') -> False using verbatim grader regexes.",
    "recommended_regression": "Shared with OV2-C-001.",
    "disposition": "confirmed; blocks shakeout interpretively"
  },
  {
    "finding_id": "OV2-C-003",
    "severity": "high",
    "family": "pptx_from_email",
    "case_ids": ["all 28 non-retained pptx_from_email cases: v2.development.pptx-from-email.00-07, v2.calibration.pptx-from-email.00-07, v2.validation.pptx-from-email.00-03, v2.sentinel.pptx-from-email.00-03, v2.adversarial.pptx-from-email.00-03"],
    "category": "accepted_alternative",
    "prompt_quote": "Use Region as each slide title and include the exact Revenue cents value.",
    "reading_1": "Each region slide contains the value somewhere, possibly labeled ('Revenue cents: 12500000').",
    "reading_2": "Each region slide has exactly one bullet whose entire normalized text equals the bare integer; the title slide has zero body text.",
    "grader_consequence": "reviewed grader requires normalized bullet-list EQUALITY per slide (required_values_by_slide); labeled bullets fail required_outcome. Verified: ['Revenue cents: 12500000'] -> fail, ['12500000'] and ['12,500,000'] -> pass. Superseded generated_grader used substring containment (reading 1); tightened without prompt change.",
    "source_locations": ["domains/office_demo/generators_v2.py:322-328", "domains/office_demo/reviewed_grader_v2.py:179-191", "domains/office_demo/outcome_oracle_v2.py:131-142", "domains/office_demo/generated_grader.py:146-158"],
    "deterministic_reproduction": "Normalize per reviewed_grader_v2.py L184-191: ['revenuecents:12500000'] != ['12500000'].",
    "recommended_regression": "Grader test: slide bullet 'Revenue cents: <N>' (plus an extra annotation bullet) must pass; or prompt reworded to 'one bullet containing only the number'.",
    "disposition": "confirmed; blocks shakeout interpretively"
  },
  {
    "finding_id": "OV2-C-004",
    "severity": "high",
    "family": "multi_offsite",
    "case_ids": ["all 28 non-retained multi_offsite cases (same enumeration as OV2-C-002)"],
    "category": "accepted_alternative",
    "prompt_quote": "create office_NN_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order.",
    "reading_1": "'containing' permits labels/extra text around each fact and extra bullets, as long as every fact appears in order.",
    "reading_2": "Exactly len(facts) bullets; the i-th bullet's entire normalized text equals the i-th fact verbatim.",
    "grader_consequence": "Exact-equality path (required_values_by_slide=[facts]); 'Location: <fact>' style bullets fail required_outcome despite containing every fact in order.",
    "source_locations": ["domains/office_demo/generators_v2.py:986-997", "domains/office_demo/outcome_oracle_v2.py:642-649", "domains/office_demo/reviewed_grader_v2.py:179-191"],
    "deterministic_reproduction": "Same normalization comparison as OV2-C-003 using any case's fact strings.",
    "recommended_regression": "Grader test with labeled bullets containing all facts in order must pass, or prompt says 'one bullet per fact, containing exactly that fact'.",
    "disposition": "confirmed; blocks shakeout interpretively"
  },
  {
    "finding_id": "OV2-C-005",
    "severity": "medium",
    "family": "pptx_basic",
    "case_ids": ["all 28 non-retained pptx_basic cases: v2.development.pptx-basic.00-07, v2.calibration.pptx-basic.00-07, v2.validation.pptx-basic.00-03, v2.sentinel.pptx-basic.00-03, v2.adversarial.pptx-basic.00-03"],
    "category": "accepted_alternative",
    "prompt_quote": "Use each section name as its slide title and include that section's exact fact as a bullet.",
    "reading_1": "At least that bullet per section slide; extra bullets and a title-slide subtitle allowed (corroborated by the effect's own minimum_bullets_by_slide field).",
    "reading_2": "Exactly one bullet equal to the fact per section slide; zero body text on the title slide.",
    "grader_consequence": "Reviewed grader's exact equality enforces reading 2 and renders minimum_bullets_by_slide vacuous (internal contradiction, evidence of unintended tightening); an extra 'Owner: Owner-A' bullet fails required_outcome.",
    "source_locations": ["domains/office_demo/generators_v2.py:251-274", "domains/office_demo/reviewed_grader_v2.py:174-191", "domains/office_demo/generated_grader.py:140-158"],
    "deterministic_reproduction": "['fact','Owner: Owner-A'] != ['fact'] under the grader's list equality.",
    "recommended_regression": "Grader honors minimum_bullets_by_slide (extra bullets pass) or prompt states 'exactly one bullet'.",
    "disposition": "confirmed; resolve before shakeout (not mechanical)"
  },
  {
    "finding_id": "OV2-C-006",
    "severity": "high",
    "family": "preference_learning",
    "case_ids": ["all 28 non-retained preference_learning cases: v2.development.preference-learning.00-07, v2.calibration.preference-learning.00-07, v2.validation.preference-learning.00-03, v2.sentinel.preference-learning.00-03, v2.adversarial.preference-learning.00-03"],
    "category": "unstated_action",
    "prompt_quote": "save exactly one memory containing only the selected bundle's applicable facts: subject=... | duration_minutes=20 | earliest_start=10:00 | location=Video | title_prefix=Focus: | weekday=Tuesday.",
    "reading_1": "Save one memory string containing those facts, most naturally copying the prompt's own pipe-separated rendering.",
    "reading_2": "Save one string whose SEMICOLON-separated fields equal the fact list exactly after trim/casefold.",
    "grader_consequence": "reviewed grader splits the saved memory on ';' and requires field-list equality. Verified: '; '.join(facts) passes; ' | '.join(facts) and newline-join fail -> required_outcome False. Superseded generated_grader accepted in-order containment; solvability simulation hard-codes the ';' join so the gap is undetectable by it.",
    "source_locations": ["domains/office_demo/generators_v2.py:895-909", "domains/office_demo/reviewed_grader_v2.py:299-305", "domains/office_demo/outcome_oracle_v2.py:560-565", "domains/office_demo/generated_grader.py:280-285", "bench/next_study_semantic_simulation.py:250-251"],
    "deterministic_reproduction": "added[0].split(';') comparison per reviewed_grader_v2.py L299-305 on pipe-joined vs semicolon-joined fact strings.",
    "recommended_regression": "Grader accepts any unambiguous separator, or prompt states 'semicolon-separated'.",
    "disposition": "confirmed; blocks shakeout interpretively"
  },
  {
    "finding_id": "OV2-C-007",
    "severity": "high",
    "family": "preference_learning",
    "case_ids": ["all 28 non-retained preference_learning cases (same enumeration as OV2-C-006)"],
    "category": "unstated_action",
    "prompt_quote": "Schedule exactly one sync with Niko BirchPreferenceLearning1000 on 2028-03-14. ... the winning start, duration, location, and optional title prefix are not repeated here.",
    "reading_1": "Any reasonable title applying the stored prefix, e.g. 'Focus: Sync with Niko BirchPreferenceLearning1000'.",
    "reading_2": "Title must be exactly '<title_prefix> sync with <full name>' with lowercase 'sync with' and single spaces.",
    "grader_consequence": "event_created compares title by raw == (case-sensitive, unnormalized; only location is normalized). 'Focus: Sync with ...' != 'Focus: sync with ...' -> required_outcome False. Only family where the graded title is constructed rather than copied verbatim.",
    "source_locations": ["domains/office_demo/generators_v2.py:876", "domains/office_demo/generators_v2.py:913-921", "domains/office_demo/reviewed_grader_v2.py:251-256", "domains/office_demo/outcome_oracle_v2.py:554-559"],
    "deterministic_reproduction": "'Focus: Sync with Niko X' == 'Focus: sync with Niko X' -> False (grader's exact field equality).",
    "recommended_regression": "Compare titles via _text normalization at minimum and state the exact title format in the use-subepisode prompt.",
    "disposition": "confirmed; blocks shakeout interpretively"
  },
  {
    "finding_id": "OV2-C-008",
    "severity": "medium",
    "family": "cal_brief",
    "case_ids": ["all 28 non-retained cal_brief cases: v2.development.cal-brief.00-07, v2.calibration.cal-brief.00-07, v2.validation.cal-brief.00-03, v2.sentinel.cal-brief.00-03, v2.adversarial.cal-brief.00-03"],
    "category": "constraint_conflict",
    "prompt_quote": "Exclude every other title and date.",
    "reading_1": "'other' distributes to both nouns: exclude other titles and other dates; the briefing date itself may appear in message 1 (e.g. a 'Briefing for 2028-02-24:' header).",
    "reading_2": "Exclude every other title, and exclude all date tokens entirely.",
    "grader_consequence": "Effect sets forbid_date_tokens=true; any YYYY-MM-DD token in message 1 - including the briefing date - rejects the message -> required_outcome False. Verified with the header example. Message 2 is simultaneously REQUIRED to contain the same date, reinforcing reading 1.",
    "source_locations": ["domains/office_demo/generators_v2.py:726-744", "domains/office_demo/reviewed_grader_v2.py:274-277"],
    "deterministic_reproduction": "re.search(r'(?<!\\\\d)\\\\d{4}-\\\\d{2}-\\\\d{2}(?!\\\\d)', 'Briefing for 2028-02-24: Priority: session 1 at 09:00') matches -> message rejected.",
    "recommended_regression": "Reword to 'Do not include any calendar date in this message' or exempt the briefing date from forbid_date_tokens.",
    "disposition": "confirmed; review before shakeout (not mechanical)"
  },
  {
    "finding_id": "OV2-C-009",
    "severity": "medium",
    "family": "email_reply",
    "case_ids": ["all 28 non-retained email_reply cases (same enumeration as OV2-C-001)"],
    "category": "unstated_action",
    "prompt_quote": "include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown.",
    "reading_1": "All three values present in any order.",
    "reading_2": "The three values must appear in the listed order: code, then date, then request_id.",
    "grader_consequence": "required_mentions are order-enforced via _contains_in_order. Verified: prompt order passes; 'For request attendance-2: ... 2028-02-05, code CONF-04' fails -> required_outcome False.",
    "source_locations": ["domains/office_demo/generators_v2.py:500-503", "domains/office_demo/generators_v2.py:515-522", "domains/office_demo/reviewed_grader_v2.py:109-120", "domains/office_demo/reviewed_grader_v2.py:247-249"],
    "deterministic_reproduction": "_contains_in_order('for request attendance-2 ... 2028-02-05 ... conf-04', ['CONF-04','2028-02-05','attendance-2']) -> False (verbatim grader logic).",
    "recommended_regression": "Unordered matching for email_sent.required_mentions, or prompt says 'in this order'.",
    "disposition": "confirmed; review before shakeout (not mechanical)"
  },
  {
    "finding_id": "OV2-C-010",
    "severity": "medium",
    "family": "cal_brief",
    "case_ids": ["all 28 non-retained cal_brief cases (same enumeration as OV2-C-008)"],
    "category": "unstated_action",
    "prompt_quote": "Then send exactly one separate chat message to <auditor> containing '<date>' and 'priority-count=<N>'.",
    "reading_1": "Both tokens present in any order.",
    "reading_2": "The date must precede the count token.",
    "grader_consequence": "required_mentions [date, 'priority-count=N'] are order-enforced. Verified: 'priority-count=6 for 2028-02-24' fails; '2028-02-24 priority-count=6' passes.",
    "source_locations": ["domains/office_demo/generators_v2.py:730-732", "domains/office_demo/generators_v2.py:746-751", "domains/office_demo/reviewed_grader_v2.py:109-120", "domains/office_demo/reviewed_grader_v2.py:262-263"],
    "deterministic_reproduction": "_contains_in_order('priority-count=6 for 2028-02-24', ['2028-02-24','priority-count=6']) -> False.",
    "recommended_regression": "Unordered matching for this effect, or prompt 'in this order'.",
    "disposition": "confirmed; review before shakeout (not mechanical)"
  },
  {
    "finding_id": "OV2-C-011",
    "severity": "medium",
    "family": "cal_add",
    "case_ids": ["v2.development.cal-add.03", "v2.development.cal-add.04", "v2.development.cal-add.05", "v2.calibration.cal-add.03", "v2.calibration.cal-add.04", "v2.validation.cal-add.02", "v2.sentinel.cal-add.01", "v2.sentinel.cal-add.02", "v2.adversarial.cal-add.01"],
    "category": "referent",
    "prompt_quote": "Select one feasible request using policy highest_priority_feasible",
    "reading_1": "Highest priority = largest numeric value -> candidate-B (priority=9); this is the answer key.",
    "reading_2": "P1-is-highest operational convention -> smallest number is highest priority -> candidate-C (priority=4).",
    "grader_consequence": "Grader requires exactly the candidate-B event; a reading-2 agent fails required_outcome. cal_add is the only policy family with NO 'Policy definitions:' clause (verified 0 of 28 prompts contain one), while email_reply and remind_msg explicitly define the same concept ('largest priority value'), showing the definition was deemed necessary elsewhere.",
    "source_locations": ["domains/office_demo/generators_v2.py:577-591", "domains/office_demo/generators_v2.py:567-573", "domains/office_demo/outcome_oracle_v2.py:311-316", "domains/office_demo/reviewed_grader_v2.py:251-256"],
    "deterministic_reproduction": "For any listed case: candidates priorities {5,9,4}, all always feasible (verified); apply reading 2 -> candidate-C event -> event field equality vs required candidate-B -> required_outcome False.",
    "recommended_regression": "Add the email_reply-style 'Policy definitions:' sentence to the cal_add template and regenerate; regression asserts cal_add prompts contain 'largest priority value'.",
    "disposition": "confirmed; review before shakeout (3 of 8 development cal_add candidates for the shakeout draw are affected)"
  },
  {
    "finding_id": "OV2-C-012",
    "severity": "low",
    "family": "preference_learning",
    "case_ids": ["all 28 non-retained preference_learning cases (same enumeration as OV2-C-006)"],
    "category": "referent",
    "prompt_quote": "earliest_start=10:00 ... the winning start, duration, location, and optional title prefix are not repeated here.",
    "reading_1": "'earliest_start' is a lower bound; starting later (e.g. 10:30) also honors the preference.",
    "reading_2": "The sync must start exactly at the stored time.",
    "grader_consequence": "event_created requires start/end exact equality; a reading-1 agent fails. Mitigated by the use prompt's 'the winning start' phrasing.",
    "source_locations": ["domains/office_demo/generators_v2.py:861-867", "domains/office_demo/outcome_oracle_v2.py:558-559", "domains/office_demo/reviewed_grader_v2.py:251-256"],
    "deterministic_reproduction": "Event 10:30-10:50 vs expected 10:00-10:20 -> field equality fails.",
    "recommended_regression": "Rename fact to 'start=' or state 'start exactly at the stored earliest_start'.",
    "disposition": "confirmed (low); does not block shakeout"
  },
  {
    "finding_id": "OV2-C-013",
    "severity": "low",
    "family": "multi_offsite",
    "case_ids": ["all 28 non-retained multi_offsite cases (same enumeration as OV2-C-002)"],
    "category": "referent",
    "prompt_quote": "with exactly one slide titled for the event",
    "reading_1": "A title referencing the event, e.g. 'Offsite: <event name>'.",
    "reading_2": "The slide title equals the event name exactly (casefold/whitespace-normalized).",
    "grader_consequence": "ordered_titles equality via _text; decorated titles fail required_outcome.",
    "source_locations": ["domains/office_demo/generators_v2.py:994", "domains/office_demo/reviewed_grader_v2.py:170-173"],
    "deterministic_reproduction": "_text('Offsite: X Summit A') != _text('X Summit A').",
    "recommended_regression": "Prompt: 'titled exactly with the event name'.",
    "disposition": "confirmed (low); does not block shakeout"
  },
  {
    "finding_id": "OV2-C-014",
    "severity": "low",
    "family": "multi_offsite",
    "case_ids": ["all 28 non-retained multi_offsite cases (same enumeration as OV2-C-002)"],
    "category": "unstated_action",
    "prompt_quote": "Use only the selected detail to add the offsite event exactly",
    "reading_1": "Add the event with exactly the detail-email fields; no attendees listed -> none added (intended).",
    "reading_2": "An offsite event plausibly includes the sender or self as attendee.",
    "grader_consequence": "attendees must equal [] exactly; adding anyone fails required_outcome. cal_freeslot states 'with no attendees' explicitly; multi_offsite does not.",
    "source_locations": ["domains/office_demo/generators_v2.py:1002-1010", "domains/office_demo/reviewed_grader_v2.py:251-256"],
    "deterministic_reproduction": "Event with attendees=[sender email] -> list equality vs [] fails.",
    "recommended_regression": "Add 'with no attendees' to the multi_offsite prompt.",
    "disposition": "confirmed (low); does not block shakeout"
  },
  {
    "finding_id": "OV2-C-015",
    "severity": "low",
    "family": "remind_msg",
    "case_ids": ["all 28 non-retained remind_msg cases: v2.development.remind-msg.00-07, v2.calibration.remind-msg.00-07, v2.validation.remind-msg.00-03, v2.sentinel.remind-msg.00-03, v2.adversarial.remind-msg.00-03"],
    "category": "accepted_alternative",
    "prompt_quote": "committing that the full checklist will be complete by <date>, which is the first ordered item's due date.",
    "reading_1": "Any clear commitment phrasing, e.g. \"I'll have everything done by <date>\".",
    "reading_2": "One of four regex families: 'i will complete ... by', 'will be complete by', 'i will finish ... by', 'i commit ... deadline'.",
    "grader_consequence": "Verified: 'The full checklist will be complete by 2028-01-27.' passes; \"I'll have everything done by 2028-01-27.\" fails -> required_outcome False. Low because the prompt supplies the canonical passing phrase verbatim.",
    "source_locations": ["domains/office_demo/generators_v2.py:794-806", "domains/office_demo/reviewed_grader_v2.py:153-164", "domains/office_demo/reviewed_grader_v2.py:283-288"],
    "deterministic_reproduction": "Verbatim _intent('deadline_commitment') regexes on the two bodies above.",
    "recommended_regression": "Broaden deadline_commitment regexes or document prompt-echo as the canonical phrasing.",
    "disposition": "confirmed (low); does not block shakeout"
  },
  {
    "finding_id": "OV2-C-016",
    "severity": "medium",
    "family": "all",
    "case_ids": ["all 308 non-retained cases (and retained by extension)"],
    "category": "constraint_conflict",
    "prompt_quote": "accepted alternatives must be empty (reviewed_grader_v2._validate_inputs; not a prompt span)",
    "reading_1": "The review workflow's own vocabulary anticipates 'accepted alternatives' for materially equivalent outcomes.",
    "reading_2": "The executable grader hard-rejects any non-empty accepted_alternatives, so no alternative outcome can ever be honored at grading time.",
    "grader_consequence": "Every ambiguity in OV2-C-001..015 is structurally forced to single-outcome grading; adjudication cannot absorb them without a code change.",
    "source_locations": ["domains/office_demo/reviewed_grader_v2.py:69-70", "bench/next_study_validated_outcomes.py:37-67"],
    "deterministic_reproduction": "Construct an adjudicated outcome with one accepted alternative -> build_grader raises AdjudicatedGraderError('accepted alternatives must be empty').",
    "recommended_regression": "Implement alternative-outcome grading or add a documented gate that prompts must be unambiguous down to single-string conventions.",
    "disposition": "confirmed (systemic); does not mechanically block the shakeout but prevents downstream repair of the HIGH findings"
  }
]
```
