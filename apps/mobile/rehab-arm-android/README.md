# 灵动康复 ArmControl Android Wrapper

This directory wraps the Stitch-first mobile PWA from `apps/web/public/rehab-arm-mobile` with Capacitor.

Load the Android toolchain in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File ..\..\..\scripts\use-android-build-env.ps1
```

Install dependencies:

```powershell
npm install
```

Sync the latest PWA assets:

```powershell
npm run sync:web
```

Build a debug APK:

```powershell
npm run build:debug
```

Expected debug APK path:

```text
apps/mobile/rehab-arm-android/android/app/build/outputs/apk/debug/app-debug.apk
```

Safety boundary: this Android wrapper is a phone UI shell. It must not add CAN, motor-current, torque, raw setpoint, M33 override, or emergency-stop release paths.
