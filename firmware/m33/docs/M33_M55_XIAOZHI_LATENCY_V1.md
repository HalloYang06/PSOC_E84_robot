# M33/M55 XiaoZhi Latency Contract V1

## Purpose

This contract exposes one completed XiaoZhi voice turn from M55 to M33 without
putting XiaoZhi network or audio processing on the M33 control path.

M55 sends one `MSG_TYPE_VOICE_LATENCY` message after a turn finishes. M33 keeps
the latest valid snapshot for QA and status reporting. The message is
observational only: it must not start, stop, or change rehabilitation motion.

## IPC payload

`voice_latency_data_t` is defined in `applications/common/m33_m55_comm.h` and
contains:

- `ipc_seq` and `turn_seq`
- `wake_to_listen_ms`
- `voice_stop_to_cloud_start_ms`
- `cloud_start_to_cloud_done_ms`
- `cloud_done_to_playback_start_ms`
- `voice_stop_to_playback_start_ms`
- `wake_to_playback_start_ms`
- `flags`

Unavailable timings use `VOICE_LATENCY_MS_UNAVAILABLE` (`UINT32_MAX`) and must
be shown as `NA`, never as a large latency value. `flags` tells the receiver
which stages are available and whether the cloud request, playback, timeout,
or fallback path occurred.

M33 validates the flags and payload before accepting a newer snapshot. Its QA
observer also reports received, accepted, invalid, stale, and dropped counts.

## QA commands

Read the current M33 snapshot:

```text
m55qa_xz_latency
```

Collect repeated measurements over a serial shell:

```powershell
python tools\xiaozhi_latency_benchmark.py --port COM16 --mode text --iterations 20
python tools\xiaozhi_latency_benchmark.py --port COM16 --mode probe --iterations 20
python tools\xiaozhi_latency_benchmark.py --port COM16 --mode observe --iterations 20
```

The benchmark writes per-turn CSV data and a JSON summary. Missing stages are
excluded from percentile calculations and retained as empty values in the CSV.

## Acceptance guidance

For the same device, network, and prompt set, compare the new run with a saved
baseline. Recommended initial gates are:

- no failed or invalid samples;
- median stop-to-playback latency at or below 3000 ms;
- p95 stop-to-playback latency at or below 5000 ms;
- at least 30 percent improvement against the baseline when evaluating an
  optimization change.

These are QA gates, not a hard real-time guarantee; cloud and network delay are
outside the MCU's control.
