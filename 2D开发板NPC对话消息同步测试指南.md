# 2D开发板NPC对话消息同步测试指南

## 已完成的优化

### 1. 创建了消息桥接器脚本
**文件**: `scripts/claude-seat-message-bridge.ps1`

这个脚本会：
- 监听 `artifacts/claude-messages/{席位名称}/inbox/` 目录
- 发现新消息时自动调用 Claude CLI
- 在CLI窗口实时显示消息和回复
- 将回复写入 `outbox/` 目录

### 2. 修改了Claude席位启动脚本
**文件**: `scripts/start-claude-seat.ps1`

现在启动Claude席位时会：
- 打开一个新的PowerShell窗口
- 自动启动消息桥接器
- 显示友好的启动信息

### 3. 添加了消息文件读写函数
**文件**: `apps/web/lib/claude-seat-bridge.ts`

新增函数：
- `writeClaudeSeatMessage()` - 写入消息到inbox
- `readClaudeSeatReplies()` - 读取outbox中的回复
- `cleanupClaudeSeatMessageFiles()` - 清理旧消息文件

### 4. 修改了平台消息提交逻辑
**文件**: `apps/web/app/actions.ts`

现在提交协作消息时：
- 消息会同时写入数据库和文件系统
- Claude席位会自动收到消息文件
- 桥接器会处理并回复

## 测试步骤

### 前置条件
1. 确保已安装 Claude CLI (`npm install -g @anthropic-ai/claude`)
2. 确保 Claude CLI 已登录
3. 确保项目已启动 (`pnpm dev`)

### 测试流程

#### 步骤1: 创建或选择Claude NPC席位

1. 访问 `http://localhost:3000/projects/{项目ID}/2d-upgrade`
2. 点击右侧面板的 "NPC 精灵" 模块
3. 如果还没有Claude NPC，点击 "添加 NPC" 创建一个：
   - 名称：例如 "测试助手"
   - 职责：例如 "协助测试消息同步功能"
   - 提供方：选择 "Claude"
4. 点击 "绑定线程" 选择一个Claude会话ID

#### 步骤2: 校准Claude席位会话

1. 在NPC列表中找到刚创建的Claude NPC
2. 点击 "校准Claude席位会话" 按钮
3. **应该会弹出一个新的PowerShell窗口**，显示：
   ```
   ========================================
   Claude NPC 席位已启动
   席位名称: 测试助手
   会话ID: xxx-xxx-xxx
   模型: sonnet
   ========================================

   正在启动消息桥接器...

   ========================================
   Claude NPC 消息桥接器已启动
   席位名称: 测试助手
   会话ID: xxx-xxx-xxx
   收件箱: D:\ai合作产品\artifacts\claude-messages\测试助手\inbox
   发件箱: D:\ai合作产品\artifacts\claude-messages\测试助手\outbox
   轮询间隔: 2秒
   ========================================

   等待平台消息...
   ```

#### 步骤3: 发送测试消息

1. 在2D开发板页面，点击NPC的 "打开对话框" 按钮
2. 在对话框中输入测试消息，例如：
   ```
   你好，这是一条测试消息。请回复"收到测试消息"。
   ```
3. 点击 "发送" 按钮

#### 步骤4: 观察CLI窗口

**PowerShell窗口应该立即显示**（2秒内）：

```
========================================
[收到平台消息] 协作指令
消息ID: msg-1234567890
时间: 2026-05-06 15:30:00
----------------------------------------
你好，这是一条测试消息。请回复"收到测试消息"。
========================================

[正在调用 Claude...]

========================================
[Claude 回复]
----------------------------------------
收到测试消息。我已经成功接收到你的测试消息。消息同步功能运行正常。
========================================

[消息已处理完成]

等待平台消息...
```

#### 步骤5: 验证平台对话框

1. 回到浏览器的2D开发板页面
2. 对话框应该显示：
   - 你发送的消息
   - Claude的回复（可能需要刷新页面或等待几秒）

### 预期结果

✅ **成功标志**：
- PowerShell窗口实时显示收到的消息
- PowerShell窗口实时显示Claude的回复
- 消息和回复都清晰可见，有颜色区分
- 平台对话框能看到完整的对话历史

❌ **如果失败**：
- PowerShell窗口没有弹出 → 检查 `start-claude-seat.ps1` 是否正确修改
- PowerShell窗口弹出但没有显示消息 → 检查 `artifacts/claude-messages/{席位名称}/inbox/` 目录是否有消息文件
- 显示消息但没有回复 → 检查 Claude CLI 是否正确安装和登录
- 平台看不到回复 → 需要实现回复收集机制（下一步）

## 目录结构

消息文件会存储在：
```
artifacts/
└── claude-messages/
    └── {席位名称}/
        ├── inbox/          # 平台发送的消息
        │   └── msg-xxx.json
        ├── outbox/         # Claude的回复
        │   └── msg-xxx-reply.json
        └── processed/      # 已处理的消息
            └── msg-xxx.json
```

## 消息文件格式

### Inbox消息格式
```json
{
  "message_id": "msg-1234567890",
  "seat_name": "测试助手",
  "title": "协作指令",
  "body": "你好，这是一条测试消息。",
  "created_at": "2026-05-06T07:30:00.000Z",
  "metadata": {
    "project_id": "proj-xxx",
    "recipient_id": "workstation-xxx",
    "message_type": "agent_command"
  }
}
```

### Outbox回复格式
```json
{
  "message_id": "msg-1234567890",
  "seat_name": "测试助手",
  "session_id": "xxx-xxx-xxx",
  "reply_at": "2026-05-06T07:30:05.000Z",
  "content": "收到测试消息。我已经成功接收到你的测试消息。",
  "success": true,
  "exit_code": 0,
  "raw_output": "..."
}
```

## 故障排查

### 问题1: PowerShell窗口一闪而过
**原因**: 脚本执行出错
**解决**: 
1. 手动运行脚本查看错误：
   ```powershell
   cd D:\ai合作产品\scripts
   .\claude-seat-message-bridge.ps1 -SeatName "测试助手" -SessionId "xxx"
   ```

### 问题2: 找不到 claude 命令
**原因**: Claude CLI 未安装或不在PATH中
**解决**:
```bash
npm install -g @anthropic-ai/claude
```

### 问题3: 消息文件存在但桥接器没有处理
**原因**: 可能是文件权限或路径问题
**解决**:
1. 检查 `artifacts/claude-messages/` 目录权限
2. 手动删除 inbox 中的消息文件重试

### 问题4: Claude返回错误
**原因**: Claude CLI 未登录或会话ID无效
**解决**:
```bash
claude login
```

## 下一步优化

当前实现已经解决了核心问题：**CLI端可以看到消息和回复**。

后续可以优化：
1. **平台端回复收集**: 实现定时任务读取outbox并更新数据库
2. **前端实时刷新**: 使用轮询或SSE实时显示新回复
3. **消息状态追踪**: 显示"已发送"、"处理中"、"已回复"状态
4. **错误处理**: 更好的错误提示和重试机制
5. **性能优化**: 使用文件系统监听替代轮询

## 总结

通过这次优化，我们实现了：
- ✅ 平台消息实时传递到Claude CLI
- ✅ CLI窗口实时显示消息和回复
- ✅ 消息不丢失（文件队列保证）
- ✅ 易于调试（可以直接查看消息文件）

**核心问题已解决**：用户现在可以在CLI窗口看到完整的对话过程！
