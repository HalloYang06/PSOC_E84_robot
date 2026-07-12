# 灵动康复 ArmControl Android Wrapper

This directory wraps the Stitch-first mobile PWA from `platform/web/public/rehab-arm-mobile` with Capacitor.

Prerequisites: install Node.js with npm, Android Studio with the Android SDK, and a compatible JDK. Make sure the Android SDK and Java tools are available in the current shell, then work from `apps/mobile`.

Verify the local Android tooling:

```powershell
npm run doctor
```

Install dependencies:

```powershell
npm ci
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
apps/mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

Safety boundary: this Android wrapper is a phone UI shell. It must not add CAN, motor-current, torque, raw setpoint, M33 override, or emergency-stop release paths.
