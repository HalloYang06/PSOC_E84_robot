# User Manual

## NanoPi preferred hotspot

The board keeps a preferred demo-hotspot profile and a lower-priority fallback profile. Credentials remain on the device and must not be copied into Git.

Read-only verification after joining the same hotspot:

```bash
nmcli -t -f NAME,DEVICE connection show --active
nmcli -t -f NAME,AUTOCONNECT,AUTOCONNECT-PRIORITY,TYPE connection show | grep -E '^(cal_network|RedmiK70E)'
ip -br address show wlan0
ip route
```

Expected priority contract:

```text
cal_network: autoconnect yes, priority 100
RedmiK70E profiles: autoconnect yes, priority 10
```

If `cal_network` is not broadcasting, leave the fallback connection active. Do not change the kernel, Wi-Fi driver, CAN, or motor services to address an absent SSID.

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

## Three-motor eye-to-hand data capture

This temporary calibration profile uses only motors `4/5/6` in the exact order
`jian_zongxiang_joint`, `zhou_zongxiang_joint`, and
`jian_xuanzhuan_joint`. Keep motor 3 and both wrist joints fixed throughout the
session. The command captures evidence only and does not move the arm.

On the NanoPi, initialize one session:

```bash
python3 /home/pi/rehab_arm_calibration/eye_to_hand_calibration.py init \
  --output /home/pi/rehab_arm_calibration/session_3motor_20260721.json \
  --session-id eye-to-hand-3motor-20260721 \
  --stereo-calibration-id natural_feature_provisional_20260712T053638Z
```

For each stopped pose, read the authoritative motor 4/5/6 angles in degrees and
capture one raw correspondence:

```bash
python3 /home/pi/rehab_arm_calibration/eye_to_hand_calibration.py capture-raw \
  --session /home/pi/rehab_arm_calibration/session_3motor_20260721.json \
  --context-json /home/pi/rehab_vla_frames/latest_platform_context.json \
  --pose-id P01 --split train \
  --joint-angles-deg 10.0,25.0,-5.0
```

Use at least eight well-spread training poses and three separate validation
poses. Hold each pose still for about one second. The same gripper tip must be
clear in both images and at least 40 pixels from an image edge. A pass prints an
observation containing `camera_xyz_m`, `joint_angles_deg`, and `sample_count`.
A timeout with `hand-eye capture requires independent stereo end-effector
depth` is a rejected pose and must not be bypassed by lowering the geometry
gate or reusing the bottle depth.

`capture-raw` intentionally leaves `robot_xyz_m` unset. First apply the
validated three-motor forward kinematics and visual-zero mapping to produce the
gripper point in `base_link`; only then materialize solver observations and run
`solve`. Do not treat joint angles as Cartesian coordinates.

After collecting the required train and validation poses, activate only an
accepted result with one command:

```bash
/home/pi/rehab_arm_calibration/activate_hand_eye_and_preflight.sh \
  /home/pi/rehab_arm_calibration/session_3motor_20260721.json
```

Exit `0` means the accepted calibration is loaded by the live vision context.
Exit `2` leaves the active calibration unchanged; inspect
`base_from_camera.candidate.json` and its quality reasons. No vision-service
restart is required after successful activation.
