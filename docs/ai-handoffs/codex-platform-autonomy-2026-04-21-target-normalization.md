# Codex Platform Autonomy Target Normalization

日期：2026-04-21  
当前主项目：`ai合作平台`  
项目 ID：`10f6a858-f3e4-467c-87f5-726caa3cc2be`

## 这轮完成了什么

### 1. 平台自维护需求数据已规范化
- 新增脚本：
  - `D:\ai合作产品\scripts\normalize-platform-autonomy-data.py`
- 已执行一次，更新了 7 条平台自维护需求：
  - `to_agent` 统一成 `ai:<seat_id>`
  - `context_summary`
  - `expected_output`
- 当前数据库中的维护需求已经是正常中文说明，不再混用裸 UUID 和旧乱码文案。

### 2. 前端工位标准化补了 metadata / extra_data 解析
- 文件：
  - `D:\ai合作产品\apps\web\lib\server-data.ts`
- 已补：
  - `metadata`
  - `source_workstation_id`
  - `skill_loadout`
  - `git_boundary`
  - `scene_key`
  - `sprite_key`
  - `x / y`
- 并新增 JSON 字符串解析，避免后端把 `extra_data` 当字符串返回时前端吃不到席位信息。

## 这轮验证

### 构建与测试
- `npm run build:web`：通过
- `python -m pytest tests -q`：通过
- 当前后端测试总数：`75 passed`

### 页面验证
- 已重新启动 `3086`
- 重新抓了真实登录态页面并直接读了页面内文：
  - `D:\ai合作产品\artifacts\exchange-auth-cookie-fixed-2026-04-22-a.png`
- 目前这条验证已经确认：
  - `信息交流` 顶部四张状态卡不再显示 `AI/NPC · 待同步席位`
  - 当前实际显示为：
    - `无人接单 -> Git 维护员 · Git 协作 / ...`
    - `处理中 -> 线程联络员 · 电脑接入 / 线程扫描 / ...`
    - `已完成 -> 主负责 NPC · 主线整合 / ...`
    - `当前负责人 -> 线程联络员 · 电脑接入 / 线程扫描 / ...`
- 也就是说，平台自维护任务目标、真实席位和顶层状态卡这三层现在已经对齐。

## 当前判断

这轮不是空转，底层已经往正确方向收了：
- 需求目标已经进一步统一成 `ai:<agent_id>`
- 维护任务文字已经回到正常中文
- 工位 metadata 解析链已经补齐

当前真实余留已经切到下一层：
- 顶层状态卡已正常
- `最终回复池` 仍然是空的
- 下一轮应该继续把“真实最终回复”补出来，让平台真正只看最终收口结果

## 下一步

1. 继续把真实 `最终回复` 回流到平台  
2. 让 `最终回复池` 真正出现 AI/NPC 最终结果  
3. 继续补截图验证，不只看 HTML  
4. 平台继续沿“只看最终回复 / 当前负责人 / 当前推荐动作，本机 Codex 看全过程”推进

## 2026-04-22 Git 主视图收口补记
- 与子线程并行排查后确认：Git 合作 空白的主因不是数据缺失，而是分舱分支缺失、主要工作流被折叠、首屏权重错误。
- 已恢复 Git 合作 独立分舱，并把首屏顺序收成：当前推荐动作 -> 状态卡 -> 最终回复池 -> 快速派单(折叠) -> 过程细节/配置(更后)。
- 真实登录态截图验证：
  - D:\ai合作产品\artifacts\git-auth-cookie-fixed-2026-04-22-m.png
  - D:\ai合作产品\artifacts\exchange-auth-cookie-fixed-2026-04-22-j.png
- 当前 Git 主视图已经能直接看到：当前推荐动作 / 当前负责人 / 最终回复池 / 快速派单入口。
- 下一步优先：继续把 信息交流 与 Git 合作 的主视图压成同一套语言，只保留 最终回复 / 当前负责人 / 当前推荐动作，进一步降低过程区权重。

## 2026-04-22 信息交流 UTF-8 收口补记
- 重新用 Unicode 转义重写了 `Exchange` 主视图，避免 shell 编码链把中文写成问号。
- 重新验证：
  - `npm run build:web` 通过
  - `python -m pytest tests -q` 通过，`75 passed`
  - 真实登录态截图：`D:\ai合作产品\artifacts\exchange-auth-cookie-fixed-2026-04-22-n2.png`
- 当前 `Exchange` 首屏已经稳定显示：
  - `当前推荐动作`
  - `协作状态`
  - `最终回复池`
- 子线程结论继续成立：下一步最该补的是后端自治推进器，让 requirement 能自动派发到真实线程并稳定产出 `requirement_final_reply`，同时继续把过程区压到折叠区，首屏只保留推荐动作、协作状态、最终回复。

## 2026-04-22 信息交流乱码修复补记
- 发现根因不是页面没更新，而是通过 shell 写中文时被编码链替换成了 `?`。
- 已改成 Unicode 转义重写 `Exchange` 分舱，重新构建、重启并抓真实登录态截图验证。
- 验证结果：
  - `npm run build:web` 通过
  - `python -m pytest tests -q` 通过，`75 passed`
  - 真实登录态截图：`D:\ai合作产品\artifacts\exchange-auth-cookie-fixed-2026-04-22-n2.png`
- 当前 `Exchange` 首屏已稳定显示：
  - `当前推荐动作`
  - `协作状态`
  - `最终回复池`
- 与子线程结论一致：前端首屏收口已到位，下一刀应转向后端自治推进器，让 requirement 能自动派发给真实线程并稳定产生 `requirement_final_reply`。
