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

