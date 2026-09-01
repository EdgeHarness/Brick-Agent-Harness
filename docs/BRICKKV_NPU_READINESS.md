# BrickKV Snapdragon NPU readiness record

## Result

The managed-cache server path passed a real Windows ARM64 QAIRT smoke run on
2026-09-01 UTC. The run used fixed synthetic text and retained no prompt or
generated text.

The six required decisions were observed in order:

1. `cold / first_request`
2. `reused / exact_extension`
3. `reset / branch`
4. `reset / session_switch`
5. `reset / parent_mismatch`
6. `cold / first_request` after a forced client disconnect

The disconnect request sent 7,470 bytes, closed without reading a response,
and the next request started cold. This is direct evidence that the patched
server discarded the interrupted provisional lineage in this run.

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

## Claim boundary

This result proves that the transactional managed-cache protocol works through
the patched GenieX server and QAIRT NPU path with the public Qwen3 0.6B smoke
model. It does not prove a latency improvement, complete the final benchmark,
or substitute for the planned Llama 3.1 8B study. The evidence itself records
both `performance_claim_authorized: false` and
`final_benchmark_complete: false`.

The remaining final-study blocker is access to the licensed Qualcomm AI Hub
Llama 3.1 8B QAIRT artifact. Once that operator-authorized artifact is exported,
the same provenance checks and the full repeated matrix can run without
changing the cache protocol.
