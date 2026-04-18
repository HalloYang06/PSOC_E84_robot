# AI 协作平台开发环境规范

版本：v0.1  
用途：统一人类工程师、AI 工程师、Runner 节点和服务器的开发环境  
适用范围：AI 协作开发平台本身

---

## 1. 环境类型

本项目需要区分以下环境：

```text
local-dev        本地开发环境
ai-runner        AI Runner 执行环境
lab-server       实验室服务器环境
edge-device      开发板/边缘设备环境
staging          测试环境
production       正式环境，后期才需要
```

第一版重点支持：

```text
local-dev
ai-runner
lab-server
edge-device-lite
```

---

## 2. 推荐开发机器配置

### 2.1 人类开发电脑

最低配置：

```text
CPU: 4 核
内存: 16GB
磁盘: 100GB 可用空间
系统: Windows 10/11、Ubuntu 22.04+、macOS 皆可
```

推荐配置：

```text
CPU: 8 核以上
内存: 32GB
磁盘: 500GB SSD
系统: Windows 11 + WSL2 或 Ubuntu 22.04/24.04
```

### 2.2 实验室服务器

MVP 推荐：

```text
CPU: 8 核以上
内存: 32GB
磁盘: 500GB SSD
系统: Ubuntu Server 22.04/24.04
网络: 局域网固定 IP
部署: Docker Compose
```

团队可用版本推荐：

```text
CPU: 16-32 核
内存: 64GB+
磁盘: 2TB NVMe
系统: Ubuntu Server 22.04/24.04
网络: 局域网固定 IP + VPN
```

### 2.3 AI Runner 电脑

普通 Runner：

```text
CPU: 4 核以上
内存: 16GB+
磁盘: 100GB+
依赖: Git、Python、Node.js、Docker
```

嵌入式 Runner：

```text
CPU: 4 核以上
内存: 16GB+
磁盘: 200GB+
依赖: 交叉编译工具链、串口工具、Git、Python
```

ROS Runner：

```text
系统: Ubuntu 22.04 推荐
依赖: ROS 2 Humble 或项目指定 ROS 版本
可选: Gazebo、MoveIt、Docker
```

GPU Runner：

```text
GPU: NVIDIA GPU
驱动: NVIDIA Driver
依赖: CUDA、cuDNN、Docker NVIDIA runtime
用途: 模型训练、视觉推理、仿真
```

### 2.4 开发板/边缘设备

开发板不建议跑完整平台，只跑轻量 Runner 或状态采集服务。

最低要求：

```text
能运行 Python 或轻量 Agent
能访问平台 API
能上传日志
能上报设备状态
```

开发板端只做：

```text
Runner 心跳
当前任务状态
串口日志上传
硬件确认清单
设备状态上报
```

不建议开发板端做：

```text
完整前端
完整数据库
完整 Git 服务
大模型推理
复杂构建任务
```

---

## 3. 基础软件版本

推荐统一版本：

```text
Git: 2.40+
Node.js: 20 LTS
pnpm: 9+
Python: 3.11+
Docker: 24+
Docker Compose: v2+
PostgreSQL: 16
Redis: 7
Gitea/Forgejo: 最新稳定版
MinIO: 最新稳定版
```

前端：

```text
Next.js: 14 或 15
React: 18 或 19
TypeScript: 5+
Tailwind CSS: 3 或 4
```

后端：

```text
FastAPI
Pydantic v2
SQLAlchemy 2
Alembic
Uvicorn
httpx
pytest
```

Runner：

```text
Python 3.11+
Git CLI
Docker CLI，可选
平台 Runner SDK
Agent Adapter SDK
```

---

## 4. 推荐端口规划

本地开发端口：

```text
3000   前端 Next.js
8000   后端 API
5432   PostgreSQL
6379   Redis
3001   Gitea/Forgejo Web
2222   Gitea/Forgejo SSH
9000   MinIO API
9001   MinIO Console
8080   Orchestrator，可选
8090   Runner debug，可选
```

注意：

1. 正式部署时不要直接暴露数据库、Redis、MinIO 内部端口到公网。
2. Runner 不建议被公网直接访问。
3. 外网访问建议通过 VPN 或反向代理。

---

## 5. 环境变量规范

统一使用 `.env`，仓库只提交 `.env.example`。

禁止提交：

```text
.env
.env.local
.env.production
*.pem
*.key
id_rsa
token.txt
secrets.json
```

### 5.1 后端环境变量

```env
APP_ENV=local
APP_NAME=ai-collab-platform
API_HOST=0.0.0.0
API_PORT=8000

DATABASE_URL=postgresql+psycopg://user:password@postgres:5432/ai_collab
REDIS_URL=redis://redis:6379/0

SECRET_KEY=change-me
TOKEN_ENCRYPTION_KEY=change-me

GITEA_BASE_URL=http://gitea:3000
GITEA_TOKEN=change-me

MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=change-me
MINIO_SECRET_KEY=change-me
MINIO_BUCKET=ai-collab

GITHUB_APP_ID=
GITHUB_APP_PRIVATE_KEY=
GITHUB_TOKEN=
```

### 5.2 前端环境变量

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=AI Collab Platform
```

前端环境变量注意：

```text
NEXT_PUBLIC_* 会暴露到浏览器。
任何 token、密钥、密码都不能使用 NEXT_PUBLIC_*。
```

### 5.3 Runner 环境变量

```env
RUNNER_ID=runner-pc1
RUNNER_NAME=PC1
PLATFORM_API_URL=http://localhost:8000
RUNNER_TOKEN=change-me
RUNNER_WORKDIR=D:/ai-runner-workspace
RUNNER_CAPABILITIES=git,node,python,docker
ALLOW_HARDWARE_ACCESS=false
MAX_CONCURRENT_TASKS=1
```

---

## 6. Docker Compose 服务

MVP 推荐服务：

```text
frontend
backend
postgres
redis
gitea
minio
orchestrator
runner-general
```

后续可增加：

```text
prometheus
grafana
loki
vector
ollama
qdrant
nginx
```

---

## 7. 本地开发启动流程

推荐流程：

```text
1. 安装 Git、Node.js、pnpm、Python、Docker。
2. 克隆仓库。
3. 复制 `.env.example` 为 `.env`。
4. 修改数据库、Redis、Gitea、MinIO 配置。
5. 执行 docker compose up -d postgres redis gitea minio。
6. 启动后端。
7. 执行数据库 migration。
8. 启动前端。
9. 注册第一个 Runner。
10. 创建第一个项目。
```

示例命令：

```bash
docker compose up -d postgres redis gitea minio
pnpm install
pnpm dev
```

后端示例：

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Windows PowerShell 虚拟环境：

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

---

## 8. AI Runner 环境准备

Runner 安装流程：

```text
1. 安装 Python 3.11+。
2. 安装 Git。
3. 安装需要的编译工具。
4. 配置 RUNNER_TOKEN。
5. 配置 RUNNER_WORKDIR。
6. 启动 Runner。
7. 在平台确认 Runner 在线。
8. 运行测试任务。
```

Runner 工作目录建议：

```text
D:/ai-runner-workspace
/opt/ai-runner/workspace
```

Runner 目录结构：

```text
workspace/
  tasks/
    TASK-001/
    TASK-002/
  cache/
  logs/
  artifacts/
```

---

## 9. 嵌入式开发环境

按项目需要安装：

```text
ARM GCC 工具链
CMake
Ninja
OpenOCD
J-Link 工具
串口工具
Python 脚本环境
芯片 SDK
```

常用工具：

```text
arm-none-eabi-gcc
cmake
ninja
openocd
pyserial
platformio，可选
STM32CubeProgrammer，可选
JLinkExe，可选
```

注意：

1. AI 可以触发编译。
2. AI 可以分析编译错误。
3. AI 不默认触发烧录。
4. 烧录必须 H3 人工确认。

---

## 10. ROS 开发环境

推荐：

```text
Ubuntu 22.04
ROS 2 Humble
colcon
rosdep
Gazebo，可选
MoveIt，可选
```

基础命令：

```bash
source /opt/ros/humble/setup.bash
colcon build
colcon test
ros2 topic list
ros2 node list
```

注意：

1. ROS Runner 适合部署在 Ubuntu。
2. 仿真可以由 AI 触发。
3. 真机运动必须人类确认。

---

## 11. 模型和 Agent 环境

支持模型来源：

```text
OpenAI-compatible API
OpenAI
Claude
Qwen
DeepSeek
Ollama 本地模型
其他自定义 HTTP Agent
```

Agent 工具：

```text
OpenHands
Codex
OpenClaw
Claude Code
自定义 Agent Adapter
```

密钥管理原则：

```text
模型 API key 只保存在后端 Secret 管理中。
Runner 只拿临时任务凭证。
前端永远不显示明文密钥。
```

---

## 12. 数据和日志目录

建议：

```text
data/
  postgres/
  redis/
  gitea/
  minio/
  runner/
  logs/
```

对象存储保存：

```text
任务完整日志
构建产物
固件
截图
上传的硬件照片
串口日志
交接包附件
```

---

## 13. 浏览器支持

需要支持：

```text
Chrome
Edge
Firefox
Safari，基础支持
手机浏览器
开发板 Chromium，轻量支持
```

前端适配断点：

```text
mobile: 360px+
tablet: 768px+
desktop: 1200px+
wide: 1600px+
```

---

## 14. 网络和访问方式

实验室内网：

```text
平台服务器使用固定 IP。
开发电脑通过局域网访问。
Runner 主动连接平台 API。
```

远程访问建议：

```text
Tailscale
ZeroTier
WireGuard
VPN
```

不建议：

```text
直接把数据库暴露公网。
直接把 Runner 暴露公网。
直接把开发板暴露公网。
```

---

## 15. 备份环境要求

必须备份：

```text
PostgreSQL
Gitea/Forgejo 仓库
MinIO 对象存储
Secret 配置
平台配置
```

备份频率建议：

```text
开发阶段: 每日
团队可用阶段: 数据库每小时增量 + 每日全量
正式阶段: 异地备份
```

---

## 16. 环境验收清单

本地开发环境：

```text
[ ] Node.js 可用
[ ] pnpm 可用
[ ] Python 可用
[ ] Docker 可用
[ ] PostgreSQL 可连接
[ ] Redis 可连接
[ ] Gitea/Forgejo 可访问
[ ] MinIO 可访问
[ ] 前端可启动
[ ] 后端可启动
```

Runner 环境：

```text
[ ] Runner 能注册
[ ] Runner 心跳正常
[ ] Runner 能拉取任务
[ ] Runner 能创建工作区
[ ] Runner 能执行测试命令
[ ] Runner 能回传日志
[ ] Runner 不暴露明文 token
```

嵌入式环境：

```text
[ ] 工具链可用
[ ] 编译命令可运行
[ ] 串口工具可用
[ ] 固件产物可保存
[ ] 烧录操作需要人工确认
```

ROS 环境：

```text
[ ] ROS 安装完成
[ ] colcon build 可运行
[ ] ros2 topic list 可运行
[ ] 仿真环境可选可用
[ ] 真机运动需要人工确认
```

---

## 17. 第一版推荐环境组合

最推荐第一版组合：

```text
一台主开发电脑:
  前端 + 后端开发

一台实验室服务器:
  PostgreSQL + Redis + Gitea + MinIO + 后端部署

一台普通 Runner:
  执行代码任务和测试

一台 ROS Runner:
  ROS 编译和仿真

开发板轻量 Runner:
  只上传状态和日志
```

如果资源有限，也可以先用一台高配置电脑跑全部服务。

---

## 18. 总结

环境设计要遵守：

```text
平台服务集中部署。
Runner 分布式执行。
开发板轻量接入。
密钥后端托管。
硬件操作人工确认。
本地先跑通，再扩展服务器和多 Runner。
```

