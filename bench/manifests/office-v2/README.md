# Successor office manifests

This directory is the canonical, model-free output of
`office-generators/2.0.0`. Regenerate or verify it from the repository root:

```powershell
python -m bench.generate_next_study --write
python -m bench.generate_next_study --verify
```

The six splits contain 528 cases across 11 families: 88 development, 88
calibration, 44 validation, 44 sentinel, 220 retained, and 44 adversarial.
Each family uses every member of a 4 workload × 4 distractor × 3 constraint
factorial exactly once. The lock binds all manifest bytes, generator/oracle
source digests, split-overlap review, predecessor-reuse review, explicit
difficulty axes, and balance counts.

The corresponding independent-oracle audit and pending human-review ledger are
under `evidence/next-study/`. Neither this directory nor its verification
command authorizes a model call. Live and retained execution remain disabled.
