# Brix Coworking discovery summary

## Publication status

This document is a non-sensitive summary of stakeholder discovery input. The original
correspondence remains outside the public repository because it contains identifiable
client communication. This summary is not an implementation specification, a data-use
authorization, or evidence that any workflow has been selected.

Before implementation, Brix must validate the current workflow, authoritative systems,
roles, data boundary, approval requirements, failure consequences, baseline, and
success threshold.

## Reported opportunity areas

Stakeholders identified the following candidate areas:

- email and task organization;
- lead and member follow-up;
- new-member onboarding;
- conference-room scheduling, confirmations, arrival instructions, and reminders;
- maintenance and facilities issue tracking;
- search over approved internal policies and operational information;
- common-member-question support;
- invoice-status and payment-follow-up tracking without storing payment-card data;
- preparation of member communications.

The stated preference is to begin with one or two functions that work reliably and to
preserve the privacy of member and business information. Those preferences do not
choose the first workflow. Selection requires the P0/S11 discovery and data-governance
evidence defined in [`PROJECT_SETUP.md`](PROJECT_SETUP.md).

## Required discovery outputs

For every candidate workflow, document:

- trigger, actors, inputs, outputs, and authoritative system;
- normal path, exceptions, approvals, reversibility, and failure consequences;
- frequency, current handling effort, delay, error rate, and source of each estimate;
- data fields, owners, access roles, storage, retention, deletion, and logging;
- provider API and safe test-environment availability;
- value, determinism, integration effort, data readiness, and harm;
- measurable shadow and pilot acceptance thresholds.

Until that work is approved, all implementation and evaluation examples must use
synthetic or separately approved redacted data.
