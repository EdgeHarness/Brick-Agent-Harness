# Security policy

## Project status

Brick is an experimental research scaffold. It is not approved for production,
private Brix data, authoritative business systems, or unattended external side
effects.

The latest release is `v0.3.1`. F0/Q0 work toward `v0.4.0` is
**unreleased**, and the native-Windows Lenovo F0 gate is pending. No release is
approved for real Brix data. Pre-1.0 interfaces and controls may change without
backward compatibility.

Unreleased Q0 removes the legacy general-filesystem, PowerShell, broad-root, and
skip-confirmation capability paths from supported CLI, web, and configuration
surfaces. Legacy `--root`, `--shell`, `--yolo`, `--with-domain`, and
`--with-office` forms are rejected before output creation, model access, network
access, or mutation.

Q0 also removes Agent Lab's old browser/stdin confirmation channel. A missing
`ActionPolicy` callback now denies; this fail-closed default is still only an
in-process policy seam, not authentication or authorization. Any future operator
decision channel must be newly bound to a run, confirmation identifier, and
nonce at S5W.

Domain-specific tools may still create `.pptx` and `.xlsx` artifacts inside an
attempt-owned synthetic workspace. That narrow artifact behavior is not a
general filesystem sandbox or authorization boundary.

Only the canonical
[`EdgeHarness/Brick-Agent-Harness`](https://github.com/EdgeHarness/Brick-Agent-Harness)
release history is supported.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
data, or identifiable transcripts. Use GitHub's private **Report a
vulnerability** or Security Advisory flow for this repository when available.
If private reporting is unavailable, contact the EdgeHarness organization
maintainers through an approved private channel and disclose only enough
information to arrange secure transfer.

Include:

- affected commit or version;
- execution mode and operating system;
- required configuration and permissions;
- observed impact;
- a minimal non-sensitive description of the reproduction conditions; and
- suggested containment, if known.

Do not test against Brix systems, third-party accounts, or data you are not
authorized to use.

## Known non-boundaries

The following are not production security controls:

- loopback HTTP binding;
- the Agent Lab child-process boundary;
- domain-pack names or SemVer labels;
- `RunConfig`, `AttemptContext`, `ToolRegistry`, or `ActionPolicy`;
- model prompts, plans, memories, or completion verification;
- any historical or future browser confirmation prompt;
- an attempt workspace path by itself;
- marker-last evidence publication as an authorization mechanism; or
- a local Ollama endpoint by itself.

`ActionPolicy` classifies actions and can request confirmation; it does not
authenticate the requester, constrain an executor at the operating-system level,
or prove authorization. Domain packs are trusted Python imports. Loopback
services remain reachable by other local processes and potentially by
browser-driven requests until the S5W control-plane gate passes.

Marker-last evidence is designed to detect incomplete or corrupted benchmark
records and fail closed after process termination. It does not make model actions
safe and does not claim lossless sudden-power-failure durability.

## Supported safety boundary

Use only synthetic data. Supported surfaces expose domain-scoped simulated
actions and attempt-owned artifacts, not arbitrary host paths or commands.
Any retained legacy overlay source is unreachable unsupported code and must not
be reintroduced through a launcher, API, UI option, configuration, or domain
composition path.

Do not place real Brix member, employee, payment, agreement, email, policy,
access-control, or other private data in the repository, model memory, logs,
benchmark evidence, or Agent Lab.

See [`PROJECT_SETUP.md`](PROJECT_SETUP.md) for the active release gates and
[`FIXES.md`](FIXES.md) for the remaining implementation defects.
