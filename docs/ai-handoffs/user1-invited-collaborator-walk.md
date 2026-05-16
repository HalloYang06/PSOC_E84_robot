# User1 Invited Collaborator Walk Handoff

AI identity: Codex GPT-5  
Role: User1 invited collaborator UX acceptance tester  
Date: 2026-05-16  
Workspace root: `D:\ai合作产品`

## Current Task

User asked Codex to act as 用户1, accept an invitation into `医疗康复机械臂`, fully experience the platform as a human user, then write a document with the issues found.

## Account Used

- URL: `http://106.55.62.122:3001/login`
- Email: `codex-userwalk-1778929071918@example.com`
- Password: `Test1234`
- Role in invited project: collaborator
- Invited project: `医疗康复机械臂`
- Project ID: `72a1cb1d-d8a8-422f-8d87-4ed071f71dbe`

## Created Documentation

- Main acceptance report: `docs/acceptance/user1-invited-collaborator-walk-2026-05-16.md`
- This handoff: `docs/ai-handoffs/user1-invited-collaborator-walk.md`

## Evidence Artifacts

- `artifacts/user1-invited-walk/`
- `artifacts/user1-medical-deep/`
- `artifacts/user1-comprehensive-2/`
- Key log: `artifacts/user1-comprehensive-2/comprehensive-log.json`

## What Was Covered

- Login as 用户1.
- Project list tabs: 项目, 邀请, 收到, 新建.
- Invitation acceptance for `医疗康复机械臂`.
- Project home page as collaborator.
- NPC workbench, including opening NPC tiles.
- Company layer.
- Data factory.
- AI lab.
- Observability.
- Right-side panels: development workshop, protagonists, NPC management, computers, skills, schedule, serial device debug, AI debug, simulation, exchange, thread debug, Git rollback.
- Secondary and tertiary drawers where safe.

## Important Safety Boundary

No real hardware, deployment, ROS write, motor action, model publish, final acceptance, destructive Git action, approval/rejection, delete, or unbind action was intentionally executed.

One non-hardware project-structure action was executed during earlier comprehensive exploration: `一键创建平台推荐工位`, which created four logical workstations in the invited project. This is documented in the report.

## Main Findings

P0:

- Collaborator project home is too dense and exposes too much operational detail.
- Copy action fails under HTTP/no clipboard environment.
- Thread/Runner/NPC states conflict from a human perspective.
- Direct routes `/robot-site` and `/skills` return 404.

P1:

- Project card navigation looks like a button but is semantically a link.
- Computer onboarding is useful but too English/diagnostic-heavy.
- Collaboration message pool needs a stronger "things I must handle" area.
- Git rollback and hardware debug need clearer action classes.
- Company layer empty state does not explain the missing station leads clearly enough.

P2:

- Next RSC payload fetch failures fall back to browser navigation.
- Development-stage copy appears in the live experience.
- Naming is inconsistent across Skill, capability workshop, robot site, robotics, etc.

## Next Pickup

If continuing implementation, start with:

1. Fix clipboard fallback for all copy buttons.
2. Add redirects or canonical routes for `robot-site` and `skills`.
3. Create a simplified collaborator landing summary on the project home page.
4. Normalize Runner/thread/NPC status into one human-readable availability conclusion.
5. Add action labels: `只读`, `登记`, `派单`, `需人审`, `危险`.

Do not rely on chat history; use the acceptance report as the source of truth.
