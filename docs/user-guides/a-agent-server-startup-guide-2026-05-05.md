# A Agent 服务器启动教程

更新时间：2026-05-05

适用场景：

- 先用当前这台 Windows 电脑当服务器。
- 同一局域网内的其他电脑通过浏览器访问平台。
- 其他电脑用 runner 脚本接入 Codex / Claude / Qwen 等本机线程。
- 暂时不做公网暴露；公网正式部署前需要 HTTPS、域名、备份、权限和防火墙加固。

默认端口：

- Web：`3000`
- API：`8010`
- 本机访问：`http://127.0.0.1:3000`
- 局域网访问：`http://<服务器局域网 IP>:3000`

---

## 1. 启动前确认

在服务器电脑上确认项目目录存在：

```powershell
cd D:\ai合作产品
```

确认依赖已经安装过：

```powershell
npm install
python -m pip install -r apps\api\requirements.txt
```

如果之前已经安装过依赖，可以跳过这一步。

确认服务器电脑的局域网 IP：

```powershell
ipconfig
```

一般看 `无线局域网适配器 WLAN` 或 `以太网适配器` 下面的 IPv4 地址，例如：

```text
192.168.2.44
```

后文用 `<服务器IP>` 代替这个地址。

---

## 2. 推荐启动方式：一键局域网服务器模式

在服务器电脑打开 PowerShell：

```powershell
cd D:\ai合作产品
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_local_server_mode.ps1 -WebPort 3000 -ApiPort 8010
```

这个脚本会自动做这些事：

- 停掉占用 `3000` / `8010` 的旧进程。
- 自动识别服务器局域网 IP。
- 执行 `npm run build:web`。
- 启动 API：`0.0.0.0:8010`。
- 启动 Web：`0.0.0.0:3000`。
- 设置浏览器访问 API 所需的环境变量。
- 尝试创建 Windows 防火墙局域网放行规则。
- 写入状态文件：`D:\ai合作产品\artifacts\local-server-mode-status.json`。

如果 PowerShell 不是管理员权限，脚本可能无法自动创建防火墙规则。服务本身仍可能启动成功，但其他电脑可能访问不到。

启动成功后会输出类似：

```json
{
  "lan_ip": "192.168.2.44",
  "web_url": "http://192.168.2.44:3000",
  "api_url": "http://192.168.2.44:8010"
}
```

---

## 3. 打开平台

服务器电脑本机打开：

```text
http://127.0.0.1:3000/login
http://127.0.0.1:3000/projects
```

其他电脑打开：

```text
http://<服务器IP>:3000/login
http://<服务器IP>:3000/projects
```

例如：

```text
http://192.168.2.44:3000/login
http://192.168.2.44:3000/projects
```

API 健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/api/health
Invoke-RestMethod http://<服务器IP>:8010/api/health
```

正常会看到 `status = ok`。

---

## 4. 其他电脑访问不到时，先检查防火墙

如果服务器本机能打开，但其他电脑打不开，优先检查 3 件事：

1. 其他电脑和服务器是否在同一个局域网。
2. 其他电脑访问的是 `http://<服务器IP>:3000`，不是 `127.0.0.1`。
3. Windows 防火墙是否放行了 `3000` 和 `8010`。

管理员 PowerShell 可手动放行：

```powershell
New-NetFirewallRule -DisplayName "AI Collab Platform Web 3000" -Direction Inbound -Action Allow -Enabled True -Profile Public,Private -Protocol TCP -LocalPort 3000 -RemoteAddress LocalSubnet
New-NetFirewallRule -DisplayName "AI Collab Platform API 8010" -Direction Inbound -Action Allow -Enabled True -Profile Public,Private -Protocol TCP -LocalPort 8010 -RemoteAddress LocalSubnet
```

如果路由器开启了 AP 隔离、访客网络隔离，其他电脑也会访问不到，需要换到同一个普通局域网。

---

## 5. 给其他电脑接入 runner

目标：让其他电脑变成平台里的“电脑节点”，并把那台电脑上的 Codex / Claude / Qwen 线程同步到项目里。

用户路径：

1. 服务器启动成功。
2. 浏览器进入平台。
3. 打开目标项目。
4. 进入 `电脑接入管理`。
5. 添加电脑，填写电脑名称。
6. 生成配对令牌。
7. 复制平台给出的 PowerShell 接入命令。
8. 在目标电脑 PowerShell 执行。
9. 回到平台点击扫描线程。

平台生成的命令大致长这样：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { New-Item -ItemType Directory -Force -Path .\ai-collab-runner | Out-Null; Invoke-WebRequest -UseBasicParsing -Uri 'http://<服务器IP>:3000/downloads/runner/connect-ai-collab-runner.ps1' -OutFile '.\ai-collab-runner\connect-ai-collab-runner.ps1'; & '.\ai-collab-runner\connect-ai-collab-runner.ps1' -Server 'http://<服务器IP>:8010' -PairingToken '<配对令牌>' -ComputerNodeId '<电脑ID>' -RunnerName '<电脑名> Runner' -RunnerId '<runner-id>' -ProjectId '<项目ID>' }"
```

注意：

- 目标电脑不需要提前有 `D:\ai合作产品`。
- 目标电脑会从服务器下载最新版 runner 脚本。
- 目标电脑自己的项目路径由那台电脑自己决定，不应该强行写死成服务器电脑路径。
- 如果要扫描真实 Claude/Codex 线程，目标电脑必须先打开对应 AI 工具并产生会话记录。

---

## 6. 线程扫描规则

runner 注册成功后，平台会尝试扫描：

- Codex 会话。
- Claude 会话。
- 后续可扩展 Qwen / GLM / OpenClaw 等 provider。

常见提示解释：

```text
Codex session index was not found
```

说明目标电脑当前没有找到 Codex 的会话索引。处理方式：

- 在目标电脑打开 Codex。
- 至少进入一次对应项目或会话。
- 回平台重新扫描线程。
- 如果仍扫不到，可以先手动绑定一个 Codex 线程占位。

```text
No live Claude sessions found
```

说明目标电脑当前没有活跃 Claude CLI 会话。处理方式：

- 在目标电脑打开 Claude Code / Claude CLI。
- 让 Claude 进入一个真实工作目录。
- 回平台重新扫描。
- 如果目标电脑只做只读任务，也可以先手动绑定 Claude 占位线程。

线程显示没有名字时：

- 先打开该 AI 的真实会话，让它有第一条用户消息或会话标题。
- 再扫描一次。
- 平台后续仍需要继续优化“线程命名”和“线程去重”。

---

## 7. 停止服务器

推荐停止方式：

```powershell
cd D:\ai合作产品
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_local_server_mode.ps1
```

这个脚本会读取：

```text
D:\ai合作产品\artifacts\local-server-mode-status.json
```

然后停止上次一键启动的 API 和 Web 进程。

如果状态文件丢失，可以手动查看端口进程：

```powershell
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 3000,8010 } | Select-Object LocalPort,OwningProcess
```

再按 PID 停止：

```powershell
Stop-Process -Id <PID> -Force
```

---

## 8. 开发模式手动启动

如果一键脚本启动失败，或者要调试日志，可以分两个 PowerShell 窗口手动启动。

窗口 1：启动 API

```powershell
cd D:\ai合作产品\apps\api
$env:CORS_ALLOWED_ORIGINS = "http://127.0.0.1:3000,http://localhost:3000,http://<服务器IP>:3000"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8010
```

窗口 2：启动 Web 开发服务

```powershell
cd D:\ai合作产品
$env:INTERNAL_API_BASE_URL = "http://127.0.0.1:8010"
$env:NEXT_PUBLIC_API_BASE_URL = "http://<服务器IP>:8010"
$env:NEXT_PUBLIC_SUPERTOKENS_API_DOMAIN = "http://<服务器IP>:8010"
npm --workspace apps/web run dev -- --hostname 0.0.0.0 --port 3000
```

开发模式适合调试；正式给其他电脑试用时，优先用 `start_local_server_mode.ps1`。

---

## 9. 用户视角验收清单

每次启动服务器后，建议按这个顺序走一遍：

1. 本机打开 `http://127.0.0.1:3000/login`。
2. 其他电脑打开 `http://<服务器IP>:3000/login`。
3. 登录后进入 `项目列表`。
4. 新建一个测试项目，或进入已有项目。
5. 邀请一个协作者账号加入项目。
6. 在项目里打开 `电脑接入管理`。
7. 添加一台电脑。
8. 生成配对令牌。
9. 在目标电脑执行 runner 接入命令。
10. 回平台确认 runner 在线。
11. 扫描线程。
12. 创建 NPC。
13. 绑定某台电脑的某条线程。
14. 给 NPC 发送一条“非自动化”的只读测试任务。
15. 检查是否出现最小回执。
16. 检查最终回复池是否可见。
17. 再开启 NPC 自动化，确认心跳时间和 token 消耗边界清楚。

建议第一条协作任务使用只读任务，例如：

```text
请只阅读当前项目说明，不要改文件。回复：你看到了哪个项目、当前绑定的线程名、你是否能执行只读协作。
```

---

## 10. 常见故障

### ERR_CONNECTION_REFUSED

含义：目标端口没有服务。

处理：

- 确认 API 8010 和 Web 3000 是否都启动。
- 本机访问 `http://127.0.0.1:8010/api/health`。
- 本机访问 `http://127.0.0.1:3000/login`。
- 如果刚 build 过，重新运行 `start_local_server_mode.ps1`，避免旧 Next 进程还在服务旧产物。

### 其他电脑能打开 Web，但 runner 注册失败

处理：

- 确认 runner 命令里的 `-Server` 是 `http://<服务器IP>:8010`，不是 `3000`。
- 确认 pairing token 是刚生成的、没有复制错。
- token 报 `PAIRING_TOKEN_INVALID` 时，回平台重新生成一枚新 token。

### 生成 token 后按钮一直转

处理：

- 先刷新页面，确认 token 是否已经生成成功。
- 如果刷新后 token 已存在，说明是前端反馈状态问题，不是后端失败。
- 后续需要继续把按钮成功态、失败态和重试态做得更明确。

### 线程显示不全

处理：

- 确认扫描脚本的 `-Take` 数量，默认可能只取最近若干条。
- 重新打开目标 AI 工具后再扫描。
- 对重要线程手动命名，避免只看到时间戳或短 ID。

### Claude 识别不到

处理：

- 目标电脑先打开 Claude Code / Claude CLI。
- 让 Claude 进入真实工作目录。
- 确认平台 runner 是最新版下载脚本。
- 如果仍然没有 live session，先绑定一个 Claude 手动占位线程，后续再替换成真实会话。

---

## 11. 当前商业化边界

现在适合：

- 本机当服务器。
- 局域网多人试用。
- 多电脑接入 runner。
- Codex / Claude 等线程逐步进入平台协作。
- 只读协作、最小回执、最终回复池验证。

现在不建议：

- 直接暴露公网。
- 给陌生用户开放注册。
- 让 AI 自动执行高风险文件修改、硬件刷写或 Git 回退。
- 在没有人工审核边界时开大规模自动化。

正式公网版本至少还要补：

- HTTPS 和域名。
- 数据库备份。
- 管理员账号体系。
- 项目/账号/电脑/NPC 权限隔离复测。
- runner 权限分级。
- AI 操作审计。
- 高风险操作人工确认。
