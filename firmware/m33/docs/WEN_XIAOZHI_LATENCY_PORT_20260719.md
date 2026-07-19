# WEN XiaoZhi Latency Port — 2026-07-19

## Source commits

The applicable July 12 work was reviewed from both WEN branches:

- M33: `1451b3511`, `edeaa0406`
- M55: `4b7e14387`, `8b4721afc`, `11d7b4121`, `87206b213`

## Porting decision

The current M33 branch already contains a newer, stricter version of the WEN
IPC contract and observer. Those files were kept in place instead of replacing
them with the older July 12 snapshots. This preserves payload validation,
unavailable-value handling, and received/accepted/invalid/stale/dropped
counters already present in the current project.

The missing reusable QA benchmark was ported and adapted to parse both the
current multi-line `m55qa_xz_latency` output and the older WEN single-line
format. The shared flash layout was also updated using the later safe layout:

| Partition | Offset | Size |
| --- | ---: | ---: |
| `filesystem` | `0x100000` | 512 KiB |
| `wifi_cfg` | `0x180000` | 256 KiB |
| `xiaozhi_cfg` | `0x1C0000` | 256 KiB |

The 256 KiB configuration partitions match the external flash erase-sector
boundary and supersede the WEN branch's earlier 32 KiB partition proposal.

M55-only `applications/voice_service.c` is intentionally not copied into this
M33 project root because its SCons source discovery would compile it as M33
code. The corresponding M55 implementation remains in the M55 firmware branch;
the shared protocol, QA parser, and flash contract are the parts that belong in
this M33 tree.

## Verification

The port is covered by:

- `tools/test_xiaozhi_latency_benchmark.py`
- `tools/test_m55_shared_fal_layout.py`
- the existing M33 XiaoZhi IPC and observer static tests

No rehabilitation motion command is emitted by the benchmark. Live QA should
still be run only when the manipulator is in a safe test state.
