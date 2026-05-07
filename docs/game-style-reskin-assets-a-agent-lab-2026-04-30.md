# A Agent Lab 游戏换肤素材清单与提示词

更新时间：2026-04-30
当前策略：先保留现有农场底座，新增 `A Agent Lab` 可切换试验皮肤。默认入口不替换素材，预览入口为 `/projects/<projectId>?skin=a-agent-lab`，或在项目页点击 `预览试验皮肤`。

## 已备份

备份目录：`D:/ai合作产品/artifacts/backups/game-ui-20260430-090529`

备份范围包含：项目页入口组件、项目页 CSS、Harvest Moon Phaser 游戏 `index.html`、主 JS、`images/`、`levels/`。

## 你需要提供的素材

1. 场景底图：农场主场景、主房内景、开发工坊、电脑机房、NPC 管理区、Skill 管理仓库、串口/调试电视区、Git 回退终端区。
2. 角色精灵：主角 1 套，NPC 角色 6 套以上，包括产品经理、前端工程师、后端工程师、嵌入式工程师、测试工程师、设计师。每套需要待机和四方向行走。
3. 可交互物件：邮箱、日历 DDL、电视串口助手、电脑/Runner 工位、Skill 仓库货架、Git 回退终端、A Agent 盒子、任务公告板。
4. UI 套件：全屏管理器面板、二级列表栏、三级抽屉、对话框、按钮、状态胶囊、加载中标志、禁用态按钮、警告/人工审核提醒。
5. 动效/VFX：选中光圈、在线脉冲、任务提醒闪光、执行中加载环、完成回执亮光、错误/离线提示。
6. 产品硬件图：A Agent 带彩光电视盒子，正面/俯视/三视角均可，后续用于登录页和宣传页。

## 技术规格

- 角色和物件统一使用透明 PNG：`true transparent background, alpha channel, no checkerboard background`。
- 地图建议先用大背景图试装，后续再切 tileset。若做 tileset，建议 `64x64 grid, seamless tileable`。
- 精灵图建议一行一个动作：idle/down/left/right/up，保持等距帧，方便后续切片。
- 所有 UI 图不要直接带中文文字，文字由前端渲染，避免后续改文案困难。
- 先放入 `apps/web/public/assets/game-skins/a-agent-lab/`，不要覆盖 `harvest-moon-phaser3-game` 原素材。

## 动画素材优先原则

不要只生成单张贴图。这个项目后续要接 Phaser/React 游戏界面，最稳的素材格式是：

1. 角色动画：透明 PNG spritesheet，一行一个动作，帧等距，方便切片。
2. 交互物件动画：透明 PNG spritesheet 或 PNG sequence，例如邮箱发光、电脑待机、日历翻页、串口电视波形跳动。
3. UI 动画：优先 Lottie JSON / SVG 动画；如果工具不支持，就生成透明 PNG sequence。
4. 特效动画：透明 PNG spritesheet，例如选中光圈、任务闪光、在线脉冲、加载中、完成回执。
5. 不建议直接给 GIF/MP4 当主素材，除非是登录页背景或宣传页，因为游戏内交互和状态切换更适合 spritesheet。

所有可叠加素材都必须写入：`true transparent background, alpha channel, no checkerboard background`。

## 动画提示词模板

### 1. 主场景底图

```text
orthographic top-down 2D game map background, premium sci-fi farm development campus, A Agent AI collaboration base, warm pixel-farm layout mixed with neon lab hardware, readable walkable paths, clear zones for NPC management, computer access station, skill library, development workshop, mailbox, calendar board and serial debug TV, no text, no logos, no UI overlay, 16:9 composition, high detail but gameplay readable
```

### 2. 主角精灵动画

```text
transparent PNG spritesheet, three-quarter top-down 2D pixel game character, A Agent platform operator, blue jacket and work cap, consistent character proportions, evenly spaced frames, idle/walk down/walk left/walk right/walk up separated by rows, 4 frames per walking row, no motion blur, no text, true transparent background, alpha channel, no checkerboard background
```

### 3. NPC 工程师精灵动画

```text
transparent PNG spritesheet, three-quarter top-down 2D pixel game NPC engineer, role color glowing armor, friendly chibi proportions, consistent with farm RPG character size, idle/walk down/walk left/walk right/walk up separated by rows, 4 frames per walking row, no text, true transparent background, alpha channel, no checkerboard background
```

可替换角色词：`product manager green`, `frontend engineer cyan`, `backend engineer blue`, `embedded engineer gold`, `test engineer red`, `designer purple`。

### 4. 可交互物件动画

```text
transparent PNG spritesheet, animated 2D game prop, three-quarter top-down pixel art, A Agent serial debug TV console with small oscilloscope screen and cable ports, 8 evenly spaced frames, screen waveform flickers from left to right, tiny status light blinking, compact readable silhouette, no text, no logo, true transparent background, alpha channel, no checkerboard background
```

可替换物件词：`mailbox task inbox`, `calendar ddl planner`, `git rollback terminal`, `computer runner workstation`, `skill library shelf`, `A Agent neon hardware box`。

### 5. UI 面板动画套件

```text
animated 2D game UI kit, holographic dark glass panel frame, cyan and gold neon edge, premium AI collaboration console style, include full-screen manager panel opening glow, side rail item hover pulse, drawer panel slide glow, dialogue box typing indicator, primary button active state, disabled button grey state, status chip pulse, loading spinner sequence, no readable text, clean slices, true transparent background, alpha channel, no checkerboard background
```

### 6. VFX

```text
2D game VFX spritesheet, neon cyan green selection ring and online pulse effects, small task notification spark, execution loading loop, completion glow, evenly spaced frames, no text, no logo, true transparent background, alpha channel, no checkerboard background
```

### 7. NPC 对话框动画

```text
animated 2D game dialogue UI spritesheet, holographic dark glass dialogue box for NPC conversation, cyan gold neon rim, typing dots animation, sender and receiver message bubble states, command sent pulse, reply received glow, 8 frames per animation row, no readable text, no logo, true transparent background, alpha channel, no checkerboard background
```

### 8. A Agent 盒子呼吸灯动画

```text
transparent PNG sequence, three-quarter top-down premium AI hardware box named A Agent, black rounded TV box with RGB light strip, tiny front screen showing abstract waveform only no readable text, 12 frames, breathing neon light loop, subtle fan vent glow, product-render quality but game-ready silhouette, true transparent background, alpha channel, no checkerboard background
```

### 9. 登录页背景动画

```text
looping cinematic background animation, premium dark AI collaboration command center, A Agent hardware box on desk, holographic education mode and developer mode panels floating above it, tiny animated chibi agents walking on a miniature map, cyan green gold neon, 6 second seamless loop, no readable text, no logo, 16:9 composition
```

## 第一轮试装顺序

1. 只换 UI 壳层：登录页、项目页、项目管理器面板的风格，不动地图素材。
2. 再换 NPC 栏头像和管理器英雄图。
3. 再换可交互物件：邮箱、日历、电视、工坊、电脑工位。
4. 最后替换地图场景和角色行走精灵，并逐场景截图验收。
