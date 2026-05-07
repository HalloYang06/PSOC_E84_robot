# 工位知识库使用说明

本目录下每个 `.md` 文件代表一个**工位（computer node）的知识库**。
工位 = 一台电脑节点（一个开发机 / 一台测试机 / NPC 接管的服务器）。

## 文件命名

`docs/workstations/<computer_node_id>.md`

例如：`docs/workstations/dev-laptop-01.md`

## 推荐结构

```markdown
# <工位名> 工位手册

## 本机环境
- OS:
- 工具链:（Node 版本、Python 版本、IDE、SSH key 等）
- 本仓库克隆路径:

## 本工位负责的事
- 主线职责（哪些 NPC 在这里跑）
- 不负责什么（避免误派单）

## 默认 skill 套餐
- skill-A
- skill-B

## 默认 GitHub commit author
- name:
- email:

## 审核策略
- 默认: inherit / force / skip
- 例外:

## 已知坑 / 切换 NPC 时要交代的事
```

## 上层（项目）/ 下层（NPC）的关系

```
项目知识库（docs/projects/<id>.md）            ← 全员都看
       ↓
工位知识库（docs/workstations/<node_id>.md）   ← 在该工位上的所有 NPC 都看
       ↓
NPC 知识库（docs/npcs/<seat_id>.md）           ← 仅本 NPC 看
```

平台从配置 `collaboration_config.workstation_profiles[<node_id>].knowledge_path`
读取本工位的知识库路径，默认就是上面这个。可以在驾驶舱"工位设置"里改。

## skill 继承

- 在 `collaboration_config.workstation_profiles[<node_id>].skill_inheritance` 写一组 skill id
- 该工位下的 NPC 默认继承这些 skill
- NPC 自加的 skill 在 `seat.skill_loadout` 里
- 实际生效 = 工位继承 ∪ NPC 自加（去重）
