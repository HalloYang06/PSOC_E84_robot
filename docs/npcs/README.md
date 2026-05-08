# NPC 岗位手册（per-seat 文档库）

本目录下每个**子目录**对应一个 NPC（seat）的"个人岗位手册"。

工位（电脑节点）→ NPC（seat）→ 线程（CLI session）三层中，NPC 是
长期员工，是减少 AI 换手成本的载体。岗位手册的目的是：**新一轮
Claude/Codex 接手这个 NPC 的对话时，能在 30 秒内把"我是谁、我在做
什么、我有什么坑"读完。**

## 目录约定

```
docs/npcs/<seat-id>/
├── README.md          ← 必须；本 NPC 的岗位说明书（见下面模板）
├── runbook.md         ← 可选；常做任务的步骤记录
├── decisions.md       ← 可选；该 NPC 拍过的设计决定，避免下一轮反悔
└── handoff/<date>.md  ← 可选；上一轮 AI 给下一轮 AI 的接手摘要
```

`<seat-id>` = `seat.id`（数据库 PK，不是 config_id）。可以在
`/projects/<project>/workbench` 瓷砖头部看到。

## README.md 推荐模板

```markdown
# <NPC 名> 岗位手册

## 我是谁
- seat_id: <seat-id>
- 所属工位: <computer_node_id>（人话名称）
- provider/model: <claude / codex / qwen> / <model name>
- 是否工位长: 是 / 否

## 我负责什么
- 主线职责（一两句话）
- 不负责什么（避免接错单）

## 我用什么 skill
- <skill-id-1>：用途
- <skill-id-2>：用途
（继承自工位的 skill 不重复列）

## 我熟悉的代码区
- `apps/web/.../...`：我经常改的目录
- `apps/api/.../...`：我经常改的目录

## 历次拍板与坑
- 2026-XX-XX：<决定 / 教训>
```

## 写作约定（给 NPC 自己）

- **每完成一次有意义的任务**，把"这次踩到的坑 / 拍的决定"追加到本
  NPC 的 `decisions.md` 或 `runbook.md`。
- 引用代码时给 GitHub 链接（owner/repo/blob/branch/path 或
  /commit/<sha>）。用当前仓库真实的 remote，不要编造占位 URL。
- 引用同伴 NPC 时用 seat-id（不是工位名），方便 watcher 路由。
- 三层文档的优先级：项目（全员）→ 工位（同电脑）→ NPC（个人）。
  下层覆盖上层。

## 平台怎么读这个目录

- 启动 NPC 线程时（`scripts/start-thread-watcher.ps1`），平台 adapter
  会在派给 Claude/Codex 的 prompt 里**告诉它去读 docs/npcs/<seat-id>/**。
- 这个 prompt 注入逻辑在 `scripts/platform-workstation-adapter.py`
  的 `_extract_executor_prompt`。
- 读不到也不会报错（NPC 自己跳过该层），但会少一次"上一任记忆"的复用。

## 三层文档的关系

```
项目知识库（docs/projects/<id>/README.md）         ← 全员看
       ↓
工位知识库（docs/workstations/<node_id>.md）       ← 同工位 NPC 看
       ↓
NPC 知识库（docs/npcs/<seat_id>/README.md）        ← 仅本 NPC 看
```
