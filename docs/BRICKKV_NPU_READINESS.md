# BrickKV Snapdragon NPU protocol-v1 record, superseded

## Result and correction

The managed-cache server path completed a real Windows ARM64 QAIRT smoke run on
2026-09-01 UTC. The run used fixed synthetic text and retained no prompt or
generated text. Its six planned decisions passed, but that smoke did not
exercise a token-limited completion. A later 31-request production-path replay
did, and showed that protocol version 1 could reuse incompatible state after a
length stop. This record is therefore **superseded for readiness**.

The six required decisions were observed in order:

1. `cold / first_request`
2. `reused / exact_extension`
3. `reset / branch`
4. `reset / session_switch`
5. `reset / parent_mismatch`
6. `cold / first_request` after a forced client disconnect

The disconnect request sent 7,470 bytes, closed without reading a response,
and the next request started cold. That remains direct evidence for disconnect
rollback in this specific run. It does not repair or outweigh the separately
reproduced truncation failure.

The first controlled reproducer established the protocol-v1 truncation boundary:

- after a `finish_reason: length` turn, the managed extension and reset
  extension produced different output digests and different prompt-token use;
- one EOS-complete exact-marker extension matched, but this narrow case did not
  establish multi-turn equivalence;
- the cause was the QAIRT incremental chat-template path retaining a physical
  turn that was not terminated like the cold full-history template.

GenieX commit `cfd4003227c46e8280cb0913dcd5cd881e10b598` contains protocol
version 2 and its cold-reset optimization. Only EOS-complete generations are
reusable; all other stop reasons reset physical state and expose
`reusable: false`. The following exact extension remains logically traceable
but does not redundantly reset the already-clean handle. Hardware revalidation
of that commit is required before this document can record readiness again.

A later disposable protocol-v2 production-path replay at Brick commit
`92faad3d8939cc4568a25068a026dea8d073c955` exercised all 31 trace records.
Reset mode was deterministic across two runs, but managed mode differed from
reset on 11 of 30 completed records, including nine append-only turns. Source
inspection found a lower runtime defect: QAIRT stopped when it sampled the
terminal EOG token without evaluating that boundary into the retained KV
state. The cold chat template included the assistant boundary; the retained
path did not. This result rejects QAIRT reuse even though the managed lineage
decisions themselves were correct.

The disposable run used a GenieX artifact from a CI run that failed its ARM64
race gate, so it is diagnostic evidence only and is not listed as accepted
evidence below. The runtime fix is isolated in
`qualcomm/geniex-qairt-plugin#50`, with a CPU fixture asserting that EOG remains
absent from visible output but is present in KV history. A separate GenieX
integration branch pins only that backport. A fresh CI artifact and a passing
automated reset-versus-managed comparison are required before advancing.

## Attested inputs

| Item | Recorded value |
| --- | --- |
| Brick source commit | `49ae8bced6b199e454da9747de784194a29b5cd6` |
| Brick source-bundle SHA-256 | `961f66715fb277073224b0042555a62af5cf850ce8f8b1f5b8277c6eea21b9a3` |
| GenieX source commit | `286ef50bc3fa95a3de9ab192a8e0b45f1425c7fa` |
| GenieX CLI SHA-256 | `9d4223e0573818ae894d745162d6f46b668b0258c48b80b963cbe269249a5e03` |
| `geniex.dll` SHA-256 | `78bb21769cdd68654cbe18010aa6753a4f7450b658406cd88286a0a31025572a` |
| QAIRT `geniex_plugin.dll` SHA-256 | `3983f4dfca7a9bed2f8ea62a74631cd95560c10395b56c4fc2ed94a6980a2490` |
| QAIRT `geniex_core.dll` SHA-256 | `1849713033b4d961272929721f7694ebe9c4b4f46647b6456cc51fb410efb818` |
| Model catalogue name | `qualcomm/qwen3_0_6b` |
| Imported model-tree SHA-256 | `c4e43fb51b4097845905ea05725f2d448b9e50ef77b773e7a160c631f15019c3` |
| Imported model tree | 11 files, 760,060,854 bytes |
| Process architecture | ARM64 |
| Runtime version label | `2.45.0.260326`, operator asserted |
| Hardware label | `Snapdragon X Elite X1E-78-100`, operator asserted |

The runner made 12 listener/process identity checks and 17 loaded-runtime
module checks. It required the same PID to own `127.0.0.1:18182`, required the
exact hashed GenieX executable, and required that process to declare the
selected data directory, listener and NPU compute mode. The requested model
name was bound to the hashed `<data-dir>/models/<catalogue-name>` tree.

## Evidence location

The write-once evidence file remains outside Git:

`C:\Models\BrickKV\evidence\managed-smoke-49ae8bc-286ef50-20260901T010741Z.json`

Evidence-file SHA-256:

`d9a7503141f94784d1d20a34178c11170356ad698410987238795b88117865bb`

The server logs contain request status and duration only. They are in:

`C:\Models\BrickKV\evidence\server-20260901T010741Z`

The verified server PID was terminated after evidence validation, and port
18182 was confirmed closed.

The broader protocol-v1 production-path replay that exposed the flaw remains
outside Git at:

`C:\Models\BrickKV\evidence\server-managed-c84013d-286ef50-20260901T013126Z.json`

Its SHA-256 is:

`cf72e99d4997ec78917f5aba8d07b456c6ed09b3f275937dd2a24fb1150d98d3`

The paired reset evidence is:

`C:\Models\BrickKV\evidence\server-reset-c84013d-286ef50-20260901T013126Z.json`

with SHA-256:

`66f2451dd2b7d728c8d5279ca3efc02a189e6c5b5ea674a7f9704c710d7338ea`

## Claim boundary

These protocol-v1 files prove that the selected code and QAIRT path executed
and that the broader replay successfully detected an unsafe case. They do not
prove that protocol version 1 is transaction-safe, prove a latency improvement,
complete the final benchmark, or substitute for the planned Llama 3.1 8B
study. The evidence itself records both
`performance_claim_authorized: false` and `final_benchmark_complete: false`.

The managed-cache GenieX branch now has a fully green CI run, including the
native ARM64 race gate. The remaining gates are a green Windows ARM64 build of
the isolated QAIRT backport, a passing corrected smoke and automated
reset-versus-managed replay on the NPU, and access to the licensed Qualcomm AI
Hub Llama 3.1 8B QAIRT artifact. Only after those gates pass can the repeated
fresh-process matrix begin.
