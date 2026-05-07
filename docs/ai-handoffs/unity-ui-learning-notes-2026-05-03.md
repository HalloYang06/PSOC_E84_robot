# Unity UI 学习与执行规范 - 2026-05-03

## 结论

当前 `D:/unity_project/My project` 的 2D 升级版客户端先继续用 Unity uGUI，不切 UI Toolkit。

原因：
- 工程已经使用 `com.unity.ugui`，并且已有 `Education2DPlatformBridge`、`Education2DPlatformApiClient`、`Education2DPlatformRouteOpener`。
- uGUI 的 Canvas、RectTransform、Button、Text/Image 更适合当前“游戏 HUD + 二级抽屉 + 三级弹窗 + WebGL 平台跳转”的落地节奏。
- UI Toolkit 后面可用于更复杂的配置页或编辑器工具，但现在强切会让平台链路验证变慢。

## 官方学习来源

- Unity 2022.3 UI 系统概览：Unity 提供 UI Toolkit、uGUI、IMGUI 三套 UI；uGUI 是 GameObject-based runtime UI，适合游戏运行时界面。
  - https://docs.unity3d.com/cn/2022.3/Manual/UIToolkits.html
- Unity uGUI 与 UI Toolkit 迁移对比：uGUI 的 UI 树在 Canvas 下，Canvas Scaler 控制缩放；层级顺序影响渲染顺序。
  - https://docs.unity3d.com/cn/2022.3/Manual/UIE-Transitioning-From-UGUI.html
- Unity Learn UI 入门：Anchor/Pivot 控制 UI 在不同窗口尺寸下的位置和缩放，Canvas Scaler 用 `Scale With Screen Size` 适配分辨率。
  - https://learn.unity.com/tutorial/working-with-ui-in-unity
- Unity UI 优化：复杂 UI 要拆 Canvas；静态元素和动态元素分开；不交互的元素关闭 Raycast Target；非交互 Canvas 不挂 GraphicRaycaster。
  - https://unity.com/how-to/unity-ui-optimization-tips
- RectTransform API：RectTransform 存储 UI 的位置、大小、anchor、pivot。
  - https://docs.unity3d.com/2022.3/Documentation/ScriptReference/RectTransform.html

## 当前项目采用的 UI 架构

Unity 场景：
- `D:/unity_project/My project/Assets/Education2D/Scenes/ReferenceBuilds/Education2D_Ref_InteriorLab.unity`

UI 根节点：
- `AAgentGameUI`

建议拆分：
- `AAgentHUD_StaticCanvas`
  - 左上项目身份
  - 右上项目列表 / 管理器 / 隐藏 UI
  - 右侧一级入口按钮
  - 底部帮助条
- `AAgentHUD_DynamicCanvas`
  - 当前推荐动作
  - 当前负责人
  - 最终回复池
  - 在线状态、加载中、执行中、灰态按钮
- `AAgentHUD_DrawerCanvas`
  - NPC 管理抽屉
  - 电脑接入管理抽屉
  - 协作消息抽屉
  - 开发工坊抽屉
  - Skill 仓库抽屉
  - 日程 DDL 抽屉
  - 串口电视抽屉
  - Git 回退抽屉
- `AAgentHUD_ModalCanvas`
  - 添加 NPC
  - 绑定线程
  - 装配 Skill
  - 创建工位
  - 人工审核确认

## 设计规则

- 一级入口必须放在游戏地图可见区域，不塞进 NPC 管理器内部。
- 二级管理器用右侧/底部抽屉，不全屏挡住地图。
- 三级编辑用较小弹窗或抽屉内弹窗，例如添加 NPC、绑定线程、编辑知识库。
- 面板默认关闭，只显示用户当前要看的层级。
- 可以保留农场时代的布局逻辑：左上身份、右侧一级按钮、底部三张主状态卡、底部提示条。
- 视觉风格换成“小A工作室 / 科技像素实验室”：深色半透明面板、蓝青光边、少量金色强调。
- 游戏角色和 NPC 不放在 UI Canvas 内；它们应是世界里的 SpriteRenderer / Animator 对象。
- UI 按钮点击后必须立刻进入灰态或 loading 态，避免用户以为没反应。

## 技术规则

- Canvas 使用 `ScreenSpaceOverlay` 作为游戏 HUD 默认模式，避免 GameView 比例变化时被 Camera 变形。
- CanvasScaler 使用：
  - `Scale With Screen Size`
  - Reference Resolution: `1920 x 1080`
  - Match Width Or Height: `0.5`
- 所有 UI 元素必须设置清晰 anchor，不用世界坐标硬摆 HUD。
- 静态 Image/Text 默认 `raycastTarget = false`。
- 只有 Button、InputField、ScrollRect 等需要交互的元素保留 Raycast。
- 复杂 UI 不要全部挂在一个 Canvas 上，避免一个动态文本变化导致整棵 UI 重建。
- 后端链路不写进 UI 生成器，继续走：
  - `Education2DPlatformBridge`
  - `Education2DPlatformApiClient`
  - `Education2DPlatformRouteOpener`

## 验收规则

- 不再把 Scene 视图截图当成最终 UI 验收。
- UI 验收必须看 Game 视图、Play Mode 或 WebGL 运行画面。
- 每次视觉改动至少检查：
  - 1280x720 是否不遮挡核心场景。
  - 1920x1080 是否排版合理。
  - 窄窗口是否没有关键按钮被裁掉。
  - 中文是否不乱码、不截断。
  - 一级、二级、三级层级是否清晰。
  - Console 没有 error。

## 下一步

1. 把当前 `AAgentGameUI` 从单 Canvas 改成四层 Canvas。
2. 给每个一级按钮补 `Button` 组件和统一灰态/loading 表现。
3. 新增 `AAgentUnityHudController`，负责打开/关闭抽屉，不再只生成静态 UI。
4. 先做 UI 交互样子，不急着接全部后端，后端桥保持现状。
5. 通过 Game 视图或 WebGL 实际运行截图验收。
