# AI-2 地图建筑场景交接

## 身份

- 角色：AI-2
- 职责：地图、建筑、房间、场景玩法承载

## 负责范围

- `projects/[id]` 经营农场壳中的主城建筑表达
- 建筑功能分配、入口关系、房间布局与差异化
- 现成素材筛选、本地化适配、截图验证与交接留痕

## 不负责

- 游戏主循环与数值平衡
- 联机逻辑
- 登录页、后端业务、Runner 业务修复
- 其他 AI 已认领模块

## 本轮结论

- 已按最新要求停止把 `/dashboard` 单独扩成第二套基地页。
- 已把“建筑气质、本地素材、主城表达”开始迁回 `projects/[id]` 当前经营农场壳主线。
- 主线项目页现在已经能直接表现调度中枢、养成学院、机房库三种不同建筑身份，并已通过真实浏览器截图验证。
- 本轮继续把三者从“右侧抽屉里有素材”推进到“主线地图层也有正式资产适配痕迹”，不再停在纯身份卡。
- 本轮继续把主线页往“同一张农场地图里的经营世界”收：新增地图内选中提示、世界状态条，并把 HUD 整体往农场风格收紧，继续压低后台页感。

## 本轮实现

- 主线结构迁移：
  - 在 `projects/[id]` 的 `ProjectPlayableShell` 中新增了主城建筑分区轨 `districtRail`。
  - 在右侧抽屉中新增 `identityCard`，用于承载当前建筑区的身份、区位、玩法摘要、房间流程和素材参考。
  - 不再从主线壳把用户引回 `/dashboard`；原“Open dashboard”已改为留在主线流程内。
- 主线地图层适配：
  - 在主线地图覆盖层新增 `mapMarker` 建筑资产牌，把调度中枢、养成学院、机房库等分区的本地素材直接压回地图层。
  - 三个重点建筑现在都同时拥有：
    - 地图层资产牌
    - 分区轨按钮
    - 右侧建筑身份卡
    - 房间流程轨
  - 这样主线页已经开始形成“真正的经营主城”读法，而不是只有 HUD 和表单抽屉。
- 主线游戏世界收口：
  - 新增 `zonePrompt`，把当前选中建筑区的名称、用途、区位直接压在游戏世界里，而不是只在右侧抽屉解释。
  - 新增 `worldStatus`，用游戏化状态条表达“Town running steady / Bottlenecks in town”。
  - 调整 HUD、顶栏、状态条和热点样式，让主线页更贴当前农场游戏的视觉气质，而不是偏黑底后台。
- 建筑身份迁移：
  - `requirements` 区已按“调度中枢”表达：Dispatch / West main road / Request Foyer / Routing Table / Handoff Window。
  - `ai` 区已按“养成学院”表达：Growth / Northeast ridge / Roster Office / Context Clinic / Model Gallery。
  - `computers` 区已按“机房库”表达：Hardware / Southeast hardware yard / Runner Bays / Repair Bench / Log Wall。
- 素材主线化：
  - 已将三类现成素材正式本地化到仓库内，不再依赖在线预览图。
  - 本地资产路径：
    - `/assets/building-scenes/buildings/dispatch-commercial-preview.png`
    - `/assets/building-scenes/buildings/academy-town-preview.png`
    - `/assets/building-scenes/buildings/runner-industrial-preview.png`
- 主线验证能力：
  - 为 `projects/[id]` 增加正式的 `?zone=` 深链参数，方便直接打开指定建筑区做截图和验收。
  - 当前已验证：
    - `?zone=requirements`
    - `?zone=ai`
    - `?zone=computers`

## 可稳定本地化素材

本轮已落地到仓库的现成素材包：

| 用途 | 本地来源目录 | 上游来源 |
|---|---|---|
| 主线调度中枢参考 | `apps/web/public/assets/building-scenes/source/kenney_city-kit-commercial` | https://opengameart.org/content/city-kit-commercial |
| 主线养成学院参考 | `apps/web/public/assets/building-scenes/source/kenney_tiny-town` | https://opengameart.org/content/tiny-town |
| 主线机房库参考 | `apps/web/public/assets/building-scenes/source/kenney_city-kit-industrial` | https://opengameart.org/content/city-kit-industrial |

说明：

- 这轮不是只挂外链参考图，而是已经把素材包下载、解包并落到仓库可控路径中。
- 当前页面使用的是这些素材包里的本地 `Preview/Sample` 图作为正式资产适配第一步。

## 建筑功能分配

| 建筑 | 主线区位 | 主线玩法 |
|---|---|---|
| 调度中枢 | `requirements` / West main road | Request Foyer / Routing Table / Handoff Window |
| 生产工坊 | `tasks` / South work field | Execution Floor / Repair Bay / Outbound Buffer |
| AI 养成学院 | `ai` / Northeast ridge | Roster Office / Context Clinic / Model Gallery |
| 审批塔 | `approvals` / Central crossing | Signoff Lobby / Risk Review Room / Record Vault |
| 机房库 | `computers` / Southeast hardware yard | Runner Bays / Repair Bench / Log Wall |
| 交付码头 | `delivery` / East outer ring | Branch Pier / Test Runway / Release Gate |

## 截图对照

- `artifacts/building-scenes/project-main-overview.png`
  - 对应：`/projects/demo-base`
  - 说明：主线项目页总览，已能同时看到分区轨、地图资产牌、当前建筑提示和世界状态条
- `artifacts/building-scenes/project-dispatch-zone.png`
  - 对应：`/projects/demo-base?zone=requirements`
  - 说明：主线里的调度中枢表达，已接入本地商业城区素材，并且地图层、当前提示、抽屉三层都已联动
- `artifacts/building-scenes/project-ai-zone.png`
  - 对应：`/projects/demo-base?zone=ai`
  - 说明：主线里的养成学院表达，已接入本地 tiny town 素材，并且地图层、当前提示、抽屉三层都已联动
- `artifacts/building-scenes/project-hangar-zone.png`
  - 对应：`/projects/demo-base?zone=computers`
  - 说明：主线里的机房库表达，已接入本地工业素材，并且地图层、当前提示、抽屉三层都已联动

## 修改文件

- `apps/web/app/projects/[id]/page.tsx`
- `apps/web/app/projects/[id]/project-playable-shell.tsx`
- `apps/web/app/projects/[id]/project-playable-shell.module.css`
- `docs/ai-handoffs/building-scenes.md`

## 验证

- 已在 `127.0.0.1:3103` 上验证 `projects/[id]` 主线项目页可正常返回 `200`。
- 已生成并检查主线页面截图，不再以 `/dashboard` 作为本轮继续扩线的承载页。
- 已验证 `requirements / ai / computers` 三个区块在主线页内能通过 `?zone=` 直接打开并显示不同建筑身份。
- 已重新检查主线页地图层截图，确认三个重点建筑区不再只靠右侧抽屉区分，而是已经有地图资产牌支撑建筑气质。
- 已重新检查主线页总览和分区截图，确认当前建筑提示与世界状态条都在同一张农场地图里工作，没有脱离主世界另起炉灶。
- 本轮截图均为真实浏览器截图，不是空白页或报错页。

## 风险

- 当前主线还是叠在现有 Harvest Moon iframe 之上，所以虽然地图层已经有资产牌回迁，但底层农场地图本体仍是旧底图，尚未真正换成立面统一的新主城素材。
- 当前 `?zone=` 深链主要用于主线场景导航与验收截图，后续还可以继续接到更明显的地图镜头或默认焦点上。
- `/dashboard` 旧验证页仍然存在仓库里，但按最新要求不应继续扩线；后续重心应只在主线壳。

## 下一步

- 继续把“调度中枢 / 养成学院 / 机房库”的建筑立面和地图读感进一步迁回 `projects/[id]` 主线，优先从“资产牌”推进到“底图建筑立面”。
- 优先利用已本地化的现成素材做更统一的主线建筑适配，而不是自己绘制。
- 继续以主线页面真实浏览器截图作为验收依据。

## 本轮更新

- 当前阶段：进行中
- 一句话说明：已停止扩 `/dashboard` 支线，并继续把调度中枢、养成学院、机房库三块的正式资产适配压回 `projects/[id]` 主线地图层、当前提示层和抽屉层，且已用真实浏览器截图验证。
- 当前分支：`ai/building-scenes`
- 截图路径：
  - `D:\ai合作产品\artifacts\building-scenes\project-main-overview.png`
  - `D:\ai合作产品\artifacts\building-scenes\project-dispatch-zone.png`
  - `D:\ai合作产品\artifacts\building-scenes\project-ai-zone.png`
  - `D:\ai合作产品\artifacts\building-scenes\project-hangar-zone.png`
