# 全量页面 UX walk 报告（用户视角）

- 时间：2026-05-08T04:55:58.927Z
- 项目：proj_ai_collab
- 总通过：24
- 总问题：4

## 通过项

- ✓ 登录页有提交按钮
- ✓ / 不报 404 — url=http://127.0.0.1:3000/projects
- ✓ 已登录态访问 /projects 不被踢回 login
- ✓ 项目列表内容已加载 — bodyLen=480
- ✓ /projects/mode-choice 可达
- ✓ GameShell 顶 nav 有「🛠️ 驾驶舱」按钮
- ✓ GameShell 顶 nav 有「🧑‍💼 工作台」按钮
- ✓ GameShell 顶 nav 有「🏢 公司层」按钮
- ✓ GameShell 顶 nav 有「隐藏/显示游戏」按钮
- ✓ 游戏 iframe 存在 — count=1
- ✓ 驾驶舱抽屉拉出
- ✓ 抽屉 iframe 用 ?embed=drawer — src=/projects/proj_ai_collab/cockpit?embed=drawer
- ✓ 工作台抽屉拉出
- ✓ 公司层抽屉拉出
- ✓ 隐藏游戏后显示占位符
- ✓ /cockpit 独立路由可达
- ✓ 驾驶舱独立页有「🎮 游戏」回新游戏壳的按钮（关键 UX 修复）
- ✓ 驾驶舱不再有「旧版页面」入口（用户已抛弃旧农场）
- ✓ /workbench 独立路由可达
- ✓ 工作台独立页有「🎮 游戏」回新游戏壳的按钮（关键 UX 修复）
- ✓ 工作台 topbar 有去驾驶舱的快捷
- ✓ /company 独立路由可达
- ✓ 公司层独立页有「🎮 游戏」回新游戏壳的按钮
- ✓ 旧 /2d-upgrade 仍可访问（保留兼容）

## 问题项


- ✗ 登录页有 email 输入 — count=0
- ✗ 登录页有 password 输入 — count=0
- ✗ CONSOLE-ERROR — Access to fetch at 'https://config.uca.cloud.tuanjie.cn/' from origin 'http://127.0.0.1:3000' has been blocked by CORS policy: Response to preflight request doesn't pass access control check: No 'Acce
- ✗ CONSOLE-ERROR — Failed to load resource: net::ERR_FAILED

## 截图

- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\01-login.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\02-home.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\03-projects-list.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\04-mode-choice.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\05-game-shell.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\06-drawer-cockpit.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\07-drawer-workbench.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\08-drawer-company.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\09-game-hidden.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\10-cockpit-standalone.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\11-workbench-standalone.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\12-company-standalone.png`
- `D:\ai合作产品\artifacts\all-pages-walk-2026-05-08\13-legacy-2d-upgrade.png`