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

Cloud phone preview:

```text
http://106.55.62.122:3001/rehab-arm-mobile/index.html
```

1. Start the static preview from `apps/web/public`:

```text
python -m http.server 4177 --bind 127.0.0.1
```

2. Open `http://127.0.0.1:4177/rehab-arm-mobile/index.html` on desktop or phone browser.
3. Optional backend connection: set `localStorage.rehabArmMobileApiBase` to the API origin that serves `/api/rehab-arm/app/v1`.
4. Keep the safety boundary visible: App sync submits structured training data for M33 review only. It is not motion permission and must not release emergency stop.
5. On Android Chrome, use "Add to Home screen" from the browser menu. The PWA includes standalone display metadata and maskable PNG icons for install preview.

## Android APK Build Environment

This workstation has the Android build prerequisites installed for the rehab-arm mobile wrapper:

```text
JAVA_HOME=D:\Java\jdk-21
ANDROID_HOME=D:\Android\Sdk
ANDROID_SDK_ROOT=D:\Android\Sdk
```

Installed Android SDK packages:

```text
platform-tools 37.0.0
build-tools 35.0.0
platforms;android-35
emulator 36.6.11
```

For a fresh PowerShell session, load the environment with:

```text
.\scripts\use-android-build-env.ps1
```

Then verify:

```text
java -version
javac -version
adb version
sdkmanager.bat --list_installed
```
