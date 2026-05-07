# 按钮全验收报告（validate-all-buttons.mjs）

运行：2026-05-07T16:01:36.835Z  ·  PROJECT=proj_ai_collab  ·  WEB=http://127.0.0.1:3100

**汇总：12 PASS / 0 FAIL（共 12）**

| # | 按钮/链接 | 结果 | 说明 | 截图前 | 截图后 |
|---|---|---|---|---|---|
| 01 | 登录页（无登录态）有 email + password 输入框 | ✅ PASS | email=2 pwd=2 | ![b](01-login-before.png) | ![a](01-login-after.png) |
| 02 | 项目列表可达（已登录态） | ✅ PASS | URL=http://127.0.0.1:3100/projects | ![b](02-projects-list-before.png) | ![a](02-projects-list-after.png) |
| 03 | /projects/{id}/cockpit 真驾驶舱可达（不死循环） | ✅ PASS |  | ![b](03-cockpit-before.png) | ![a](03-cockpit-after.png) |
| 04 | 工作台 /workbench 可达 + 顶部有 ← 驾驶舱 | ✅ PASS | URL=http://127.0.0.1:3100/projects/proj_ai_collab/workbench backLinks=1 | ![b](04-workbench-before.png) | ![a](04-workbench-after.png) |
| 05 | 工作台 ← 驾驶舱 跳到 /cockpit（不再打回 workbench） | ✅ PASS | URL=http://127.0.0.1:3100/projects/proj_ai_collab/cockpit | ![b](05-back-to-cockpit-before.png) | ![a](05-back-to-cockpit-after.png) |
| 06 | cockpit 打开工作台 → /workbench | ✅ PASS | URL=http://127.0.0.1:3100/projects/proj_ai_collab/workbench | ![b](06-cockpit-to-workbench-before.png) | ![a](06-cockpit-to-workbench-after.png) |
| 07 | + 号开瓷砖（找到 composer textarea） | ✅ PASS | +按钮=2 composer=1 tiles=0 | ![b](07-open-tiles-before.png) | ![a](07-open-tiles-after.png) |
| 08 | 瓷砖打开后出现占用状态 badge | ✅ PASS | badge=1 | ![b](08-occupancy-badge-before.png) | ![a](08-occupancy-badge-after.png) |
| 09 | 收起档案后变 "展开档案" | ✅ PASS | before收起=1 after展开=1 | ![b](09-collapse-profile-before.png) | ![a](09-collapse-profile-after.png) |
| 10 | 派单 textarea + Ctrl+Enter 发送（输入框清空 = 已提交） | ✅ PASS | textarea=1 cleared=true | ![b](10-dispatch-before.png) | ![a](10-dispatch-after.png) |
| 11 | cockpit ← 项目列表 → /projects | ✅ PASS | linkCount=1 URL=http://127.0.0.1:3100/projects | ![b](11-back-to-list-before.png) | ![a](11-back-to-list-after.png) |
| 12 | 退出登录按钮可见且点击后回 /login | ✅ PASS | URL=http://127.0.0.1:3100/login | ![b](12-logout-before.png) | ![a](12-logout-after.png) |