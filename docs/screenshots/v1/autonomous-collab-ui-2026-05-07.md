# 自主合作 UI 验收报告（validate-autonomous-collab-ui.mjs）

运行：2026-05-07T18:02:19.146Z  ·  PROJECT=proj_ai_collab  ·  WEB=http://127.0.0.1:3000  ·  API=http://127.0.0.1:8010

**汇总：2 PASS / 5 FAIL（共 7）**

| # | 步骤 | 结果 | 说明 | 截图前 | 截图后 |
|---|---|---|---|---|---|
| 01 | 驾驶舱可达 (baseline，未被踢回 /login) | ❌ FAIL | URL=http://127.0.0.1:3000/login?next=/projects/proj_ai_collab/cockpit | ![b](01-cockpit-baseline-before.png) | ![a](01-cockpit-baseline-after.png) |
| 02 | 触发式派单表单可达 (在 /2d-upgrade，非驾驶舱) | ✅ PASS | triggerHits=true | ![b](02-2d-upgrade-form-before.png) | ![a](02-2d-upgrade-form-after.png) |
| 03 | 工作台开 2 个瓷砖 | ❌ FAIL | +按钮=0 已开瓷砖=0 | ![b](03-workbench-before.png) | ![a](03-workbench-after.png) |
| 04 | 跨工位 → 瓷砖出现 📌 待审区 | ❌ FAIL | auto_msg=4ba6fc97-003f-4977-8bf4-8b196b98e252 reviewBoxes=0 | ![b](04-cross-pending-review-before.png) | ![a](04-cross-pending-review-after.png) |
| 05 | 瓷砖点 [通过] → 待审消失 | ❌ FAIL | approveBtn=0 | ![b](05-cross-approve-before.png) | ![a](05-cross-approve-after.png) |
| 06 | 同工位场景执行 (免审 → 直接 queued) | ✅ PASS | 已造数据，同工位免审 | ![b](06-same-immediate-before.png) | ![a](06-same-immediate-after.png) |
| 07 | 驾驶舱 pending_review 区可见 | ❌ FAIL | cockpit待审命中=false | ![b](07-cockpit-pending-before.png) | ![a](07-cockpit-pending-after.png) |