# 局域网多电脑接入指南（3 分钟）

> 让平台调用**另一台电脑**上的 Claude/Codex 线程一起做项目。

---

## A 主机（运行平台的电脑）

### 1. 找到本机局域网 IP
```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
  $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" -or $_.IPAddress -like "172.16.*"
} | Select-Object IPAddress, InterfaceAlias
```
找到你常用的网卡（WLAN / 以太网）对应的 IP，例如 `192.168.2.44`。

### 2. 启动平台到 LAN 模式（一键脚本）
```powershell
cd D:\ai合作产品
powershell -ExecutionPolicy Bypass -File scripts\start_local_server_mode.ps1 -LanIp 192.168.2.44
```

或手动启动：
```powershell
# 后端
cd D:\ai合作产品\apps\api
$env:CORS_ALLOWED_ORIGINS="http://localhost:3000,http://192.168.2.44:3000"
$env:PYTHONUTF8="1"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 前端（新终端）
cd D:\ai合作产品
$env:NEXT_PUBLIC_API_BASE_URL="http://192.168.2.44:8000"
$env:INTERNAL_API_BASE_URL="http://192.168.2.44:8000"
npm run dev:web
```

### 3. 开防火墙入站规则（管理员 PowerShell）
```powershell
New-NetFirewallRule -DisplayName "AI Collab API 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -RemoteAddress LocalSubnet
New-NetFirewallRule -DisplayName "AI Collab Web 3000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000 -RemoteAddress LocalSubnet
```

### 4. 验证
- 浏览器访问 `http://192.168.2.44:3000` 能登录
- 命令行 `Invoke-WebRequest http://192.168.2.44:8000/api/health` 返回 200

### 5. 在 UI 上生成"配对令牌 + 接入命令"
1. 登录 → 进入项目 `/projects/{id}/2d-upgrade`
2. 右侧 dock 点"电脑接入"
3. 创建一个新电脑节点（例如 "PC-B-Linux"），点"生成配对令牌"
4. 复制弹出的"一行 PowerShell 命令"——这条命令带上了 Server 地址 + Token + 节点 ID

---

## B 主机（另一台要接入的电脑）

### 1. 装好 Claude / Codex CLI
```powershell
# Claude
npm install -g @anthropic-ai/claude-cli
claude --version

# Codex（如果用）
npm install -g @openai/codex
codex --version
```

### 2. 把 A 主机生成的"一行命令"粘到这台电脑的 PowerShell 执行
```powershell
# 形如：
powershell -NoProfile -ExecutionPolicy Bypass -Command "& {
  New-Item -ItemType Directory -Force -Path .\ai-collab-runner | Out-Null
  Invoke-WebRequest -Uri 'http://192.168.2.44:3000/downloads/runner/connect-ai-collab-runner.ps1' -OutFile '.\ai-collab-runner\connect-ai-collab-runner.ps1'
  & '.\ai-collab-runner\connect-ai-collab-runner.ps1' -Server 'http://192.168.2.44:8000' -PairingToken '<token>' -ComputerNodeId 'PC-B-Linux' -RunnerName 'PC-B Runner' -RunnerId 'runner-pc-b' -ProjectId 'proj_xxx' -Watch
}"
```

`-Watch` 参数让 runner 持续轮询任务，启动后保持窗口开着。

### 3. 验证（B 主机）
```powershell
# 看 runner 进程在跑：
Get-Process | Where-Object { $_.MainWindowTitle -match "ai-collab" }

# 看本机 Claude 能跑：
echo "回复一个字" | claude --print --permission-mode bypassPermissions
```

---

## A 主机派任务给 B 主机的 NPC

1. 进入项目 `/projects/{id}/2d-upgrade`
2. 右侧 dock 点 "NPC 管理"
3. 选一个 NPC，把它的 `computer_node_id` 改为 PC-B 的节点 ID
4. 派任务（点"打开 NPC 对话框"，发送指令）
5. **B 主机的 runner 收到任务** → 启动本机 Claude → 跑出结果 → 回写到平台
6. **A 主机 UI 看到回执**

---

## 常见问题

### B 主机连不上
- 防火墙：在 A 主机管理员 PS 里跑前面"开防火墙"那条
- IP 错：A 主机的 LAN IP 用 `Get-NetIPAddress` 重新确认（VMware 虚拟网卡 IP 是访问不到的）
- 跨网段：两台电脑必须在同一个子网（都是 192.168.2.x）

### B 主机 Claude 没反应
- `claude --version` 先确认装了
- 本机直接 `echo "test" | claude --print --permission-mode bypassPermissions` 先跑通
- 查 `D:\ai合作产品\artifacts\claude-thread-log\*.log`（在 A 主机上查 B 主机回写的日志）

### 看 Claude 真实做了什么
- A 主机 UI 派任务时，给 message 加 `--tee-log` 参数（已支持）
- 日志在 A 主机 `D:\ai合作产品\artifacts\claude-thread-log\<message-id>.log`
- 内容含 PROMPT / RAW OUTPUT / FINAL REPLY 三段

---

## 多电脑协作的真实场景示例

- **PC-A**（你的主机）：跑平台 + 开发工坊知识库 + 一个本地 Claude NPC
- **PC-B**（家里另一台）：跑 runner，挂 Codex NPC（专门做嵌入式驱动）
- **PC-C**（实验室那台）：跑 runner + 接硬件，挂 Claude NPC（专门做硬件烧录前的代码审查）

派任务："给 NanoPi 加 SPI 驱动"
- 平台分析 → 派给 PC-B 的 Codex NPC（驱动专家）写代码
- PC-B Codex 完成 → handoff → PC-C 的 Claude NPC 审查代码 + 烧录前 lint
- PC-C Claude 通过 → 触发 H3 审批 → 你点"批准" → 实际烧录

每一步在平台都能看到，CLI 端也能看到。这才是"多电脑 AI 协作"。
