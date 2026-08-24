# Security policy

## Project status

Brick is an experimental research scaffold. It is not approved for production,
private Brix data, authoritative business systems, or unattended external side
effects.

The latest release is `v0.11.1` (pre-D0 integrity repair), preceded by
`v0.11.0` (S6C), `v0.10.0` (S6G), `v0.9.0` (S5W), `v0.8.0` (S5), `v0.7.0` (B0),
`v0.6.0` (S1R), `v0.5.0` (S4), and `v0.4.0` (F0/Q0). The native-Windows Lenovo
F0, S4, S5W, S6G, and S6C gates passed. The repair still mechanically blocks
retained execution and did not run D0.
Annotated tags and bound evidence are release-authoritative; the tagged S4
release commit intentionally retains candidate prose until immediate docs-only
descendant `D` promotes status. No release is approved for real Brix data.
Pre-1.0 interfaces and controls may change without backward compatibility.

Q0, released in `v0.4.0`, removes the legacy general-filesystem, PowerShell,
broad-root, and skip-confirmation capability paths from supported CLI, web, and
configuration surfaces. Legacy `--root`, `--shell`, `--yolo`, `--with-domain`, and
`--with-office` forms are rejected before output creation, model access, network
access, or mutation.

Q0 also removed Agent Lab's old browser/stdin confirmation channel. S5W adds a
narrow JSONL decision channel bound to a run, confirmation identifier, and
nonce. A missing, malformed, stale, mismatched, timed-out, or denied decision
fails closed. This remains a human decision seam, not production authorization
or an operating-system sandbox.

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
- any browser confirmation prompt by itself;
- an attempt workspace path by itself;
- marker-last evidence publication as an authorization mechanism; or
- a local Ollama endpoint by itself.

`ActionPolicy` classifies actions and can request confirmation; it does not
authenticate the requester, constrain an executor at the operating-system level,
or prove authorization. Domain packs are trusted Python imports. S5W therefore
adds a per-start high-entropy capability and exact Host/Origin controls rather
than treating loopback as authority. The console is still single-user local
development software and must not be remotely exposed.

Marker-last evidence is designed to detect incomplete or corrupted benchmark
records and fail closed after process termination. It does not make model actions
safe and does not claim lossless sudden-power-failure durability.

## Supported safety boundary

Use only synthetic data. Supported surfaces expose domain-scoped simulated
actions and attempt-owned artifacts, not arbitrary host paths or commands.

The one exception is an explicitly enabled real-account connector. Legacy MCP
subprocess connectors keep their own OAuth material. Normalized HubSpot and
Optix connectors store operator-managed credentials through the OS keyring
(Windows Credential Manager on the supported Windows host), never in repository
files, prompts, arguments, transcripts, or logs. Draft mode drops every tool
declared to transmit or invite; a world-changing call is refused unless an
operator confirms it. The checked-in normalized bindings are unbound. Use a
developer or sandbox account until Brix approves production access. See
[`connectors/README.md`](connectors/README.md).

Inference remains local, but a connector request is network exchange with its
provider. HubSpot or Optix receives the fields needed for that operation. A
connected run therefore cannot be described as keeping all business data on the
device.

Real-account runs use empty run-only memory. Normal run transcripts, tasks,
answers, and chat turns are not persisted; the connector operation ledger keeps
only minimal status and hashed object identifiers outside the repository. This
is a retention control, not a claim that the provider does not retain its own
API records or logs.
Any retained legacy overlay source is unreachable unsupported code and must not
be reintroduced through a launcher, API, UI option, configuration, or domain
composition path.

Do not place real Brix member, employee, payment, agreement, email, policy,
access-control, or other private data in the repository, model memory, logs,
benchmark evidence, or Agent Lab.

See [`docs/PROJECT_SETUP.md`](docs/PROJECT_SETUP.md) for the active release gates and
[`docs/FIXES.md`](docs/FIXES.md) for the remaining implementation defects.
