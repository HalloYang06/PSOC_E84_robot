# User Manual

## Stereo RGB + YOLO First Run

1. Capture left/right RGB frames on the edge device.
2. Run pretrained YOLO locally and choose one target object.
3. Estimate a coarse target depth from the stereo pair.
4. POST the result to:

```text
/api/rehab-arm/v1/devices/{device_id}/vision/stereo-context
```

5. Keep `control_boundary` set to `stereo_vision_context_only_not_motion_permission`.
6. Use the returned `vla_vision_context` only as high-level input for the main line.

## Rehab Arm Phone PWA Preview

1. Start the static preview from `apps/web/public`:

```text
python -m http.server 4177 --bind 127.0.0.1
```

2. Open `http://127.0.0.1:4177/rehab-arm-mobile/index.html` on desktop or phone browser.
3. Optional backend connection: set `localStorage.rehabArmMobileApiBase` to the API origin that serves `/api/rehab-arm/app/v1`.
4. Keep the safety boundary visible: App sync submits structured training data for M33 review only. It is not motion permission and must not release emergency stop.
