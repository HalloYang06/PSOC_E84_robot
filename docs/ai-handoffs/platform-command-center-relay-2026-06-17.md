# Platform Command Center / Relay Handoff - 2026-06-17

AI identity: Codex GPT-5
Role: External platform / command center / XiaoZhi relay index keeper

This handoff records the verified relationship between the Medical Rehabilitation Manipulator main repository and the separate AI collaboration platform repository. Use it before relying on chat history for platform ownership.

## Verified Repositories

Main rehabilitation manipulator repository:

- Local path: `D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan`
- GitHub remote: `https://github.com/ChillAmnesiac/Medical-Rehabilitation-Manipulator.git`
- Branch checked: `feature/rehab-arm-ros2-architecture`

External AI collaboration platform repository:

- Local path: `D:\ai-collab-product`
- GitHub remote: `https://github.com/wenjunyong666/ai-.git`
- Branch checked: `ai/game-loop-core`

## Relationship And Boundary

The platform repo owns the server-side command center UI, model relay, XiaoZhi-compatible cloud relay, provider configuration, telemetry display, VLA context, and dry-run candidate workflow.

The main rehabilitation manipulator repo owns the ROS2/NanoPi/M33/M55/C8T6 protocol truth, safety boundaries, robot description, and formal motion path documentation.

Safety boundary to preserve:

- Formal real motion remains `JointTrajectory -> NanoPi -> M33 -> motor`.
- M33 remains final safety authority.
- Platform, App, M55, VLA, MuJoCo, and NanoPi must not bypass M33.
- Platform/LLM/VLA output is suggestion/context/dry-run only, not motion permission.
- Forbidden low-level outputs include CAN frames, motor current, motor torque, raw motor position, raw motor velocity, direct motor commands, and M33 safety override.

## Platform Entry Points Checked

In `D:\ai-collab-product`:

- Code: `apps/api/app/modules/rehab_arm/`
- Docs: `docs/medical-rehab-arm-platform-development-plan.md`
- Docs: `docs/rehab-arm-nanopi-vla-mujoco-integration.md`

Current XiaoZhi relay state from platform-side work:

- Cloud endpoint used during prior QA: `ws://106.55.62.122:8011/api/rehab-arm/v1/projects/fd6a55ed-a63c-44b3-b123-96fb3c154966/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha`
- PCM compatibility path has been used for M55 temporary `pcm_s16le` testing.
- Official Opus path should stay the long-term XiaoZhi mainline; PCM is compatibility/debug unless explicitly documented otherwise.
- TTS downlink work belongs in the platform repo, not in this main ROS2/M33 repository.

## Changed In This Main Repo

- `docs/AI_PROJECT_STRUCTURE_GITHUB.md` now includes a stable external platform repository section.
- `docs/PROJECT_PROGRESS.md` records the repository identity and safety-boundary indexing update.
- `docs/TROUBLESHOOTING_AND_LESSONS.md` records the lesson to verify platform repo path/remote/branch before documenting platform state.
- Local checkout facts for adjacent subsystems now live in `docs/ai-handoffs/adjacent-subsystem-checkouts-2026-06-17.md` instead of the stable index.

## Verification

Commands run:

```powershell
git -C D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan status --short --branch
git -C D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan remote -v
git -C D:\RT-ThreadStudio\workspace\_nanopi_rosnode_usbcan branch --show-current
git -C D:\ai-collab-product status --short --branch
git -C D:\ai-collab-product remote -v
git -C D:\ai-collab-product branch --show-current
```

No code behavior changed in this documentation task.

## Known Dirty Files Not Owned By This Task

In the main repo, these were present before this documentation change and were intentionally not staged:

- `launch/system.launch.py`
- `output/`

The platform repo also has many existing modified and untracked files from platform development and QA. They were not staged or changed for this main-repo documentation task.

## Next Steps

1. Continue XiaoZhi ASR/LLM/TTS relay fixes in `D:\ai-collab-product`, not in this main repo.
2. Keep official XiaoZhi Opus as the long-term protocol path; document PCM as compatibility/debug if it remains.
3. When platform API contracts change, update this main repo's protocol docs first or in the same change, without inventing a parallel protocol in the platform.
