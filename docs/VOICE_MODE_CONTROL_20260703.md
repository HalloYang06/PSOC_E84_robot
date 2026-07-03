# XiaoZhi Voice Mode Control

这份记录说明当前“小智语音切换 M33 控制模式”的最小闭环。

## 1. 当前链路

```text
用户说话
  -> M55 小智 voice_service 收到 STT 文本
  -> M55 发布 MSG_TYPE_ASR_TEXT 给 M33
  -> M33 m55_model_bridge 转给 m55_voice_mode_bridge
  -> M33 白名单解析
  -> control_set_mode(...)
```

语音识别和云端交互仍然在 M55。真正切控制模式仍然在 M33，这样 M33 继续作为电机和安全状态的 owner。

## 2. 支持的语音文本

当前只做白名单匹配。

```text
切换到被动模式
停止
退出
进入主动模式
切换到记忆模式
开启助力模式
进入 AI assist
```

映射关系：

```text
被动 / 停止 / 退出 / stop / passive -> CONTROL_MODE_PASSIVE
主动 / active                         -> CONTROL_MODE_ACTIVE
记忆 / memory                         -> CONTROL_MODE_MEMORY
助力 / 辅助 / assist / ai assist       -> CONTROL_MODE_ASSIST
```

为了避免把普通问答误当控制命令，包含下面词的文本会被忽略：

```text
什么
怎么
如何
吗
是不是
?
```

非被动模式还必须带命令提示词，例如“切换、进入、启动、开启、设置、模式、switch、set、start”。所以“主动模式是什么”不会切模式。

## 3. 串口验证

先确认 M55 能把识别文本发到 M33。说一句话后，M33 应看到：

```text
[m55_model_bridge] asr text: ...
```

如果是可执行的模式命令，M33 应继续打印：

```text
[voice_mode] set mode=... ret=0 text=...
```

如果不是控制命令，M33 打印：

```text
[voice_mode] ignore text: ...
```

## 4. 安全边界

这次只切 `control_manager` 的模式状态，不直接调用 `control_move_joint()`，也不直接发电机命令。

后续如果要让语音触发运动，必须再加安全检查和二次确认。急停仍然不能依赖语音，应该保留物理急停或本地安全链路。

