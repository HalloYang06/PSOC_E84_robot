# AI 协作平台 Runner 与 Agent 规范

版本：v0.1  
用途：统一 Runner、Agent Adapter、任务执行、安全限制和日志回传规则

---

## 1. Runner 定位

Runner 是部署在电脑、服务器或开发板上的执行节点，负责接收平台任务并在受控环境中执行。

Runner 不是自由 shell，不允许 AI 随意执行高风险命令。

---

## 2. Runner 生命周期

```text
启动
  -> 读取配置
  -> 注册到平台
  -> 上报能力
  -> 发送心跳
  -> 拉取任务
  -> 创建工作区
  -> 执行任务
  -> 回传日志和结果
  -> 清理临时凭证
```

---

## 3. Runner 上报能力

```json
{
  "runner_id": "runner_pc1",
  "host": "PC1",
  "os": "windows",
  "capabilities": [
    "git",
    "node",
    "python",
    "docker",
    "ros",
    "embedded-build"
  ],
  "hardware_access": false,
  "status": "online"
}
```

---

## 4. 任务执行规则

1. 每个任务独立工作区。
2. 默认从任务分支拉取代码。
3. 只注入任务需要的临时凭证。
4. 命令执行必须记录日志。
5. 超时必须停止任务。
6. 失败必须回传错误摘要。
7. 任务结束必须清理临时文件和凭证。

---

## 5. Agent Adapter 输入输出

输入：

```json
{
  "task_id": "TASK-001",
  "goal": "修复任务 API 状态流转",
  "workspace": "/workspace/TASK-001",
  "branch": "ai/be-task/TASK-001-status",
  "context": {
    "summary": "",
    "related_files": [],
    "requirements": [],
    "constraints": []
  },
  "permissions": {
    "can_write": true,
    "can_run_tests": true,
    "can_access_hardware": false
  }
}
```

输出：

```json
{
  "status": "success",
  "summary": "",
  "changed_files": [],
  "test_commands": [],
  "test_results": [],
  "risk_notes": [],
  "handoff_needed": false
}
```

---

## 6. 安全限制

禁止默认执行：

```text
删除仓库历史
强制推送 main
输出明文 token
修改系统级配置
格式化磁盘
关闭安全服务
访问真实硬件
烧录固件
控制电机或机械臂
```

所有硬件操作必须返回：

```text
HUMAN_APPROVAL_REQUIRED
```

---

## 7. 日志规范

Runner 日志分三层：

```text
完整日志:
  保存到对象存储。

摘要日志:
  显示给前端和 AI。

错误摘要:
  用于快速定位失败。
```

日志禁止包含：

```text
token
password
private key
ssh key
cookie
authorization header
```

