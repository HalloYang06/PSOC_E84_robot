# Migration validation

Validation date: 2026-07-13. Host: Windows 11, PowerShell, repository base `6c08902cb12aab4b123ac59e0f839c65bf401d8f`.

These results validate source builds and offline contracts in the stated environment. They do not claim firmware flashing, hardware behavior, Android APK installation, ROS/CAN integration, six-axis closed-loop behavior, or medical safety qualification.

## Tool preflight

| Tool | Executable and version |
| --- | --- |
| SCons | `F:\RT-ThreadStudio\platform\env_released\env-new\.venv\Scripts\scons.exe`; SCons `v4.10.0.b3e979a3e42c43b91f7624895910afb869a19806`; not on `PATH`. A legacy `v3.1.2.bee7caf9defd6e108fc2998a2520ddb36a967691` batch entry also exists under `env\tools\Python27\Scripts`. |
| Arm GCC | `F:\STM32CubeCLT\STM32CubeCLT_1.18.0\GNU-tools-for-STM32\bin\arm-none-eabi-gcc.exe`; GNU Arm `13.3.1 20240614` (a second copy also exists at `F:\gcc\bin`) |
| CMake | `F:\STM32CubeCLT\STM32CubeCLT_1.18.0\CMake\bin\cmake.exe`; `3.28.1`; not on `PATH` |
| Ninja | `F:\STM32CubeCLT\STM32CubeCLT_1.18.0\Ninja\bin\ninja.exe`; `1.11.1`; not on `PATH` |
| Node.js | `C:\Program Files\nodejs\node.exe`; `v24.14.0` |
| npm | `C:\Program Files\nodejs\npm.cmd`; `11.9.0` |
| Python | `C:\Users\ASUS\.espressif\python_env\idf5.4_py3.12_env\Scripts\python.exe`; `3.12.4` |
| Java | missing from `PATH`; no Android Studio JBR found at `C:\Program Files\Android\Android Studio\jbr\bin\java.exe` |
| ADB | missing from `PATH` |
| Docker | `C:\Program Files\Docker\Docker\resources\bin\docker.exe`; CLI `29.5.3`; Desktop Linux daemon not running |
| colcon | missing from `PATH` |
| ROS 2 | `ros2` missing from `PATH`; no ROS/AMENT/COLCON environment variables present |

## Result matrix

| Area | Command | Result | Environment | Evidence |
| --- | --- | --- | --- | --- |
| M33 | `RTT_EXEC_PATH=F:\STM32CubeCLT\STM32CubeCLT_1.18.0\GNU-tools-for-STM32\bin scons -C firmware/m33 -j4` (SCons invoked by the absolute path above) | pass | Windows; SCons 4.10.0; GNU Arm 13.3.1 | Linked `rt-thread.elf`; size `735188` text, `2776` data, `324445` bss. Secure image packaging was skipped because Edge Protect tools or boot config were not found; no flash/hardware test was run. |
| M55 | same tool environment as M33, `scons -C firmware/m55 -j4` | fail | Windows; SCons 4.10.0; GNU Arm 13.3.1 | Link failed on unresolved `ifx_deepcraft_wake_init`, `ifx_deepcraft_wake_detail`, `ifx_deepcraft_wake_stage`, and `ifx_deepcraft_wake_process`. Default Edge Impulse root is absent; fallback declarations become active while the Deepcraft adapter source is not added unless `XIAOZHI_WAKE_BACKEND=deepcraft`. This is an inherited backend/source-graph defect, not a relocated include-path failure. |
| C8T6 | from `firmware/c8t6`: `cmake --preset Debug -DCMAKE_MAKE_PROGRAM=F:/STM32CubeCLT/STM32CubeCLT_1.18.0/Ninja/bin/ninja.exe`; then `cmake --build --preset Debug` (CMake invoked by absolute path) | pass | Windows; CMake 3.28.1; Ninja 1.11.1; GNU Arm 13.3.1 | Configured and linked `SenorsCollect.elf`; RAM 4272 B/20 KB (20.86%), flash 38404 B/64 KB (58.60%). No flash/hardware test was run. |
| ROS 2 | `source /opt/ros/jazzy/setup.bash && colcon build --base-paths ros/rehab_arm_ws/src --symlink-install && colcon test --base-paths ros/rehab_arm_ws/src && colcon test-result --verbose` | not-run | Windows host without ROS Jazzy | `colcon` and `ros2` are missing and no sourced ROS/AMENT environment is present. Requires a Linux ROS 2 Jazzy environment; no hardware/CAN test was attempted. |
| Web | `npm --prefix platform ci`; `npm --prefix platform run build:web` | pass | Node v24.14.0; npm 11.9.0 | Next.js 14.2.35 production build compiled, type-checked, and generated 10 static pages. Existing React hook lint warnings remain. |
| API rehab subset | `python -m pytest platform/api/tests/test_rehab_arm_app_backend.py platform/api/tests/test_rehab_arm_app_live_emg.py platform/api/tests/test_rehab_arm_sync.py platform/api/tests/test_rehab_arm_vla_closed_loop_status.py -q` | pass | Python 3.12.4 | `55 passed, 33 warnings`; warnings are inherited Pydantic/FastAPI deprecations. |
| API full suite | `python -m pytest platform/api/tests -q` | fail | Python 3.12.4; non-gating diagnostic | Collection stops in `test_runner_git_preflight.py`: `ModuleNotFoundError: No module named 'runner.logs'`. The full suite is deliberately excluded from `verify_all.ps1`. |
| Android sync | `npm --prefix apps/mobile ci`; `npm --prefix apps/mobile run sync:web` | pass | Node v24.14.0; npm 11.9.0 | Dependency install and Web asset sync passed. |
| Android APK | prerequisite: `npm --prefix apps/mobile run doctor`; gated command: `npm --prefix apps/mobile run build:debug` | not-run | Java, javac, ADB, and `sdkmanager.bat` missing from `PATH`; no Android SDK environment or `android/local.properties` | `doctor` was attempted and stopped because `java` is not recognized. The prerequisite gate failed, so `build:debug` was not run and no APK claim was made. |
| VLA | `python -m pytest ai/vla/tests -q` | pass | Python 3.12.4; repository root on import path | `14 passed`. These are high-level request/dry-run boundary tests, not a motion authorization test. |
| Repository layout/history | `python -m pytest tools/test -q` | pass | Python 3.12.4; Git full history | `27 passed`, including layout, path, documentation, source-map, second-parent, and ancestry guards. |
| Compose | `docker compose -f platform/deploy/docker-compose.yml config --quiet`; `docker compose -f platform/deploy/docker-compose.public.yml config --quiet` | pass | Docker CLI 29.5.3; daemon stopped | Both files parse without daemon access. The public file warns that deployment environment/secrets variables are unset; no containers were started. |
| Secrets/large files | Task 12 secret scan and repository-size audit | not-run | Pending Task 12 | Generated/runtime tracked-file guards pass, but dedicated secret scanning and large-file inventory remain pending. |

## Source migration exactness

Source migration exactness is separate from build status. `python -m pytest tools/test -q` passed the source-map, integration-second-parent, ancestry, and target-path checks for all six imported components. That result establishes that the recorded source SHAs and histories are reachable and mapped as designed; it does not turn the M55 build failure, unavailable ROS environment, or unavailable Android toolchain into passes.

## Inherited warnings and audit findings

- M33 and M55 emit existing compiler/linker warnings, including `_getentropy` not implemented and RWX load segments; M33 additionally reports unused/redefined/maybe-uninitialized warnings. They did not prevent the M33 link but require firmware-owner review.
- The Web build reports four existing `react-hooks/exhaustive-deps` warnings.
- The API subset passes with 33 Pydantic/FastAPI deprecation warnings.
- `npm audit` for `platform` exits nonzero with 5 findings: 1 moderate and 4 high (`glob`, `next`, and `postcss`). Suggested automatic fixes require breaking upgrades; no `npm audit fix` was run.
- Public compose validation reports unset deployment variables, including database credentials, application secrets, auth configuration, domain, ACME, and SuperTokens mail settings. Syntax validation passes, but deployment readiness is not established.
