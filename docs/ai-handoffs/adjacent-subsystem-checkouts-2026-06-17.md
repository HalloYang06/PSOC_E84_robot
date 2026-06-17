# Adjacent Subsystem Checkouts - 2026-06-17

AI identity: Codex GPT-5
Role: Local checkout mapper for adjacent M55/C8T6/main integration workspaces

This handoff records machine-local checkout facts verified on this Windows bench. These paths are intentionally kept out of the stable project index because local workspace layout can change.

## Verified Local Checkouts

| Subsystem | Local path | GitHub remote | Branch / state | Relationship |
|---|---|---|---|---|
| Main integration/docs | `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan` | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git` | `feature/rehab-arm-ros2-architecture` | ROS2/NanoPi/MuJoCo/docs integration workspace and stable index home. |
| M55 Git-managed firmware | `D:\RT-ThreadStudio\workspace\_m55_ref_repo` | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git` | `M55` | Formal Git checkout for M55 WiFi, LVGL, XiaoZhi/voice, model runtime, and M33/M55 result bridge work. |
| M55 RT-Thread Studio burn workspace | `D:\RT-ThreadStudio\workspace\wifi` | Not a valid Git checkout in this local state | None | Build/burn workspace used for M55 hardware iteration and resource flashing. Sync durable source changes back to the `M55` branch checkout before committing. |
| C8T6 firmware | `D:\RT-ThreadStudio\workspace\c8t6_github_C8T6` | `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git` | `C8T6` | Formal Git checkout for STM32F103C8T6 sensor-node firmware and CAN transport. |

## Boundary

- Stable GitHub branch homes belong in `docs/AI_PROJECT_STRUCTURE_GITHUB.md`.
- Local checkout paths, dirty worktrees, burn workspaces, and machine-specific notes belong in this handoff or a newer handoff.
- Do not treat the `wifi` burn workspace state as a permanent repository fact.

## Verification Commands

```powershell
git -C D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan status --short --branch
git -C D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan remote -v
git -C D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan branch --show-current

git -C D:\RT-ThreadStudio\workspace\_m55_ref_repo status --short --branch
git -C D:\RT-ThreadStudio\workspace\_m55_ref_repo remote -v
git -C D:\RT-ThreadStudio\workspace\_m55_ref_repo branch --show-current

git -C D:\RT-ThreadStudio\workspace\c8t6_github_C8T6 status --short --branch
git -C D:\RT-ThreadStudio\workspace\c8t6_github_C8T6 remote -v
git -C D:\RT-ThreadStudio\workspace\c8t6_github_C8T6 branch --show-current
```

No code behavior changed in this documentation cleanup.
