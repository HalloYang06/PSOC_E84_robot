# User Manual

## Competition-day operation

Use `docs/demo/competition-live-demo-plan-20260721.md` as the authoritative
five-minute script, preflight checklist, downgrade table, and operator handoff.
Do not improvise code, camera placement, model thresholds, joint trajectories,
or kernel changes after the night-before rehearsal freezes the demo baseline.

Quick status and backup packaging:

```powershell
powershell -ExecutionPolicy Bypass -File tools\demo\competition-day-safe-launcher.ps1 -Action status
powershell -ExecutionPolicy Bypass -File tools\demo\competition-day-safe-launcher.ps1 -Action prepare-backup
```

## NanoPi RK3576 vision verification

The canonical source package is `tools/nanopi/vision`. It is safe to inspect or
run in no-upload mode because it does not send CAN or motor commands.

When the NanoPi is online, first verify the existing runtime without changing
the kernel:

```bash
uname -r
systemctl is-active rehab-rknpu-load.service rehab-vla-vision.service
systemctl is-enabled rehab-rknpu-load.service rehab-vla-vision.service
lsmod | grep rknpu
```

Expected historical state: both services are active and enabled, and the RKNPU
module is loaded for the running kernel. A different result means deployment
needs evidence-based recovery; it does not by itself justify a kernel change.

Inspect only non-secret tuning keys from the deployed environment:

```bash
grep -E '^REHAB_(VLA_RKNN|VLA_FPS|TARGET_CONF|END_EFFECTOR_CONF|LEFT_CAMERA|RIGHT_CAMERA)=' \
  /home/pi/rehab_vla/rehab_vla_vision.env
```

Run the RKNN benchmark with a known image and installed model:

```bash
python3 tools/nanopi/vision/nanopi_vla_rknn_benchmark.py \
  --image /home/pi/rehab_vla_frames/latest_left.jpg \
  --model /home/pi/rehab_vla/rknn_models/target.rknn 320
```

For a host-only check from the repository root:

```bash
python -m pytest tools/nanopi/vision/test_nanopi_stereo_natural_feature_calibration.py \
  tools/nanopi/vision/test_nanopi_vla_stereo_dense_fallback.py -q
```

Pass criteria for repository synchronization are successful syntax/tests and
no changes outside the NanoPi vision package and architecture records. Live
deployment additionally requires matching file hashes, active camera streams,
RKNN runtime evidence, fresh platform frames, and no repeated asynchronous
upload errors.
