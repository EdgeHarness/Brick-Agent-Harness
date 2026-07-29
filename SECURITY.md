# Security policy

## Project status

Brick is an experimental research scaffold. It is not approved for production,
private Brix data, authoritative business systems, or unattended external side
effects.

Only the latest commit on `main` is maintained. Pre-1.0 interfaces and controls may
change without backward compatibility.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private data, or
identifiable transcripts. Use GitHub's private **Report a vulnerability** or Security
Advisory flow for this repository when available. If private reporting is unavailable,
contact the EdgeHarness organization maintainers through an approved private channel
and disclose only enough information to arrange secure transfer.

Include:

- affected commit or version;
- execution mode and operating system;
- required configuration and permissions;
- observed impact;
- a minimal non-sensitive description of the reproduction conditions;
- suggested containment, if known.

Do not test against Brix systems, third-party accounts, or data you are not authorized
to use.

## Known non-boundaries

The following are not production security controls:

- loopback HTTP binding;
- model prompts, plans, memories, or completion verification;
- browser confirmation buttons;
- the current real-filesystem path checks;
- a local Ollama endpoint by itself;
- the `--yolo` or `--shell` execution modes.

Use real-filesystem and shell modes only against disposable test directories with
independent backups. See [`FIXES.md`](FIXES.md) and
[`PROJECT_SETUP.md`](PROJECT_SETUP.md) for the blocking remediation and release gates.
