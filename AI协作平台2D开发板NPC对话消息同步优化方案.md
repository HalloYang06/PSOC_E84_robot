# AI协作平台2D开发板NPC对话消息同步优化方案

## 问题诊断

### 当前问题
用户从平台2D开发板发送消息给Claude NPC时，**CLI端完全看不到消息的输入和输出**，但后台确实在运行。

### 根本原因分析

通过代码审查发现了完整的消息流转链路：

1. **平台端发送流程** (`apps/web/app/actions.ts:4685`)
   - 提交消息到 `/api/collaboration/messages`
   - 尝试唤醒Claude会话

2. **Claude会话唤醒** (`apps/web/lib/claude-seat-bridge.ts:358`)
   - 通过PowerShell脚本启动Claude CLI
   - 探测会话是否可用

3. **PowerShell启动脚本** (`scripts/start-claude-seat.ps1:145`)
   - 只是启动Claude CLI，没有传递消息

### 问题所在

**关键缺失环节**：
- ✅ 消息已存储到数据库
- ✅ Claude CLI会话已启动
- ❌ **消息没有传递到Claude CLI**
- ❌ **CLI没有轮询或监听平台消息**
- ❌ **CLI的输出没有回写到平台**

当前架构：
```
平台Web → 数据库 → [断层] → Claude CLI
```

应该是：
```
平台Web → 数据库 → 消息桥接器 → Claude CLI
                              ↓
                         回复收集器 → 平台数据库
```

## 推荐方案：消息文件桥接

### 实现思路
1. 平台发送消息时，同时写入到 `artifacts/claude-messages/{seat-name}/inbox/{message-id}.json`
2. Claude CLI启动时，附加一个监听脚本，轮询inbox目录
3. 发现新消息时，通过 `claude` 命令发送
4. 捕获输出，写入 `outbox/{message-id}-reply.json`
5. 平台轮询outbox，读取回复并更新数据库

### 优点
- 不需要修改Claude CLI本身
- 文件系统作为消息队列，简单可靠
- 易于调试（可以直接查看文件）
- 支持离线消息队列

## 实施步骤

### 第一步：创建消息桥接器脚本
创建 `scripts/claude-seat-message-bridge.ps1`

### 第二步：修改平台消息提交逻辑
在 `apps/web/app/actions.ts` 中添加文件写入

### 第三步：修改Claude会话启动脚本
在 `scripts/start-claude-seat.ps1` 中启动桥接器

### 第四步：添加回复收集机制
在 `apps/web/lib/claude-seat-bridge.ts` 中添加回复读取

### 第五步：前端对话框实时刷新
在对话框组件中添加轮询

## 预期效果

- ✅ CLI窗口实时显示平台发来的消息
- ✅ CLI窗口实时显示Claude的回复
- ✅ 平台对话框同步显示消息和回复
- ✅ 支持连续对话
- ✅ 消息不丢失（文件队列保证）
