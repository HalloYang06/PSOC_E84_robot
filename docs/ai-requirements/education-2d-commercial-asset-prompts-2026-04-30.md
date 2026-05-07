# 教育版 2D 商用素材提示词文档 - 2026-04-30

## 1. 使用原则

本文件里的每一段提示词都必须能单独复制使用。不要依赖“统一风格”“通用负面词”“前文已说明”这类上下文。

每一段提示词都要包含：

```text
素材类型、视角、风格、用途、内容细节、商用原创限制、无文字/无商标/无水印、透明背景要求
```

海报、整图和硬件产品渲染不一定需要透明背景；角色、NPC、建筑、道具、UI 图标、tileset 必须尽量要求透明背景或明确可切片。

AI 生图不直接生成中文文字。标题、按钮、职业标签、模型名称等文字应由前端或设计工具后期叠加。

## 2. 商用台账字段

```text
asset_id
asset_name
asset_type
prompt
negative_prompt
generator
generation_date
license_review_status
human_review_status
source_file
final_file
usage_scope
```

## 3. A Agent 海报母版

### A Agent 首页主视觉

```text
Premium commercial product poster key art for "A Agent", visually similar to the provided A Agent poster, a black compact Linux AI hardware box on a dark futuristic desk, small front OLED display, visible USB-C port, LAN port, HDMI port, DEBUG port, subtle RGB neon edge light, top glass panel showing an abstract circuit board and a generic A-shaped mark, two floating holographic interface panels above the box, left panel green for education version, right panel blue for developer version, below the box an isometric voxel RPG world with glowing dotted paths and tiny engineer NPC stations, high-end cinematic lighting, sharp readable composition, dark premium sci-fi mood, original non-branded industrial design, no copied interface, no third-party logos, no readable UI text generated in the image, no watermark, no brand marks, no copyrighted characters, not imitating any existing game, anime, movie, or product poster.
```

### A Agent 黑色硬件盒子

```text
Compact black Linux AI hardware box, visually similar to the hardware box in the provided A Agent poster, premium commercial product render, rounded rectangular metal body, small front OLED status screen, visible USB-C port, LAN port, HDMI port, DEBUG port, subtle RGB neon light strip around the top edge, top glass panel with abstract circuit board details and a generic A-shaped mark, dark futuristic desk surface, high-end cinematic product lighting, clean reflections, original non-branded industrial design, no real logos, no readable text, no watermark, no brand marks, no copyrighted design imitation, not based on any existing consumer electronics product.
```

### 教育版入口卡片

```text
Green holographic UI panel asset for the education version entrance of an AI learning RPG, visually similar to the green education panel in the provided A Agent poster, dark premium sci-fi interface style, small voxel student engineer avatar on the left, clean bullet-list layout shapes without readable text baked into the image, glowing thin green border, embedded electronics learning mood, commercial product UI concept, transparent PNG panel asset, true transparent background, alpha channel, no checkerboard background, no real text, no logo, no watermark, no brand marks, no copied UI, no copyrighted characters, not imitating any existing game interface.
```

### 开发版入口卡片占位

```text
Blue holographic UI panel asset for the developer version entrance of an AI collaboration platform, visually similar to the blue developer panel in the provided A Agent poster, dark premium sci-fi interface style, small abstract model provider icon placeholders without real brand logos, multi-computer multi-agent collaboration mood, glowing thin blue border, clean layout shapes without readable text baked into the image, commercial product UI concept, transparent PNG panel asset, true transparent background, alpha channel, no checkerboard background, no real text, no logo, no watermark, no brand marks, no copied UI, no copyrighted characters, not imitating any existing game interface.
```

### 体素职业 NPC 大地图

```text
Isometric voxel RPG world map for AI collaboration and embedded education, visually similar to the bottom voxel world in the provided A Agent poster, dark forest and circuit-board terrain hybrid, glowing dotted paths connecting small engineer stations, central castle-like generic A hub, tiny voxel NPCs for product manager, frontend engineer, backend engineer, embedded engineer, test engineer, and designer, each NPC standing on a colored platform, premium dark sci-fi game poster style, high clarity, commercial original non-branded assets, no readable text, no logos, no watermark, no brand marks, no copyrighted characters, not imitating any existing voxel game, anime, movie, or board game.
```

## 4. 主角素材

### 教育版体素学生角色

```text
Tiny voxel student engineer character for an isometric educational RPG, visually similar to the tiny voxel characters in the provided A Agent poster, green education-version color accents, small backpack, small circuit-board accessory, friendly brave expression, cute but premium commercial dark sci-fi style, consistent proportions, idle and walk spritesheet, evenly spaced frames, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 主角行走 spritesheet

```text
Young student engineer avatar, three-quarter top-down 2D RPG spritesheet, visually similar to the tiny RPG engineer characters in the provided A Agent poster, premium dark sci-fi educational workshop style with neon accents, short jacket, small tool pouch, friendly confident expression, readable silhouette, consistent proportions, 4 directions, idle and walk animations separated by rows, evenly spaced frames, no motion blur, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 主角工具动作 spritesheet

```text
Young student engineer avatar using small electronics tools, three-quarter top-down 2D RPG spritesheet, visually similar to the tiny RPG engineer characters in the provided A Agent poster, premium commercial dark sci-fi educational workshop style with neon accents, actions include checking a circuit board, holding a jumper cable, tuning a knob, and celebrating project success, consistent character proportions, evenly spaced frames, readable silhouette, no motion blur, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

## 5. NPC 素材

### 总导师 林博士

```text
Friendly embedded systems professor NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, premium dark sci-fi workshop town style with neon platform accents, lab coat with subtle circuit pattern, tablet in hand, wise and warm personality, readable silhouette, idle and talk animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game, anime, movie, or real person.
```

### 手册管理员 墨书

```text
Magical technical librarian NPC for an educational embedded-systems RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, dark premium sci-fi library style with holographic green glow, holding a glowing hardware manual and small circuit diagram cards, calm helpful personality, readable silhouette, idle and page-turn animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no readable text on the book, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 主控工程师 阿芯

```text
Microcontroller engineer NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, premium dark embedded electronics workshop style with neon glow accents, compact work jacket, tiny generic development-board badge without text, soldering goggles lifted on forehead, cheerful precise personality, idle and explain animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 传感器工程师 璃感

```text
Sensor specialist NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, clean premium dark sci-fi workshop style with cyan-green glow accents, carrying a glowing generic IMU module and floating abstract angle graph elements without text, graceful analytical personality, readable silhouette, idle and scan animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 电机工程师 轮匠

```text
Motor engineer NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, sturdy workshop outfit, small wheel and generic motor-driver tools, energetic practical personality, premium dark sci-fi workshop color accents, readable silhouette, idle and wrench animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 控制算法师 派德

```text
PID control mentor NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, elegant engineer robe with three colored tuning dials, floating smooth curve motif without text, calm mathematical personality, premium dark sci-fi workshop style with golden glow accents, readable silhouette, idle and tuning animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 仿真师 桥线

```text
Wiring simulation technician NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, premium dark electronics lab style with holographic green-blue glow, holding colorful jumper wires and a holographic breadboard tablet without readable text, careful safety-first personality, readable silhouette, idle and connect-wire animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 烧录师 火花

```text
Firmware flashing technician NPC for an educational 2D RPG, three-quarter top-down character sprite, visually similar to the tiny engineer NPCs in the provided A Agent poster, safe electronics workstation outfit, USB cable coil, tiny generic status-light device, responsible safety-focused personality, premium dark sci-fi workshop accents, readable silhouette, idle and upload animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game or anime character.
```

### 职业 NPC 体素套装

```text
Set of tiny voxel engineer NPC characters for an isometric RPG map, visually similar to the colored profession NPCs in the provided A Agent poster, product manager with a green planning tablet, frontend engineer with a cyan code panel, backend engineer with a blue server cube, embedded engineer with a golden chip module, test engineer with a red shield checklist icon without text, designer with a purple tool icon, premium dark sci-fi A Agent poster style, original non-branded character designs, consistent proportions, separated sprites, transparent PNG, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing voxel game, anime, or movie.
```

## 6. 精灵伙伴素材

### 传感器精灵

```text
Small sensor spirit companion for an educational embedded-systems RPG, three-quarter top-down 2D sprite, visually similar to the glowing tiny characters and neon accents in the provided A Agent poster, original non-branded mascot design, floating tiny IMU crystal, blue-green glow, cute but premium dark sci-fi workshop style, readable silhouette, idle hover animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game, anime, or mascot.
```

### 控制精灵

```text
Small PID control spirit companion for an educational embedded-systems RPG, three-quarter top-down 2D sprite, visually similar to the glowing tiny characters and neon accents in the provided A Agent poster, original non-branded mascot design, three tiny orbiting dials representing proportional integral derivative without letters, warm yellow and cyan accents, premium dark sci-fi workshop style, readable silhouette, idle hover animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game, anime, or mascot.
```

### 接线精灵

```text
Small wiring helper spirit companion for an educational electronics RPG, three-quarter top-down 2D sprite, visually similar to the glowing tiny characters and neon accents in the provided A Agent poster, original non-branded mascot design, colorful jumper-wire tail, safety badge shape without text, playful but clean premium dark sci-fi workshop style, readable silhouette, idle hover animation frames, consistent proportions, transparent PNG spritesheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copyrighted characters, not imitating any existing game, anime, or mascot.
```

## 7. 建筑素材

### 手册馆

```text
2D RPG building asset for an educational embedded-systems game, three-quarter top-down view, visually similar to the dark voxel-map buildings and glowing stations in the provided A Agent poster, dark premium sci-fi technical library, hardware manuals visible as abstract book shapes without readable text, glowing circuit windows, green holographic education accents, readable entrance, commercial original design, transparent PNG building asset, true transparent background, alpha channel, no checkerboard background, no text signage, no logo, no watermark, no brand marks, no copyrighted architecture, not imitating any existing game building.
```

### 模块工坊

```text
2D RPG building asset for an educational embedded-systems game, three-quarter top-down view, visually similar to the dark voxel-map buildings and glowing stations in the provided A Agent poster, electronics module workshop with small generic circuit boards, clean benches, colorful cables, premium dark sci-fi workshop style with neon poster lighting, readable entrance, commercial original design, transparent PNG building asset, true transparent background, alpha channel, no checkerboard background, no text signage, no logo, no watermark, no brand marks, no copyrighted architecture, not imitating any existing game building.
```

### 仿真接线台

```text
Interactive wiring simulation station prop for an educational electronics RPG, three-quarter top-down 2D game asset, visually similar to the glowing workstations and holographic elements in the provided A Agent poster, large safe training workbench with virtual breadboard, jumper wires, glowing connection nodes, premium dark sci-fi workshop style, commercial original design, transparent PNG prop asset, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no unsafe wiring, no copyrighted design imitation.
```

### PID 调参塔

```text
2D RPG building asset for an educational control-systems game, three-quarter top-down view, visually similar to the dark voxel-map buildings and glowing stations in the provided A Agent poster, elegant tuning tower with three large colored control dials and smooth curve light strips without text, premium dark sci-fi workshop town style, readable entrance, commercial original design, transparent PNG building asset, true transparent background, alpha channel, no checkerboard background, no text signage, no logo, no watermark, no brand marks, no copyrighted architecture, not imitating any existing game building.
```

### 烧录站

```text
Firmware flashing station building asset for an educational embedded-systems RPG, three-quarter top-down view, visually similar to the dark voxel-map buildings and glowing stations in the provided A Agent poster, safe electronics upload bay, USB cable motifs, generic status lights, protective testing area, premium dark sci-fi workshop style, readable entrance, commercial original design, transparent PNG building asset, true transparent background, alpha channel, no checkerboard background, no text signage, no logo, no watermark, no brand marks, no unsafe sparks, no copyrighted architecture, not imitating any existing game building.
```

## 8. 地图 Tileset

### 暗色体素地形 tileset

```text
Isometric voxel tileset for a premium educational sci-fi RPG map, visually similar to the bottom terrain in the provided A Agent poster, dark forest and circuit-board terrain hybrid, mossy blocks, stone paths, glowing dotted route tiles, shallow water tiles, small cliff edges, embedded circuit traces, commercial original non-branded dark neon style, 64x64 or 128x128 grid, seamless tileable, include straight edges, inner corners, outer corners, transition tiles, no text, no logo, no watermark, no brand marks, no copyrighted tile designs, not imitating any existing voxel game.
```

### 工坊镇地面 tileset

```text
2D RPG tileset for an educational embedded-systems workshop town, orthographic top-down view, visually similar to the dark terrain and glowing route language in the provided A Agent poster, clean stone paths, muted grass, lab floor tiles, plaza tiles, embedded circuit inlays, premium dark sci-fi learning mood with neon poster accents, commercial original non-branded style, 64x64 grid, seamless tileable, include straight edges, inner corners, outer corners, transition tiles, no text, no logo, no watermark, no brand marks, no copyrighted tile designs, not imitating any existing game.
```

### 水边与道路边缘 tileset

```text
2D RPG tileset for an educational sci-fi workshop town, orthographic top-down view, visually similar to the dark terrain and glowing route language in the provided A Agent poster, clean stream edges, workshop road edges, dark forest-to-lab transition tiles, subtle glowing circuit traces, commercial original non-branded style, 64x64 grid, seamless tileable, include straight edges, inner corners, outer corners, transition tiles, no text, no logo, no watermark, no brand marks, no copyrighted tile designs, not imitating any existing game.
```

## 9. 硬件道具素材

### 平衡小车套件图标

```text
Small two-wheeled self-balancing robot car kit icon for an educational embedded-systems RPG, three-quarter top-down 2D game prop, visually similar to the premium dark hardware-and-voxel style in the provided A Agent poster, original generic design, visible microcontroller board, IMU module, motor driver, two wheels, safe educational electronics kit style, neon sci-fi accents, high clarity, transparent PNG prop, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no real product design copy, no copyrighted hardware layout imitation.
```

### 主控板道具

```text
Generic microcontroller development board game prop for an educational embedded-systems RPG, three-quarter top-down 2D asset, visually similar to the premium dark hardware-and-voxel style in the provided A Agent poster, original non-branded layout, visible pins and USB port, clean premium electronics style with subtle neon glow, high clarity at small size, transparent PNG prop, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no real board copy, no copyrighted hardware layout imitation.
```

### IMU 模块道具

```text
Generic IMU sensor module game prop for an educational embedded-systems RPG, three-quarter top-down 2D asset, visually similar to the premium dark hardware-and-voxel style in the provided A Agent poster, tiny original circuit board with a simple orientation arrow symbol without text, clean premium electronics style with subtle cyan glow, high clarity at small size, transparent PNG prop, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no real module copy, no copyrighted hardware layout imitation.
```

### 电机驱动模块道具

```text
Generic motor driver module game prop for an educational embedded-systems RPG, three-quarter top-down 2D asset, visually similar to the premium dark hardware-and-voxel style in the provided A Agent poster, original non-branded circuit board, small heat sink, screw terminals, clean premium electronics style with subtle orange glow, high clarity at small size, transparent PNG prop, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no real module copy, no copyrighted hardware layout imitation.
```

### 杜邦线道具组

```text
Set of colorful jumper wire game props for an educational electronics RPG, three-quarter top-down 2D separated objects, visually similar to the premium dark hardware-and-voxel style in the provided A Agent poster, red black yellow blue green wires, clean connector ends, safe electronics learning style, premium dark sci-fi accents, high clarity at small size, transparent PNG prop sheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no unsafe wiring scene, no copyrighted design imitation.
```

## 10. UI 素材

### 任务徽章

```text
Set of 2D educational RPG achievement badges for embedded-systems learning, visually similar to the neon sci-fi UI language in the provided A Agent poster, includes microcontroller badge, sensor badge, motor badge, wiring safety badge, PID control badge, firmware upload badge, premium dark sci-fi icon style, clean readable silhouettes, separated icons, commercial original non-branded design, transparent PNG icon sheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copied icon set, no copyrighted symbols.
```

### 风险提示图标

```text
Set of 2D safety warning icons for an educational electronics game UI, visually similar to the neon sci-fi UI language in the provided A Agent poster, includes power polarity warning, voltage mismatch warning, firmware upload caution, human confirmation warning, premium dark sci-fi interface icon style, clean readable silhouettes, separated icons, commercial original non-branded design, transparent PNG icon sheet, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copied icon set, no copyrighted symbols, no unsafe dramatic sparks.
```

### 奖励宝箱

```text
2D RPG reward chest prop for an educational embedded-systems game, three-quarter top-down view, visually similar to the dark voxel-map rewards and neon accents in the provided A Agent poster, premium dark sci-fi workshop style, subtle circuit pattern without text, warm golden glow, original non-branded design, readable silhouette, transparent PNG prop, true transparent background, alpha channel, no checkerboard background, no text, no logo, no watermark, no brand marks, no copied game chest design, no copyrighted symbols.
```

## 11. 宣传海报

### 教育版宣传海报

```text
Commercial poster key art for an educational 2D RPG about embedded systems and robotics, visually similar to the provided A Agent poster, premium dark sci-fi brand mood, black AI hardware box as the learning terminal, green holographic education panel mood, isometric voxel RPG world below, young student engineer standing with friendly AI mentor NPCs, small two-wheeled self-balancing robot car kit in the foreground, glowing manual library, wiring simulation station, PID tuning tower, original helper spirits, adventurous but safe learning mood, high quality digital illustration, no readable text generated in the image, no logo, no watermark, no brand marks, no copyrighted characters, no existing game style imitation, no anime imitation, no real school name, no unsafe wiring or dangerous sparks.
```

### 平衡小车主线海报

```text
Commercial key art poster for the first main quest of an educational embedded-systems RPG, visually similar to the provided A Agent poster, title concept "self-balancing robot car project" but no readable text in image, student engineer and mentor NPCs gathered around a small two-wheeled balancing robot car kit, black AI hardware box in the background, green holographic education interface glow, isometric voxel workshop town elements, holographic circuit diagram shapes, safe wiring table, PID tuning light curves, premium dark sci-fi workshop mood, original non-branded characters and hardware, cinematic lighting, no logo, no watermark, no brand marks, no copyrighted characters, no copied game style, no anime imitation, no real product design copy, no unsafe wiring scene.
```

## 12. 审核清单

每批素材上线前检查：

```text
是否像某个知名 IP
是否包含文字或商标
透明背景是否真实可用
同一角色比例是否一致
缩小到游戏尺寸后是否可读
是否存在误导性硬件接线
是否适合未成年人教育场景
是否有生成记录和授权记录
```

需要后期叠加的文字：

```text
A Agent
一台盒子，接入你的 AI 协作团队
教育版
AI 游戏化学习
开发版
进入教育版
进入开发版
产品经理 / 前端工程师 / 后端工程师 / 嵌入式工程师 / 测试工程师 / 设计师
```
