# OpenClaw 性能优化指南

## 当前配置

- **模型**: Claude Sonnet 4.6（已优化）
- **超时**: 300秒
- **响应时间**: 约 10-60秒（取决于任务复杂度）

## 已完成的优化

1. ✓ 切换到 Sonnet 4.6（比 Opus 快 3-5倍）
2. ✓ 增加超时到 5分钟（支持复杂任务）

## 进一步优化选项

### 1. 清理 OpenClaw 会话历史

```bash
# 清理旧会话，减少上下文
rm -rf /home/pi/.openclaw/agents/main/sessions/*
systemctl --user restart openclaw-gateway.service
```

### 2. 减少 maxTokens（更快响应）

编辑 `/home/pi/.openclaw/openclaw.json`:
```json
"maxTokens": 4096  // 从 8192 降到 4096
```

### 3. 使用 Haiku 模型（最快，适合简单任务）

如果任务简单，可以切换到 Haiku:
```json
"primary": "custom/claude-haiku-4-5"
```

响应时间: 2-5秒

### 4. 混合模式（推荐）

- 简单问答: Haiku（2-5秒）
- 一般任务: Sonnet（10-30秒）
- 复杂任务: Opus（30-60秒）

需要在代码中根据消息长度/复杂度选择模型。

## 性能对比

| 模型 | 响应时间 | 质量 | 适用场景 |
|------|---------|------|---------|
| Haiku 4.5 | 2-5秒 | 良好 | 简单问答、状态查询 |
| Sonnet 4.6 | 10-30秒 | 优秀 | 一般任务、代码生成 |
| Opus 4.6 | 30-60秒 | 最佳 | 复杂推理、多步骤任务 |

## 当前建议

保持 Sonnet 4.6，这是速度和质量的最佳平衡。

如果需要更快响应，可以：
1. 清理会话历史
2. 降低 maxTokens
3. 对简单任务使用 Haiku
