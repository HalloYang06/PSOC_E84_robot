# Codex Login Visual Verification - 2026-04-21

## 本轮目标
- 给 `ai合作平台` 项目页补一条真实登录态、成员视角的可视化验证链。
- 重点验证团队页中这些内容在成员态下是否真实可见：
  - `NPC 席位`
  - `最终回复池 / 最终回复中心`
  - `当前负责人 / 当前推荐动作`
- 写入范围尽量只落在 `artifacts`、必要的 `scripts` 和本 handoff。

## 这轮实际做了什么

### 1. 新增无头 Edge 成员态截图脚本
新增文件：
- `D:\ai合作产品\scripts\capture-auth-screenshot.mjs`

能力：
- 直接用本机 Edge 远程调试协议截图，不依赖 Playwright。
- 支持两种模式：
  - 直接注入 `farm_access_token`
  - 真实走 `/login` 表单登录，再跳回目标项目页截图
- 失败时可选落一份页面文本 dump，方便定位是登录问题还是页面问题。

### 2. 项目页改成明确动态页
改动文件：
- `D:\ai合作产品\apps\web\app\projects\[id]\page.tsx`

新增：
- `export const dynamic = "force-dynamic";`
- `export const revalidate = 0;`

目的：
- 避免项目页被 Next 当成公共壳缓存。
- 给登录态 / 成员态 SSR 取数留出正确前提。

## 产出的验证证据

### 真实成员态 PNG
- `D:\ai合作产品\artifacts\platform-loginflow-exchange-screenshot-2026-04-21.png`
- `D:\ai合作产品\artifacts\platform-loginflow-machine-room-screenshot-2026-04-21.png`
- `D:\ai合作产品\artifacts\platform-auth-git-screenshot-2026-04-21.png`

### 辅助文本 / HTML 证据
- `D:\ai合作产品\artifacts\platform-auth-exchange-live-2026-04-21.html`
- `D:\ai合作产品\artifacts\platform-auth-exchange-text-2026-04-21.txt`

## 我自己验证到的结果

### 1. `信息交流` 页成员态截图
截图：
- `platform-loginflow-exchange-screenshot-2026-04-21.png`

图中已确认可见：
- 顶部项目名 `ai合作平台`
- `在线电脑 1`
- `真实线程 12`
- `NPC 席位 4`
- `最终回复中心`
- `当前推荐动作`
- `最终回复池`
- `当前负责人`

也就是说，团队页里你要求的主视图块确实已经进了真实浏览器截图，不只是 HTML 字符串。

### 2. `机房` 页成员态截图
截图：
- `platform-loginflow-machine-room-screenshot-2026-04-21.png`

图中已确认可见：
- `机房`
- `真实线程页`
- `收口结果视图`
- 真实扫描线程条目
- `12 个扫描线程`
- `NPC 席位 4`

这张图证明 `NPC 席位` 和 `真实扫描线程` 在成员态页面里是分开的，而且席位数量已经不是 0。

### 3. `Git 合作` 页成员态截图
截图：
- `platform-auth-git-screenshot-2026-04-21.png`

图中已确认可见：
- `Git 协作中台`
- `AI 链待接`
- `已回执`
- `当前最佳目标`
- `当前推荐动作`

这张图能证明平台里“自维护调度”那层在真实浏览器里能看到，不只在代码里存在。

### 4. 构建与测试
- `npm run build:web` 通过
- `python -m pytest tests -q` 通过，`75 passed`

## 当前遗留风险

### 1. 服务端初始 HTML 的 `authState` 仍有不一致
我用直接带 cookie 的 HTTP 抓取项目页时，页面初始注水数据里仍会出现：
- `authState.isAuthenticated = false`
- `hasProjectAccess = false`

但真实走浏览器登录表单再截图时，团队页主要协作内容是能正常显示的。

这说明现在至少还有一个需要继续收的点：
- SSR 初始状态
- 客户端实际成员态视图

这两层还没有完全对齐。

### 2. `next start` 的长期稳定启动链还不够稳
这轮截图和构建都能跑，但 `3086` 的生产服务启动方式仍然容易因为工作目录或 `.next` 识别问题掉线。  
当前这是验证链里的环境风险，不是功能逻辑本身的问题。

## 建议下一步
1. 继续收 `authState / hasProjectAccess` 的 SSR 初始值，让它和真实成员态截图一致。
2. 保留这条 Edge 登录流截图脚本，后面所有关键面板都用它做真图验证。
3. 在平台主视图继续瘦身时，优先以这三张成员态图为准，不要只看匿名 HTML。
