# wifi 避坑文档

## 47. 2026-06-26 XiaoZhi 离线根因：M55 IPC 预检拒绝了 M33 实际 shared IPC 指针

现象：

1. 现场 LVGL 显示小智没有连接上，M33 shell 仍能运行 `m55qa_status`。
2. `m55qa_status` 一度只能打印浅层 `ipc_ready=1 tx_pending=0 rx_pending=0 has_model=0`，没有完整 `voice_status`。
3. OpenOCD 看到 M33/M55 都在 Thread mode，M55 PC 在 `0x6068....`，说明不是 CM55 app 完全没跑。
4. 平台 PC 侧 WebSocket smoke 使用新项目 token 后可收到 `{"type":"hello","version":3}`，说明云端公网 WebSocket 已经可接受。

根因：

1. M33 当前镜像里 `g_m33_m55_shared_data` 实际位于 `.cy_sharedmem 0x240fe000`。
2. M55 上一轮为避免早期脏共享指针 HardFault，只允许 `0x261C0000-0x26200000` 和 `0x061C0000-0x06200000`。
3. 结果 M55 把 M33 的真实 shared IPC 指针当成非法地址拒绝，`m33_m55_comm_init()` 长期 deferred attach，`xz_bridge` 无法消费 M33->M55 控制消息，也无法回传完整 voice status。
4. 这会表现成 token 写不进去、队列容易满、LVGL 连接态不更新，但不是 WiFi 扫描或 WHD resources 问题。

修复：

1. M55 `applications/m33_m55_comm.c` 保留脏指针预检，但新增合法范围 `0x24000000-0x24100000`，覆盖 M33 SRAM 内的 `.cy_sharedmem`。
2. 同步到 `_m55_ref_repo`，避免实际烧录树和 Git 镜像分叉。
3. 云端确认设备绑定到真实项目 `fd6a55ed-a63c-44b3-b123-96fb3c154966`，PC WebSocket smoke 可收到 hello。
4. 通过 M33 `tools/load_xiaozhi_token.ps1` 以 40 字符 chunk 慢速写入新 scoped relay token。

验证：

1. M55 build 通过，`text=1682092 data=81404 bss=4533184`。
2. M55 flash 通过：`rtthread.hex wrote 1765376 bytes`，`whd_resources_all.bin wrote 466944 bytes`。
3. M33 重新 verify 通过：`verified 543252 bytes`。
4. 修复后 `m55qa_status` 恢复完整 `voice_status`，并显示：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_token=1 token_len=455`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `srv_hello=1`
   - `tx_pending=0`
   - `lcd_init=0 lvgl_flush` 持续增长

避坑：

1. `ipc_ready=1` 只说明 M33 侧 IPC 初始化，不代表 M55 已经 attach 并能消费队列。必须看到完整 `voice_status` 才能继续 token/QA。
2. 如果 `m55qa_status` 只有浅层输出，先查 M55 `m33_m55_comm` attach 和 shared pointer 范围，不要先回 WiFi/token/resource。
3. 单次 `m55qa_xz_token_part` 成功不代表整条 token 成功；必须看 `voice_ack cmd=1006 result=0` 和最终 `token_len/xz_ws`。

## 46. 2026-06-26 M55 不是简单资源爆满，而是早期 IPC 句柄读到脏共享指针

现象：

1. 用户现场看到 M33/M55 都不像正确启动，系统灯也不亮。
2. 之前怀疑是资源爆了，但实际复现里 build/link 没有直接超限。
3. OpenOCD 抓到的是 M55 早期 HardFault，Fault 地址是类似 `0x1924bf42` 的脏指针，不是典型的纯内存越界报错。

本轮判断：

1. 重点不是继续改 WiFi/token/platform。
2. M55 `mtb_ipc_get_handle()` 在启动早期会去读 M33 写入的共享 IPC 指针；如果 M33 还没把共享对象稳定起来，或者残留了旧值，就可能把脏地址当成 `mtb_ipc_shared_t*` 继续解引用。
3. 这次加了 M55 启动前的共享指针预检，只接受 `0x261C0000-0x26200000` 或别名区 `0x061C0000-0x06200000`，否则延迟重试，不再直接进 HardFault。

本轮修复：

1. M55 `applications/m33_m55_comm.c` 增加 IPC shared ptr 预检。
2. 如果 shared ptr 不在合法共享 RAM 区，M55 先等待，再重试 attach。
3. 同步到 `_m55_ref_repo` 镜像，避免实际烧录树和可提交镜像再次分叉。
4. 本轮把本地 `xiaorui` 默认阈值降到 `550/1000`，并放宽本地语音活动门，现场更容易触发“我在”。

验证：

1. M55 build 通过，`text=1677884 data=81404 bss=4533184`。
2. M55 烧录通过，`rtthread.hex wrote 1761280 bytes`，`whd_resources_all.bin wrote 466944 bytes`。
3. OpenOCD reset-run 后，M55 已能跑到线程态，不再停在 HardFault；CM33 也保持运行。

## 45. 2026-06-25 小智体验差要先看音频块、播放队列、唤醒阈值

现象：

1. 平台能回 TTS，但扬声器人声卡顿、不清晰。
2. 多问几轮后停止/唤醒/下一轮状态变差。
3. “小瑞”本地唤醒不稳定。

本轮判断：

1. 不是优先回到 WiFi/token/平台配置。M55 已经能打通平台链路时，体验差更像本地音频和状态机问题。
2. M55 `sound0` 之前使用 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`，16k/mono/16bit 下约 128ms；小智音频帧是 60ms，这会造成攒帧、尾包延迟和听感不连续。
3. `sound0` replay queue 过浅时，TTS worker 会等待队列释放；等待太久会拖累 stop/re-arm 和后续轮次体验。
4. 唤醒模型默认阈值 `800/1000` 对现场小声/远场偏硬，且之前 mic peak 偏低。

本轮修复：

1. M55 audio replay block 改为 `1920` 字节，正好对应 16k/mono/16bit 的 60ms 小智帧。
2. M55 audio replay block count 和 replay queue count 改为 `8`，降低播放队列抖动。
3. M55 TTS replay 高水位从 `2` 提到 `6`，等待上限从 `2000ms` 降到 `300ms`，避免播放堵塞拖死下一轮状态。
4. 小瑞唤醒 Edge Impulse 默认阈值从 `800/1000` 降到 `650/1000`。
5. M55 PDM gain 从 `24` 提到 `32`，提升本地唤醒输入幅度。

补充：

1. 这轮又把本地唤醒默认阈值从 `650/1000` 放到 `600/1000`。
2. 语音活动门限也进一步放松，避免现场“喊了但模型没机会判”。
3. 唤醒触发后会先播本地固定反馈“我在”，再进入后续对话。

验证：

1. M55 build 已完成，`rtthread.hex` 更新时间为 `2026-06-25 13:34:49`。
2. M55 flash 通过：`rtthread.hex` 写入 `1744896 bytes`，`whd_resources_all.bin` 写入 `466944 bytes`。
3. COM4 仍为 `0 bytes`，OpenOCD 之前确认 CM33 在 RT-Thread idle；需要物理 Reset 或短断电后继续 `m55qa_status` 和真实“小瑞”测试。

## 44. 2026-06-25 小瑞唤醒保持 xiaorui，现场诊断不要扩大共享状态结构

用户确认唤醒词仍然是“小瑞”，代码里应保持 `xiaorui`，不要改成 `OK Infineon`。

本轮改动：

1. M55 Edge Impulse wake 后端保留默认阈值 `800/1000`，但改为运行时阈值变量，便于现场通过 IPC 临时调低验证。
2. M55 wake 推理日志加密度，输出 `threshold / feature_src / feature_ret / noise / xiaorui`。
3. 唤醒成功日志增加 `conf / noise / threshold`，便于确认本地“我在”是否由模型触发。
4. M33 QA 增加 `m55qa_wake_threshold <0..1000>` 控制命令，并在 `m55qa_status` 中从现有 `err` 解码 `wake_feature / wake_noise / wake_xiaorui`。

避坑：

1. 不要给 `voice_status_msg_t` 直接加 wake 诊断字段；M33 `.cy_sharedmem` 会溢出。
2. 当前 wake 诊断继续使用 M55 `voice_status.last_error` 的既有编码：
   - `feature_src = err / 1000000`
   - `noise = (err / 1000) % 1000`
   - `xiaorui_confidence = err % 1000`
3. 若 `wake_on=1 wake_ready=1 frames/windows` 增长，但 `wake_xiaorui=0`，优先看 mic 幅度和模型置信度，不要回退到 WiFi/token/平台配置。

验证状态：

1. M55 build 通过：`text=1660960 data=81464 bss=4532828`。
2. M55 flash 通过：`rtthread.hex` 写入 `1744896 bytes`，`whd_resources_all.bin` 写入 `466944 bytes`。
3. 本轮最后 COM4 无输出但 OpenOCD 显示 CM33 在 RT-Thread idle；需要物理 Reset 或短断电后继续现场唤醒 QA。

## 43. 2026-06-23 官方小智协议只作为协议参考，平台仍连接自有平台

本轮用户明确要求：参考官方小智做法，但继续连接自己的平台。不要因为“官方小智”四个字去切 URL、token 或 WiFi 资源。

已确认官方协议方向：

1. WebSocket JSON 负责 `hello/listen/tts/stt/error` 等事件。
2. 音频 binary 走 Opus。
3. protocol v3 binary 需要按帧头拆出 Opus payload，不能只剥第一帧头后把整包当单帧处理。

本轮有效修复：

1. LVGL 小智在线态以 `token && websocket_client_is_connected()` 为主，避免 COM4 已经 `xz_ws=1` 但屏幕还显示未连接。
2. M55 TTS pending slot 从 4KB 增大到 16KB。
3. M55 binary TTS 保留完整 v3 payload 入 pending，由 TTS worker 循环拆 v3 Opus frame 后转 PCM 给 M33。
4. M55->M33 TTS IPC 增加节流和 retry，避免真实平台 TTS 下发时把 M33 speaker 队列压满。
5. 曾尝试把 M55 auto reconnect 改成异步线程，但现场回归为 `xz_stage=20` 且手动 reconnect 排队不恢复；已回退，只保留稳定同步 reconnect。

验证：

1. M55 构建通过：
   - `text=1534136 data=68744 bss=4541616`
2. M55 烧录通过：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. 最终基线恢复：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_token=1 token_len=442`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
4. v3/TTS 测试阶段已经看到真实 mic0 触发自有平台 TTS 并进入 M33 speaker：
   - `xz_last=114/218880`
   - `xz_rx=3/3`
   - M33 `tts audio rx total=1920`
   - M33 `tts audio write chunk=1/2/3`

注意：

1. 不要把“参考官方小智协议”理解为切换平台。
2. 如果后续又看到 `xz_stage=20` 卡住，先检查最近是否改过 reconnect 线程/桥接队列，不要先动 token。
3. M33 CM55 voice-status watchdog 已在 M33 工程构建通过，但本轮未确认 M33 烧录入口，暂未烧入现场板。

## 42. 2026-06-23 WebSocket 正常但真实 mic0 不上传时，先查 M55 mic 线程 stale

本轮继续只处理英飞凌 M55/M33 小智语音链路，不改 WiFi/token/resources。

现场现象：

1. 用户侧 LVGL 看到“小智还没连上”。
2. 但 COM4 `m55qa_status` 明确显示：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `xz_token=1 token_len=442`
   - `srv_hello` 在 reconnect 后从 1 增到 2
3. `m55qa_capture_on` ACK 成功，但一轮真实 mic QA 没上传：
   - `xz_last=0/0`
   - `tts_fwd=0/0`
   - `frames/pcm_seq` 基本不动

根因：

1. M33 侧原来有两个线程消费 M55 IPC RX 队列：`main.c` 和 `voice_manager.c`。`voice_manager` 会抢走 `VOICE_STATUS/ACK`，导致 QA/status 偶发看不到最新状态。
2. 修成 M33 单消费者后，又暴露 M55 mic0 线程 stale：`g_m55_mic.running=1`，但 mic 线程已经不再产出帧。后续 capture start 认为 mic busy，不会重建 reader。

修复：

1. M33 `voice_manager_start()` 不再启动第二个 IPC consumer；由 `applications/main.c` 统一处理 `VOICE_STATUS/ACK/TTS_AUDIO`。
2. M55 `applications/main.c` 给 mic0 增加：
   - `frame_count`
   - `last_frame_tick`
3. `m55_mic_start_internal()` 如果发现 running 但超过 2 秒无帧，打印 stale 日志并重建 mic 线程。

验证：

1. M55 编译通过：
   - `text=1533960 data=68744 bss=4541616`
2. M55 烧录通过：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
   - 末尾 KitProg acquire 失败发生在写完之后，仍按已知非关键处理。
3. 烧录后基线和 mic0 采样恢复：
   - `wake_on=1 xz_ws=1 token_len=442 srv_hello=1`
   - `frames=3380 pcm_seq=3380`
4. 现场真实 mic0 QA 成功：
   - `m55qa_capture_on` ACK `0`
   - M55 上传真实 mic 音频：`xz_last=188/360960`
   - `xz_fail=0`
   - M33 收到两段平台 TTS：`tts audio rx total=320` 和 `tts audio rx total=640`
   - 最终 `tts_fwd=20/2432 tx_pending=0 xz_ws=1 xz_stage=70 xz_errno=0`

结论：

如果 `xz_ws=1/token_len=442/srv_hello>0`，但真实 mic QA 没有 `xz_last` 增长，不要回到 WiFi 扫描、token 或资源固件。优先查 `frames/pcm_seq` 是否增长，以及 M55 mic0 reader 是否 stale。

## 41. 2026-06-22 真实 CM55 mic0 小智链路已打通，起始静音不能触发 EOU

本轮在现场验证真实麦克风产品路径，不改 WiFi/token/resources。

现象：

1. `m55qa_capture_on` ACK 成功后，如果现场人员晚几秒才说话，最终可能 `xz_last=0/0`。
2. 一次刚好卡准窗口的测试出现了 `asr text`，并且 `xz_last=57/109440`，说明真实 mic0 和平台 STT 能通。
3. QA WAV 已经稳定返回 TTS，所以问题不是 WiFi/token，也不是平台不可达。

根因：

1. M55 EOU 把 `xiaozhi_last_voice_tick` 初始化为 start tick。
2. 起始静音超过最小录音时间 + 静音阈值后，会在用户还没开口前自动结束会话。

修复：

1. 增加 M55 session 标志 `xiaozhi_voice_seen`。
2. 每次 XiaoZhi listen start 清零。
3. 只有检测到真实语音后，才允许 silence-based EOU。
4. 最大录音超时仍保留，用来兜底纯静音会话。

验证：

1. M55 编译通过：
   - `text=1533800 data=68744 bss=4541608`
2. M55 烧录通过：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. 烧录后基线：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0 token_len=442 srv_hello=1`
4. 现场真实 mic0 QA：
   - `m55qa_capture_on` ACK `0`
   - M55 上传真实 mic 音频：`xz_last=188/360960`
   - `xz_fail=0`
   - M33 收到平台 TTS 并写播放：`tts audio rx total=640`、`audio_playback Started`、`tts audio idle flush chunks=5 bytes=640 ret=0`
   - 最终 `tx_pending=0`，WebSocket 仍健康。

结论：

真实产品链路已闭环：

`CM55 mic0 speech -> M55 XiaoZhi WebSocket -> platform TTS -> M33 audio_playback`

## 40. 2026-06-22 人声素材板端自测已打通到 M33 speaker 写入

本轮继续只做小智语音链路，没有回到 WiFi/token/resources。

关键结论：

1. 人声 WAV 自测链路已经在板端跑通：
   - `human WAV -> M33 QA PCM -> M55 XiaoZhi WebSocket -> platform TTS -> M33 audio_playback`
2. M55/M33 共享结构不能再随便加字段；之前扩 `voice_status_msg_t` 会导致 M33 `.cy_sharedmem` 溢出。
3. 本轮诊断只在 M55 内部加计数，并临时复用现有 status 字段输出：
   - `srv_lens = listen_start_count/listen_stop_count/start_ret`
   - `srv_err` 低 16 位 = `stop_ret`

验证：

1. M55 编译通过：
   - `text=1533768 data=68744 bss=4541600`
2. M33 编译通过：
   - `text=474160 data=15344 bss=311877`
3. M55 烧录通过：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
4. COM4 人声 QA：
   - `m55qa_probe_pcm_on` / `m55qa_capture_on` / `m55qa_capture_off` 均 ACK `0`
   - `m33qa_xz_probe full` 发 `87` 包 / `166974` 字节
   - `retries=0 tx_pending=0`
   - `probe_lwip=87/0`
   - `xz_last=151/289920`
   - `xz_fail=0`
   - M33 收到平台 TTS 下行并写播放：`tts audio rx total=320`、`audio_playback Started`、三段 `tts audio write` 共 `320` 字节、`tts audio idle flush chunks=3 bytes=320 ret=0`

边界：

1. 当前不要再把无 STT 文本计数当作 WiFi/token 故障；板端已经收到并写入 TTS audio。
2. `srv_tts/tts_fwd` 仍没有完整反映 M33 实际收到的 TTS，下次可单独修状态统计。
3. 下一步才是让用户或现场人员对真实 CM55 mic0 说话验证产品路径。

## 39. 2026-06-22 当前小智平台先走 PCM 兼容链路，已恢复 TTS 下行到 M33

本轮目标是快点恢复完整小智功能，不再纠缠 WiFi/token/resources。

关键结论：

1. PC smoke 已证明当前 e201 relay 对 `pcm_s16le` 兼容链路可返回 STT/TTS。
2. 板端 Opus 上行能发出去，但本轮只回 `listen/start` 控制文本，没有 STT/TTS。
3. 因此 M55 默认切到 `pcm_s16le` 兼容路径，先打通实际功能；Opus 保留为后续官方路线优化。

本轮修复：

1. M55 默认：
   - `XIAOZHI_USE_OFFICIAL_OPUS_AUDIO=0`
   - `hello.audio_params.format=pcm_s16le`
2. PCM 模式对齐 PC smoke：
   - hello 只带 `features.mcp`
   - `listen/start mode=auto`
   - `listen/stop` 只带 `state=stop`
3. M55 自动重连线程在 `xiaozhi_listening_active=1` 时不再 reset session，避免 capture 后短暂 WebSocket 状态波动把会话清掉。
4. M33 QA 的 `capture_on` 等 listening 状态时间加到 3 秒。

验证：

1. M55 编译通过：
   - `text=1533240 data=68744 bss=4541584`
2. M55 烧录通过：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. COM4 QA：
   - `m55qa_probe_pcm_on` / `m55qa_capture_on` / `m55qa_capture_off` 均 ACK `0`
   - `m33qa_xz_probe 3000` 发 `50` 包 / `96000` 字节
   - `retries=0 tx_pending=0`
   - `probe_lwip=50/0`
   - `xz_last=197/378240`
   - `xz_fail=0`
   - M33 收到平台 TTS 下行并写播放：`tts audio rx total=640`、`audio_playback Started`、`tts audio write chunk=1/2/3`

边界：

1. 当前可用功能链路是：
   - `M33 QA PCM / CM55 mic PCM -> M55 raw PCM WebSocket -> XiaoZhi platform -> M33 TTS audio/write`
2. 后续要用真实 CM55 mic0 人声再验一次产品路径。
3. `m55qa_status` 的 `xz_rx/tts_fwd/srv_tts` 仍未完整反映这次 M33 TTS 下行，后续观测修复要以 M33 `tts audio rx/write` 为准同步校正。

## 38. 2026-06-22 小智 stop 控制帧必须保留 start 的 mode

本轮只动小智语音协议层，没有回退 WiFi/token/资源方向。

现象：

1. `m55qa_capture_on + m33qa_xz_probe` 已能让 M55 接收全部 QA PCM，并上传 Opus：
   - `probe_lwip=50/0`
   - `xz_last` 增长
   - `xz_fail=0`
2. 但平台有时只返回 `listen/start` 类控制文本，没有 `stt/tts/binary audio`。
3. 文档里曾记录过成功链路使用 `listen start mode=manual` 和 `listen stop mode=manual`，而当前代码里的 stop 又退回成只发 `state=stop`。

修复：

1. M55 在 session start 时记录 `xiaozhi_listening_source`。
2. `listen/stop` 现在会携带：
   - `mode`
   - `audio_bytes`
   - `audio_chunks`
3. 手动 QA 路径现在是 `start mode=manual` 对应 `stop mode=manual`；本地/实时唤醒不会被误标成 manual。

验证：

1. M55 编译通过：
   - `text=1648696 data=68744 bss=4541600`
2. M33 编译通过：
   - `text=499512 data=15344 bss=311877`
3. M33 烧录通过：
   - `build/rtthread.hex` 写入 `618496 bytes`，verify `617180 bytes`
4. M55 烧录通过：
   - `rtthread.hex` 写入 `1720320 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
5. COM4 最终 QA：
   - `m55qa_probe_pcm_on` / `m55qa_capture_on` / `m55qa_capture_off` 都 ACK `0`
   - `m33qa_xz_probe 3000` 发出 `50` 包 / `96000` 字节，`retries=0 tx_pending=0`
   - `probe_lwip=50/0`
   - `xz_last=207/37053`
   - `xz_fail=0`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - 仍无平台 STT/TTS/binary：`srv_stt=0 srv_tts=0/0/0 xz_rx=2/0 tts_fwd=0/0`

边界：

如果 stop mode 修正后仍没有 STT/TTS，下一个方向是平台 relay 日志或官方小智协议差异，不是 WiFi 扫描、token 重新配置或 WHD resources。

补充：

1. M55 现在在控制 ACK 前先发布一次 status，减少 M33 读到旧 `xz_listening=0` 的窗口。
2. M33 QA 的 `m55qa_capture_on` 和 `m33qa_xz_probe` 会短等 `VOICE_STATUS_FLAG_XIAOZHI_LISTENING`，避免 ACK/status IPC 顺序造成误判。

## 31. 2026-06-20 小智链路新结论：平台下行已到 M33，剩余 blocker 是 speaker 播放

本轮确认：

1. 不要再把 WiFi/token 当主 blocker：
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `saved=1 auto=1 storage=0`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - `token_len=442`
2. M55 仍按官方产品路线：
   - `CM55 mic0 -> Opus -> WebSocket -> platform -> M33 TTS audio`
3. 为无人值守 QA 新增显式开关：
   - `m55qa_probe_pcm_on`
   - `m55qa_probe_pcm_off`
   - 只有打开 QA gate 且小智正在 listening 时，M55 才接收 `m33qa_xz_probe` 的 PCM。
4. QA gate 已验证：
   - `m55qa_probe_pcm_on` 返回 `voice_ack cmd=11 result=0`
   - `m55qa_capture_on` 返回 `voice_ack cmd=1 result=0`
   - `m33qa_xz_probe` 后，M33 收到平台下行：`tts audio rx total=1280`
   - M33 也进入播放写入：`tts audio write chunk=...`

本轮修复：

1. M55 不再把每个 TTS 下行包硬截断为最多 8 个 128B IPC chunk。
2. M55 发送 TTS chunk 到 M33 时增加短等待，避免 M33 队列瞬时满就直接丢。
3. M33 QA 控制命令增加短重试，避免瞬时 IPC 忙导致 `m55qa_capture_on ret=-255`。

当前剩余问题：

1. 平台/模型/下行不是空想，已经走到 M33。
2. 实验性的 M33 async speaker worker 会触发 RT-Thread audio 断言：
   - `(rt_object_get_type(&timer->parent) == RT_Object_Class_Timer) assertion failed at function:rt_timer_stop`
3. 因此 async speaker worker 已回退，下一步要参考板卡/RT-Thread 音频驱动的官方播放方式，而不是随便开 worker 写 `sound0`。
4. 真实用户语音仍要回到 CM55 mic0 路线验证；`m33qa_xz_probe` 只用于无人 QA，不是产品路径。

下一步建议：

1. 先修 M33 speaker 播放稳定性。
2. 再跑：
   - `m55qa_probe_pcm_on`
   - `m55qa_capture_on`
   - `m33qa_xz_probe`
   - `m55qa_capture_off`
   - `m55qa_status`
3. 成功标准是同时满足：
   - M33 出现 `tts audio rx total=...`
   - speaker 无断言
   - shell 仍响应
   - `tx_pending=0`
4. 不要回头重配 SSID/token/资源，除非 `m55qa_status` 里的 WiFi 或 WebSocket 指标明确退化。

## 1. 现象

在 `wifi` 工程中启用 `WHD + FAL` 后，常见报错有：

```text
Read resource head error for partition[whd_firmware]
whd_bus_sdio_download_resource: TRX header mismatch
Read resource head error for partition[whd_clm]
ERROR: WLAN: could not download clm_blob file
```

最终表现为：

```text
[E/whd.wlan] Unable to start the WiFi module!
```

## 2. 根因总结

这次问题最终确认有 3 个根因：

1. `WHD` 资源分区一开始没有预烧录内容。
2. 资源打包头最初写成了 `12` 字节，但官方 `resource_hnd_t` 实际是 `16` 字节。
3. `whd_clm` 和 `whd_nvram` 位于同一个 `256KB` 擦除扇区，分开烧录会互相擦掉。

## 3. 正确配置思路

### 3.1 WHD 资源方式

`wifi` 工程要使用：

- `Flash Abstraction Layer (FAL)`

不要改成：

- `File System`

因为当前工程没有现成 `/sdcard` 挂载点，走 `FS` 会直接找不到资源文件。

### 3.2 分区名称

WHD 资源分区名必须保持：

- `whd_firmware`
- `whd_clm`
- `whd_nvram`

分区表定义见：

- [fal_cfg.h](/D:/RT-ThreadStudio/workspace/wifi/libraries/Common/board/ports/fal/fal_cfg.h)

### 3.3 外部 Flash 基地址

`norflash0` 的实际基地址见：

- [fal_flash_port.c](/D:/RT-ThreadStudio/workspace/wifi/libraries/Common/board/ports/fal/fal_flash_port.c)

关键定义：

```c
#define FLASH_START_ADDRESS 0x60E00000
```

因此资源物理地址为：

- `whd_firmware` -> `0x60E00000`
- `whd_clm` -> `0x60E60000`
- `whd_nvram` -> `0x60E70000`

## 4. 官方资源文件

本工程最终验证通过的资源文件如下：

- Firmware:
  - [55500A1.trxcse](/D:/RT-ThreadStudio/repo/Extract/Board_Support_Packages/Infineon/PSOC_E84-EDGI-TALK/1.1.0/libraries/components/wifi-host-driver/wifi-host-driver/WHD/COMPONENT_WIFI6/resources/firmware/COMPONENT_55500/COMPONENT_SM/55500A1.trxcse)
- CLM:
  - [55500A1.clm_blob](/D:/RT-ThreadStudio/repo/Extract/Board_Support_Packages/Infineon/PSOC_E84-EDGI-TALK/1.1.0/libraries/components/wifi-host-driver/wifi-host-driver/WHD/COMPONENT_WIFI6/resources/clm/COMPONENT_55500/55500A1.clm_blob)
- NVRAM:
  - [cyw55513modpse84som_rev3.txt](/D:/RT-ThreadStudio/repo/Extract/Board_Support_Packages/Infineon/PSOC_E84-EDGI-TALK/1.1.0/resources/cyw55513modpse84som_rev3.txt)

## 5. 资源打包的关键坑

### 5.1 资源头不是 12 字节，而是 16 字节

官方定义见：

- [wiced_resource.h](/D:/RT-ThreadStudio/workspace/wifi/libraries/components/wifi-host-driver/wifi-host-driver/WHD/COMPONENT_WIFI6/resources/resource_imp/wiced_resource.h)

`resource_hnd_t` 的布局是：

- `uint32_t location`
- `uint32_t size`
- `8` 字节 union 存储区

因此总长度是 `16` 字节。

如果错误地按 `12` 字节打包，运行时会出现：

```text
whd_bus_sdio_download_resource: TRX header mismatch
```

因为 `WHD` 读取 `block0` 时会把 `HDR0` 跳过去。

### 5.2 已修正的打包脚本

当前正确脚本：

- [pack_whd_resources.py](/D:/RT-ThreadStudio/workspace/tools/pack_whd_resources.py)

生成结果：

- [whd_firmware.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_firmware.bin)
- [whd_clm.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_clm.bin)
- [whd_nvram.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_nvram.bin)
- [whd_resources_all.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin)

## 6. 烧录方式的关键坑

### 6.1 不要分开烧 `clm` 和 `nvram`

OpenOCD 日志已经证明这片外部 Flash 的擦除粒度是：

```text
Erase sector size: 0x00040000
```

也就是 `256KB`。

而：

- `whd_clm` 在 `0x60000`
- `whd_nvram` 在 `0x70000`

它们落在同一个 `0x40000 ~ 0x7FFFF` 擦除扇区里。

所以如果分开烧：

- 先烧 `clm`
- 再烧 `nvram`

后写入会把前一个擦掉，最后就会报：

```text
Read resource head error for partition[whd_clm]
```

### 6.2 正确做法：一次性烧录合并镜像

不要再使用以下脚本作为最终烧录方案：

- [program_resources_verify.bat](/D:/RT-ThreadStudio/workspace/wifi/program_resources_verify.bat)
- [program_with_resources_split.bat](/D:/RT-ThreadStudio/workspace/wifi/program_with_resources_split.bat)

这两个只适合调试验证。

最终应使用：

- [program_with_resources.bat](/D:/RT-ThreadStudio/workspace/wifi/program_with_resources.bat)

这个脚本会：

1. 烧录 [rtthread.hex](/D:/RT-ThreadStudio/workspace/wifi/Debug/rtthread.hex)
2. 再一次性烧录 [whd_resources_all.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin)

## 7. 调试命令

为了定位这次问题，工程里加了两个 `msh` 调试命令，位于：

- [main.c](/D:/RT-ThreadStudio/workspace/wifi/applications/main.c)

命令如下：

```sh
whd_dump_head
whd_dump_block0
```

用途：

- `whd_dump_head`
  - 直接读取 `whd_firmware` 分区前 32 字节
- `whd_dump_block0`
  - 通过 `WHD` 的 `resource_ops.whd_get_resource_block()` 读取 firmware 第 0 块前 32 字节

最终正确输出中，`whd_dump_block0` 前 4 字节应为：

```text
48 44 52 30
```

也就是：

```text
HDR0
```

## 8. 最终成功标志

启动日志出现以下信息说明修复成功：

```text
WLAN MAC Address
WLAN Firmware
WLAN CLM
wlan init success
eth device init ok
```

## 8.1 2026-06-13 最小 WiFi 扫描 QA 结论

本次在 `wifi` 工程中先关闭/绕开 LVGL、语音、OpenClaw、HTTP 和自动连接，只保留 WiFi 初始化与开机自动扫描 QA。

关键结论：

1. 资源烧录不是当前阻塞点。官方 `Edgi_Talk_M55_WIFI` 和本工程合并资源镜像均已验证资源可用。
2. `FINSH_THREAD_PRIORITY=20` 时，CM55 shell 会在无有效控制台输入时长期占用调度，导致 WHD FreeRTOS 包装线程得不到运行；将 shell 优先级降到 `30` 后，WHD 线程可以运行。
3. 不能用 `rt_wlan_is_ready()` 判断是否可以扫描；它更偏向连接 ready 状态。开机扫描前应等 WHD 初始化阶段到 ready，并确认 `wlan0` 已注册。

## 8.2 2026-06-19 烧录 probe 选择坑

这轮 `program_with_resources.bat` 的真正阻塞点不是固件，而是 probe 选择。

现象：

1. 默认 `openocd.exe ... interface/kitprog3.cfg ...` 会先尝试板载 `KitProg3 CMSIS-DAP`，但在 `Acquisition in Test Mode` 阶段失败。
2. 直接改成通用 `interface/cmsis-dap.cfg` 时，OpenOCD 会落到外接 `Horco CMSIS-DAP v2`，随后报 `CMSIS-DAP command CMD_INFO failed`。
3. 最终确认板载下载器本体是 `USB\\VID_04B4&PID_F155`，父序列号是 `17040F11022F2400`，需要显式锁定它，不能让 OpenOCD 自选。

当前处理：

- `program_with_resources.bat` 已改成在 `kitprog3.cfg` 下显式加 `adapter serial 17040F11022F2400`。
- 这样可以稳定把 `rtthread.hex` 和 `whd_resources_all.bin` 写进去。
- 末尾仍可能看到 `kitprog3: failed to acquire the device`，但这发生在写入完成之后，属于收尾握手告警，不是写入失败。

可复用技巧：

- 同机同时插着板载 `KitProg3` 和外接 `Horco CMSIS-DAP` 时，不要靠自动探测。
- 先用 `Get-PnpDeviceProperty` 查 `DEVPKEY_Device_Parent`，再把板载 probe 的父序列号写进烧录脚本。
- 如果 `cmsis-dap` 走到 `CMD_INFO failed`，优先怀疑 probe 模式/驱动，而不是 hex 或资源文件。

## 8.2 2026-06-15 XiaoZhi WebSocket QA 结论

本轮确认 WiFi 已不是主阻塞点：

- 串口 `m55qa_status` 显示 `saved=1 auto=1`，复位后可自动连回。
- DHCP 正常，实测 `ip=192.168.3.32 gw=192.168.3.1 dns0=192.168.3.1`。
- `wlan=1 ready=1 rssi=-56`。

小智 WebSocket 仍未连通：

- 已将 `applications/websocket_client.c` 从手写 POSIX/lwIP socket 握手改为 lwIP 自带 `wsock_*` callback client 的薄适配层。
- 已打开 `RT_LWIP_USING_WEBSOCKET`，并编入 `src/apps/websocket/websocket_client.c`、`sha-1.c`、`base64-decode.c`。
- 为避免把 TLS/mbedTLS 拉进 M55，已把 lwIP websocket client 里的 TLS 引用改为 `#if LWIP_ALTCP_TLS` 条件编译；当前平台 URL 是明文 `ws://...:8011`。
- M55 构建通过，烧录 M55 hex 和 `whd_resources_all.bin` 均到 100%。
- 串口 QA 仍显示 `xz_ws=0 xz_stage=20 xz_errno=-4`，其中 `-4` 是 lwIP `ERR_RTE`，出现在 `wsock_connect()` / `altcp_connect()` 启动连接阶段。

当前判断：

- 云端 URL/token/path 之前已由 PC raw WebSocket 验证过可返回 `101 Switching Protocols`。
- 同板 WiFi/DHCP 正常，因此当前 blocker 更像 lwIP raw/altcp 路由或默认 netif 上下文问题，而不是 WiFi 扫描/连接问题。
- 下一步应优先在 M55 上诊断 `netif_default`、`ip_route()`、`altcp_connect()` 的输入和返回，或在官方 `wsock_connect_addr()` 前显式绑定可用 WiFi netif/local IP。
4. 当前 porting 层原先的 active scan 后再 passive scan 在本板上不稳定，表现为上层等待 `SCAN_DONE` 超时。临时减枝方案改为 active-only 异步扫描，active 完成即上报 `RT_WLAN_DEV_EVT_SCAN_DONE`。

OpenOCD 内存 QA 成功证据：

```text
g_m55_wifi_scan_qa.magic        = 0x57465141  // "WFQA"
g_m55_wifi_scan_qa.phase        = 4
g_m55_wifi_scan_qa.scan_result  = 0
g_m55_wifi_scan_qa.scan_count   = 6
g_whd_scan_diag_start_calls     = 1
g_whd_scan_diag_start_ret       = 0
g_whd_scan_diag_callback_calls  = 13
g_whd_scan_diag_report_calls    = 12
g_whd_scan_diag_done_calls      = 1
```

当前临时 QA 入口：

- [main.c](/D:/RT-ThreadStudio/workspace/wifi/applications/main.c): `M55_WIFI_SCAN_QA_ONLY`
- [whd_wlan.c](/D:/RT-ThreadStudio/workspace/wifi/libraries/components/wifi-host-driver/porting/src/wlan/whd_wlan.c): active-only scan 与 `g_whd_scan_diag_*`

后续重新引入功能时，建议顺序为：

1. 保持 active-only scan，移除 QA-only 后只恢复正常 WiFi 配网服务。
2. 再恢复保存配置/自动连接。
3. 再恢复 LVGL 配网界面。
4. 最后恢复语音、OpenClaw、HTTP/WebSocket 等重负载模块。

## 9. M55 DEEPCRAFT 唤醒词与外部 RSRAM

### 9.1 M55 唤醒词模型必须放到 secondary/RSRAM

官方 DEEPCRAFT `AM_LSTM` 唤醒模型和工作缓冲较大，不能全部放进 M55 内部 `m55_data_INTERNAL`。如果链接时报：

```text
rtthread.elf section `.bss' will not fit in region `m55_data_INTERNAL'
region `m55_data_INTERNAL' overflowed
```

处理方式：

1. `applications/ifx_deepcraft/SConscript` 中定义 `CY_ML_MODEL_MEM=.cy_socmem_data`。
2. `Smart_Lights_Demo_config.c` 中的 `am_tensor_arena`、`data_feed_int`、`mtb_ml_input_buffer`、`xIn`、`features`、`output_scores` 都放入 `.cy_socmem_data`。
3. `board/linker_scripts/link.ld` 已将 `.cy_socmem_data` 映射到 `m55_data_secondary`，即外部/secondary RAM 区。

本次验证的成功构建产物：

```text
D:\RT-ThreadStudio\workspace\wifi\Debug\rtthread.hex
text=790760 data=246544 bss=1647468
```

### 9.2 只保留 WW-only，不要回到旧失败唤醒路径

主线唤醒入口是：

```text
voice_service -> xiaozhi_wake_engine -> ifx_deepcraft_wake_adapter -> mtb_wwd
```

不要把 `wake_word_detector.cpp` / `model_deployment.c` 的旧本地测试模型重新接回主线。它们只适合作为旧 demo/调试材料，不是当前小智唤醒词主线。

当前官方示例唤醒词仍是：

```text
OK Infineon
```

后续如果要换成“你好小智”，需要重新训练/导出官方 DEEPCRAFT 兼容唤醒词模型，而不是改字符串。

### 9.3 烧录后不要用 M33 串口命令误判 M55

`COM26` 是 KitProg3 USB-UART，但当前 shell 可能属于 M33。烧 M55 后，在该 shell 输入：

```text
wake_on
```

如果返回：

```text
wake_on: command not found.
```

这只能说明当前交互 shell 不是 M55 shell，不能说明 CM55 没跑。正确确认 CM55 是否运行：

```bat
cd /d D:\RT-ThreadStudio\repo\Extract\Debugger_Support_Packages\Infineon\OpenOCD-Infineon\2.0.0\bin
openocd.exe -s ../scripts -s ../flm/cypress/cat1d -f interface/kitprog3.cfg -f target/infineon/pse84xgxs2.cfg -c "init; targets cat1d.cm55; halt; reg pc; reg msp; resume; shutdown"
```

本次验证结果：

```text
pc (/32): 0x6059f636
msp (/32): 0x2003ff88
```

`pc` 落在 M55 镜像区间 `0x6058xxxx`，说明 CM55 已经从刚烧录的 M55 镜像运行。

本次实际成功日志为：

```text
[1300] WLAN MAC Address : 9C:C7:D3:E1:B8:40
[1301] WLAN Firmware    : wl0: Jul 25 2024 08:20:41 version 28.10.301 (aede64b) FWID 01-8cf45cc8
[1302] WLAN CLM         : API: 20.0 Data: IFX.5551x Compiler: 1.49.5 ClmImport: 1.48.0 Customization: v2 24/06/28 Creation: 2024-07-02 03:05:22
[1325] Disabled scanmac randomisation for 55500
[I/WLAN.dev] wlan init success
[I/WLAN.lwip] eth device init ok name:w0
[I/WLAN.dev] wlan init success
[I/WLAN.lwip] eth device init ok name:w1
```

## 9. 后续联网测试

WiFi 初始化成功后，可在 `msh` 中按以下顺序测试：

```sh
ifconfig
wifi scan
wifi join <SSID> <PASSWORD>
ifconfig
ping 8.8.8.8
ping www.baidu.com
```

## 10. 一句话结论

这次问题不是 `LVGL` 占 Flash，也不是 `WHD` 驱动本身坏了，而是：

- 资源没有预烧录
- 资源头格式最初打错
- 外部 Flash 擦除粒度导致分开烧录互相覆盖

最终正确方案是：

- `WHD resources = FAL`
- 使用修正后的 `16` 字节资源头
- 使用 [whd_resources_all.bin](/D:/RT-ThreadStudio/workspace/wifi_resources/whd_resources_all.bin) 一次性整体烧录

## 11. LVGL 配网页扫描为空的排查顺序

LCD 配网页的目标是让用户不用命令行完成配网；命令行只保留给开发诊断。若点击“扫描”后列表为空，不要直接判断是界面坏了，按下面顺序看：

1. 先确认当前交互 shell 是 M55，不是 M33。M55 启动日志应出现 `This core is cortex-m55`，并且 WiFi 成功时应出现 `WLAN MAC Address`、`WLAN Firmware`、`WLAN CLM`、`wlan init success`。
2. 在配网页点“诊断”，看 `WHD stage/result`。如果 WHD 没到 ready，先回到资源烧录、SDIO、固件下载问题，不要调 UI。
3. 看扫描诊断字段：`cb` 是收到的 AP report 数，`done` 是扫描完成事件数，`timeout` 是等待扫描完成超时次数。
   - `cb=0 done=0 timeout>0`：底层扫描没有完成，优先查 WHD/SDIO/中断/事件。
   - `cb=0 done>0 timeout=0`：扫描确实完成但没看到 AP，优先确认路由器是 2.4G/5G 可见、距离、信道和国家码。
   - `cb>0 count=0`：缓存逻辑异常或隐藏 SSID 被过滤。
4. 新版 `wifi_config_scan()` 已经改为等待 `RT_WLAN_EVT_SCAN_DONE`，AP 回调会在等待期间持续缓存到 LVGL 列表。不要再用“刚点扫描立刻读取 0 个 AP”判断扫描失败。

常用现场命令：

```sh
m55_wifi_diag
m55_wifi_scan
# 等 3-5 秒
m55_wifi_aps
m55_wifi_status
```

## 12. 2026-06-11 LVGL 摄像头 QA 结论

本轮为了在 M55 串口不可用时继续 QA，使用 NanoPi 摄像头直拍英飞凌 LCD：

```sh
ssh pi@192.168.2.66
sudo insmod /usr/lib/modules/6.1.141.can-new/kernel/drivers/media/usb/uvc/uvcvideo.ko
v4l2-ctl -d /dev/video45 -c auto_exposure=1,exposure_time_absolute=90,brightness=-10,contrast=65,backlight_compensation=0,sharpness=7
ffmpeg -hide_banner -loglevel error -f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video45 -frames:v 1 -y /tmp/ifx_diag_xy.jpg
```

为了让摄像头可读，LVGL 配网页底部增加黑底白字大号 QA 短码：

```text
R0 N0 C0 D0 T0
S1322 E02000002
X6c Y02
```

字段含义：

- `R`：`rt_wlan_is_ready()`，当前为 `0`，WiFi 管理层未 ready。
- `N`：scan running，当前为 `0`，扫描没有启动。
- `C/D/T`：scan report / scan done / scan timeout 计数，当前全为 `0`，说明不是扫描 API 或 LVGL 列表缓存问题。
- `S1322`：WHD SDIO BLHS `CHK_BL_INIT` 阶段，主机已写 `SDIO_BLHS_H2D_BL_INIT`。
- `E02000002`：`WHD_TIMEOUT`。
- `X6c Y02`：等待 `SDIO_BLHS_D2H_READY` 时，实际读到 D2H `0x6c`，期望位是 `0x02`。

结论：当前“WiFi 扫描不到”不是最终问题，真正卡点是 CYW55513/CYW55500 SDIO bootloader handshake 未给出期望的 `D2H_READY`。下一步优先查：

1. `BLHS_SUPPORT` 是否适用于当前 CYW55513 模组和固件资源组合。
2. `COMPONENT_55500/COMPONENT_55500A1`、`CYW55513IUBG`、NVRAM、CLM、firmware 是否严格匹配板卡。
3. `m55_sdio_kick_change()`、SDIO reset/power 时序、BT 共享启动窗口是否让 WiFi bootloader 进入异常状态。
4. 若仍只能靠摄像头 QA，保留黑底短码，不要改回小字诊断。

## 13. 2026-06-13 官方资料回查与下一轮上电测试

本轮用户明确要求先不要再猜、不要先做 LVGL；板子当前未上电，因此只做官方资料和本地源码对照，不做烧录/复位。

已确认的官方/原始基线：

1. Infineon WHD 官方仓库说明 WHD 是 Infineon WLAN 芯片的嵌入式 Wi-Fi Host Driver，Wi-Fi 6 `55500` 支持 `SDIO`。
2. Infineon `mtb-example-psoc-edge-wifi-web-server` 官方例程说明 PSOC Edge + AIROC `CYW55513` 可通过 `SoftAP + STA` 并发模式做 Web 配网；这说明后续 LCD/LVGL 配网方向成立，但必须等 WHD 初始化和扫描先跑通。
3. 本地 BSP `libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/bsp.mk` 明确：
   - `BSP_COMPONENTS` 包含 `WIFI_INTERFACE_SDIO`、`CYW55513_MOD_PSE84_SOM`。
   - `MPN_LIST` 包含 `CYW55513IUBG`。
   - `DEVICE_COMPONENTS` 为 `55500 55500A1 PSE84`。
   - `DEVICE_CYW55513IUBG_DIE` 为 `55500A1`。
   - `DEVICE_DEFINES` 为 `BLHS_SUPPORT TRXV5`。
4. 本地官方 `projects/Edgi_Talk_M55_WIFI` 例程 README 明确该例程用于 M55 上验证 Wi-Fi scanning、connection、iperf，运行路径也是先 `wifi scan` 再 `wifi join`。
5. 当前工程的 `board/SConscript` 与 `Edgi_Talk_M55_WIFI/board/SConscript` 的关键宏一致，包含 `BLHS_SUPPORT`、`COMPONENT_55500`、`COMPONENT_55500A1`、`COMPONENT_SM`、`TRXV5`。
6. 当前工程 `rtconfig.h/.config` 与 `Edgi_Talk_M55_WIFI` 的关键配置一致：`RT_SDIO_STACK_SIZE=2048`、`RT_SDIO_THREAD_PRIORITY=0`、`BSP_USING_SDIO0`、`WHD_RESOURCES_IN_EXTERNAL_STORAGE_FAL`、`WHD_USING_CHIP_CYW55500`、`WHD_USING_WIFI6`、`CY_WIFI_WHD_THREAD_STACK_SIZE=5120`。

本轮已回正的实验改动：

1. `WHD/COMPONENT_WIFI6/src/whd_chip_constants.c`
   - 恢复官方 BSP 的 55500/TRXV5 RAM 常量：
     - `CHIP_RAM_SIZE = 0xE0000 - 0x20 - 0x1000`
     - `ATCM_RAM_BASE_ADDRESS = 0x3a0000 + 0x20 + 0x1000`
   - 原先把 `0x1000` 偏移去掉属于行为改动，且和官方 BSP 不一致。
2. `WHD/COMPONENT_WIFI6/src/bus_protocols/whd_bus_sdio_protocol.c`
   - `CHK_BL_INIT` 恢复严格等待 `SDIO_BLHS_D2H_READY`。
   - 不再接受 `TRXHDR_PARSE_DONE/VALDN_RESULT/VALDN_DONE` 作为 ready 替代；`0x6c` 应作为异常证据保留，而不是越过官方状态机。
   - 写 reset vector 后恢复官方错误语义：读回失败或值不一致不能强行改成成功。
3. 诊断埋点仍保留，用于下一次上电后读 `g_whd_diag_*` 判断卡点。

本轮编译验证：

```text
scons -j4
text=1278972 data=81488 bss=4534732
build OK
```

下一次板子上电后的最小验证顺序：

1. 烧录当前构建和合并后的 WHD 资源：
   - 使用 `program_with_resources.bat`。
   - 注意 OpenOCD 退出时可能仍有 KitProg3 acquire 报错，先看是否写入了主程序和资源镜像，不要只看退出码。
2. 复位后先等 20-30 秒，不要先点 LVGL 扫描。
3. 用 OpenOCD 读取诊断全局：
   - `g_whd_diag_extra0 = 0x2001b734`
   - `g_whd_diag_extra1 = 0x2001b738`
   - `g_whd_diag_flags  = 0x2001b73c`
   - `g_whd_diag_result = 0x2001b740`
   - `g_whd_diag_stage  = 0x2001b744`
4. 如果仍是 `S1322 E02000002 X6c Y02`：
   - 说明官方严格 BLHS 下还是等不到 `READY`，优先查 Wi-Fi 芯片 reset/power/SDIO bootloader 入口时序，而不是扫描 API 或 LVGL。
5. 如果通过 WHD init 并出现 `WLAN MAC Address / WLAN Firmware / WLAN CLM / wlan init success`：
   - 再运行 `m55_wifi_scan` 或 `wifi scan`。
   - 等 3-5 秒后运行 `m55_wifi_aps`。
   - 此时才回到 LVGL 配网页列表刷新和触摸交互。

## 14. 2026-06-13 WiFi + LVGL 触屏配网里程碑

本轮确认 WiFi 扫描与 LVGL 配网页已经从底层阻塞推进到可用交互阶段，是后续“小智连接服务器平台 / OpenClaw 工具调用 / M55 网络服务”的前置里程碑。

已完成：

1. WiFi 扫描链路打通：
   - `whd_wlan.c` 增加扫描诊断计数。
   - 现场曾读到 `scan_result=0`、`scan_count=6`，后续 LVGL 场景下也读到 WHD scan callback/report/done 计数增长，说明资源烧录、WHD 初始化和扫描回调已通。
   - 当前应继续使用 `program_with_resources.bat` 同时烧录主固件和 `whd_resources_all.bin`，不要只烧 `rtthread.hex`。
2. LVGL 配网页上线：
   - `applications/rehab_wifi_panel.c` 提供触屏扫描、选择 SSID、输入密码、保存、连接、断开、清除和诊断入口。
   - 默认隐藏黑底诊断覆盖层，诊断只作为开发按钮打开。
   - 配网页启动后会自动发起一次扫描，用户不再需要进命令行 `msh` 配网。
3. 触屏输入体验修复：
   - 自定义键盘的 `Del` 不再插入字符串 `Del`，而是执行删除。
   - 避免使用当前字体缺失的 LVGL 图标符号，减少方框字。
   - 重新压缩顶部状态文案、放大网络列表、整理按钮布局，减少互相覆盖。
4. 构建脚本补强：
   - `applications/SConscript` 显式加入 LVGL `env_support/rt-thread` include path。
   - `libraries/Common/board/SConscript` 显式补齐 LVGL port 编译所需的 `src` 下头文件路径，避免干净 worktree 中出现私有头找不到的问题。

本轮验证：

```text
D:\RT-ThreadStudio\workspace\wifi
scons -j4
build OK
text=1160736 data=17396 bss=4525076

program_with_resources.bat
rtthread.hex 写入成功
whd_resources_all.bin 写入成功

OpenOCD reset run
reset command issued
```

注意事项：

- OpenOCD/KitProg3 在写入或 reset 后仍可能打印 `failed to acquire the device`，但只要日志已经显示 `wrote ... rtthread.hex` 和 `wrote ... whd_resources_all.bin`，先不要把它等同于资源未烧录。
- 临时 M55 Git worktree 全量重建时曾因旧分支缺少 LVGL include path 失败；补齐路径后继续全量重建会卡在长时间 C++/LVGL 编译阶段，本地 `workspace\wifi` 主工作区构建和实机烧录已验证。
- WiFi 列表滚动曾怀疑会被刷新打回顶部，现场复查确认可以下拉，暂不改刷新逻辑。

下一步：

1. 继续用触屏配网页完成真实路由器连接，确认拿到 IP。
2. 在 M55 上恢复/验证小智连接服务器平台所需的网络客户端或 HTTP/WebSocket 路径。
3. WiFi 稳定后再恢复语音、小智唤醒和 OpenClaw/OpenAI 类服务，不要在 WiFi 未连通时同时调多条链路。

## 15. 2026-06-13 WiFi 优先与小智延后连接策略

现场现象：

- WiFi/LVGL 已能完成真实连接，但在加入“小智自动连接”后，配网阶段一度出现连接卡住或用户体验退化。
- M33 串口 shell 当前不稳定，`m55qa_status` 无法稳定返回，因此不能把 WiFi 配网页依赖在命令行控制链路上。

本轮结论：

1. WiFi 配网优先级最高。M55 启动后不得在 WiFi 未 ready、未拿到 IP 前启动 voice/mic/WebSocket。
2. 小智连接应是“网络稳定后的后置动作”：
   - 先等 `wlan_ready != 0` 且 `netdev_ip != 0`。
   - 连续多次确认 ready 后，再启动 wake listening 和 XiaoZhi WebSocket reconnect。
   - reconnect 失败只记录并延后重试，不能阻塞 LVGL 配网 UI。
3. 平台 token 只允许通过本地忽略文件或现场注入使用，不能提交进仓库或文档。

已落地：

- `main.c` 增加 `M55_XIAOZHI_AUTO_ENABLE`，当前策略是启用安全版自动连接，但自动线程先等 WiFi/IP 稳定，再启动小智。
- `voice_service_init()` 的首次 WebSocket 连接失败改为 deferred，不再导致整个 voice service 初始化失败；后续由 reconnect 路径在网络 ready 后处理。
- 本轮 M55 `scons -j4` 构建通过，并已用 `program_with_resources.bat` 烧入一次。

后续验证顺序：

1. 复位后先通过 LVGL 连 WiFi，确认屏幕显示已连接。
2. 等 10-20 秒观察是否有小智连接日志或平台侧连接事件。
3. 如果 M33 shell 恢复，再用 `m55qa_status` 看 `xz_token=1`、`xz_ws=1`、`wlan=1`、`ip!=0.0.0.0`。
4. 如果串口仍无响应，不要反复发命令；优先恢复 M33 shell 或用摄像头/平台侧日志做 QA。

## 16. 2026-06-13 对齐官方小智 WebSocket 例程

官方参考：

- 本地官方参考仓库：`D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32`
- 关键文件：
  - `docs/websocket.md`
  - `main/protocols/websocket_protocol.cc`
  - `main/protocols/protocol.cc`

官方协议要点：

1. WebSocket 握手 header：
   - `Authorization: Bearer <token>`
   - `Protocol-Version: 1`
   - `Device-Id`
   - `Client-Id`
2. 设备 hello：
   - `type=hello`
   - `version=1`
   - `transport=websocket`
   - `features.mcp=true`
   - `audio_params.format=opus`
   - `sample_rate=16000`
   - `channels=1`
   - `frame_duration=60`
3. 听音控制：
   - `{"type":"listen","state":"start","mode":"auto"}`
   - stop 使用 `{"type":"listen","state":"stop"}`
   - wake detect 使用 `{"type":"listen","state":"detect","text":"..."}`。

本轮修正：

- M55 `xiaozhi_voice_relay` 已从自定义 `version=3 + pcm_s16le + 20ms + mode=auto_stop` 改为官方例程形态 `version=1 + opus + 60ms + mode=auto`。
- PC smoke 脚本 `tools/xiaozhi_ws_smoke_test.ps1` 同步为官方 hello/listen 格式。
- 已用本地 token 在 PC 端验证官方 hello/listen 可被中转站接受：
  - `hello` 返回 `transport=websocket`、`audio_params.format=opus`、`frame_duration=60`。
  - `listen start mode=auto` 返回 ACK。
  - 发送 60ms 二进制帧并 stop 后，中转站返回 chat/VLA 分类回复。

仍需注意：

- 当前 M55 端还没有真正引入 Opus 编码器；本轮先把协议 JSON 和时序对齐官方例程。
- 当前中转站对 60ms 二进制帧已能给出回复，但后续要做到完全官方一致，应补 M55 Opus encoder 或让中转站明确兼容 PCM-to-ASR 转码边界。
- 不要在 WiFi 未 ready 前启动小智；官方协议对齐不能牺牲 LVGL 配网稳定性。

## 17. 2026-06-13 LVGL 配网页状态显示优化

现场照片反馈：

- WiFi 已能连接并显示扫描数量，但顶部状态区过挤，小智连接状态不够明显。
- 底部“诊断”按钮出现方框字，说明当前 `rehab_wifi_font` 并未覆盖所有中文 glyph 或按钮区域显示不稳定。

本轮修正：

1. WiFi 状态 label 只保留两行：连接状态/扫描数量 + 操作提示。
2. 小智状态拆成独立浅蓝状态条，固定显示 `XiaoZhi: <state> S:<stage> E:<errno>`，便于不用串口也能看 WebSocket 阶段。
3. 诊断按钮改为 `INFO/HIDE`，诊断面板默认文案改为 ASCII，避开字库缺字导致的方框字。

验证：

- `python -m SCons -j4` 构建通过。
- 本轮仅改 UI 显示，不改 WiFi 扫描、连接、自动连接和资源烧录流程。

## 18. 2026-06-13 LVGL 竖屏布局二次压缩与小智阶段显示

现场照片反馈：

- WiFi 列表、输入框、自动连接和两排按钮在 480x640 竖屏上仍然互相挤压。
- 小智状态只显示“连接中”，不足以判断是 DNS、TCP、WebSocket 握手还是自动线程未启动。

本轮修正：

1. AP 列表高度从 `188` 压到 `136`，SSID/密码输入框从 `46` 压到 `40`，给底部按钮区腾空间。
2. 6 个主按钮改为 `2 x 3` 紧凑网格，每个按钮 `198 x 42`，避免和“自动连接”复选框互相遮挡。
3. 小智状态按 WebSocket stage/errno 显示为 `等待启动/解析中/建Socket/TCP连接/握手中/DNS失败/TCP失败/握手失败/已连接` 等更具体状态。

验证：

- `python -m SCons -j4` 构建通过。
- 已用 `program_with_resources.bat` 烧录，应用和资源 programming 均到 100%；末尾 KitProg3 acquire error 仍为既有现象。

## 19. 2026-06-13 补齐 LVGL 配网页中文字库

现场问题：

- “诊断/隐藏”等按钮曾出现方框字，根因是 `rehab_wifi_font.c` 的 symbols 列表缺少 `诊`、`隐`、`藏` 等 glyph。
- 之前临时用 `INFO/HIDE` 绕开缺字，但这会让中文触屏界面体验变差。

本轮修正：

1. 使用 `lv_font_conv 1.5.3` 从 `C:\Windows\Fonts\Noto Sans SC (TrueType).otf` 重新生成 `applications/rehab_wifi_font.c`。
2. 扩展 symbols，覆盖配网页和小智状态常用字：`诊断隐藏未配置等待解析建握手接收线程启动选择输入检查扫码二维码启用发送小智` 等。
3. 将按钮和诊断面板文案恢复为中文：`诊断/隐藏`、`诊断等待刷新`。

验证：

- `python -m SCons -j4` 构建通过。
- 已用 `program_with_resources.bat` 烧录，应用和资源 programming 均到 100%；末尾 KitProg3 acquire error 仍为既有现象。

## 20. 2026-06-13 按源码实际中文集合补齐 LVGL 字库

现场问题：

- 在继续做小智真实状态面板后，固定 UI 文案新增了 `在线待唤醒/正在思考/正在回答/准备语音回复/说唤醒词，我会回应你` 等中文。
- 手写 symbols 容易继续漏字，导致同一类“方框字”反复出现。

本轮修正：

1. 从 `applications/rehab_wifi_panel.c`、`applications/xiaozhi_ui_state.c`、`applications/voice_service.c`、`applications/wifi_config_service.c` 自动提取固定 UI/状态文案里的中文字符。
2. 用提取出的 109 个不同中文字符和标点重新生成 `applications/rehab_wifi_font.c`。
3. 保留 `#include "lvgl.h"`，避免 `lv_font_conv` 默认生成的 `lvgl/lvgl.h` 路径在当前工程里编译失败。

验证：

- `python -m SCons -j4` 构建通过，固件尺寸约 `text=1227156 data=81428 bss=4528904`。
- 已用 `program_with_resources.bat` 烧录，M55 应用写入 `1310720 bytes`，WHD 资源写入 `466944 bytes`，两段 programming 均到 100%；末尾 KitProg3 acquire error 仍为既有现象。

边界：

- 这只覆盖固定 UI 文案。小智模型回复是任意中文，不能靠静态小字库完整覆盖所有汉字；后续若要完整显示长中文回复，应考虑外部字库/更大字库/回复摘要显示。官方小智主路径仍应以语音回复为主。

## 21. 2026-06-13 小智动态回复缺字兜底

### 现象

- 固定 UI 文案补齐后，小智平台动态回复仍可能出现方框字。
- 根因是模型回复不是固定集合，109 个源码抽取字无法覆盖任意聊天文本。

### 当前处理

1. `rehab_wifi_font` 保留源码抽取字库，同时把 `.fallback` 接到 LVGL 已启用的 `lv_font_simsun_16_cjk`。
2. `xiaozhi_ui_state` 保存动态回复时按 UTF-8 边界截断，避免 160 字节缓冲区切断半个汉字后造成乱码/方框。
3. 这样固定 UI 优先使用 18px Noto Sans SC，动态回复缺字时尽量回退到内置 CJK 字体。

### 后续取舍

- 如果要“任意中文长回复完全不缺字”，需要外置/完整中文字库或更大的生成字库，flash/text 体积会继续增加。
- 当前策略优先保证小智状态、短回复、唤醒/思考/回答流程可读，并给后续小模型保留资源。

## 22. 2026-06-13 小智音频协议先按 PCM 兼容

### 现状

- 官方参考例程的 WebSocket 二进制音频是 Opus。
- 当前 M55/M33 这条链路暂时没有完整 Opus 编解码闭环。

### 当前取舍

1. M55 `hello` 先上报 `pcm_s16le`，不再假装是 Opus。
2. 这样平台中转站如果按 PCM 处理，就能先把“说话 -> 平台 -> 回答”打通。
3. 后续如果要严格回官方 Opus，再补完整编解码，而不是继续让协议字段和实际数据打架。

## 23. 2026-06-15 小智连接当前卡在 WebSocket 传输层，不是 WiFi

现场结论：

1. WiFi 自动连接已稳定，复位后 `m55qa_status` 可见 `saved=1 auto=1 storage=0`、`wlan=1 ready=1`、`ip=192.168.3.32`。
2. CM55 独立 TCP 探针可以连到 `106.55.62.122:8011`，说明 WiFi、DHCP、网关、基础 TCP 都不是当前主因。
3. PC 侧使用同一个 URL 和 scoped token 做原始 WebSocket Upgrade，可以拿到 `HTTP/1.1 101 Switching Protocols`，说明平台 token、路径和云端服务有效。
4. CM55 手写 socket WebSocket 客户端已经能走到握手接收阶段，但 `recv` 在当前 RT-Thread/lwIP socket 路径上会阻塞；`select()`、`fcntl(O_NONBLOCK)`、`MSG_DONTWAIT`、`SO_RCVTIMEO`、`FIONBIO`、直调 `lwip_recv` 都不够可靠。

下一步建议：

- 不要继续把小智问题回退到 WiFi 扫描/资源固件方向。
- 改走 BSP 自带的 lwIP callback WebSocket 客户端：启用 `RT_LWIP_USING_WEBSOCKET`，把 `rt-thread/components/net/lwip/lwip-2.1.2/src/apps/websocket/*.c` 编进来，再用 `lwip/apps/websocket_client.h` 的 `wsock_connect/wsock_write` 包住现有 `applications/websocket_client.h` API。
- 只有当 `m55qa_status` 显示 `xz_ws=1` 后，再继续唤醒词、PCM/Opus、扬声器回复闭环。

## 24. 2026-06-15 WebSocket 已连通，当前阻塞转为音频格式/ASR

现场结论：

1. M55 编译通过并烧录后，WiFi 自动连接稳定：`saved=1 auto=1`、`wlan=1 ready=1`、`ip=192.168.3.32`。
2. 小智 WebSocket 已能连上：`xz_ws=1 xz_stage=70 xz_errno=0`。
3. `m55qa_capture_on` 已能触发 M55 麦克风采集，`m55qa_capture_off` 后可见上行统计，例如 `frames=2326 pcm_seq=2326 probe_lwip=387/744588`。
4. 目前没有收到 `stt/llm/tts` 或二进制语音回复；`probe_posix=0/2` 只证明收到过握手/控制文本。

本轮修正：

1. M55 WebSocket header 和 hello 已统一为协议 v3：
   - `Protocol-Version: 3`
   - `hello.version=3`
   - binary 使用 `[type=0,reserved=0,payload_size_be16,payload]`
2. M55 `audio_params.format` 改为 `pcm_s16le`，因为当前真实 payload 是 16 kHz mono S16LE PCM，不再声明成 Opus。
3. `WSMSG_MAXSIZE` 保持 `4096`，避免 60ms PCM 帧加 v3 头超过原来的 1420 限制。

仍需注意：

- 官方小智 ESP32 例程主路径是 Opus 编解码；当前 M55 还没有 Opus encoder，M33 也还没有 Opus decode->speaker 闭环。
- PC 侧 `ClientWebSocket` 探针证明平台 hello 可以接受并回显 `pcm_s16le`，但这不等于平台 ASR 后端已经处理 PCM。
- 下一步不要再回头查 WiFi 扫描/密码。应看平台 relay 日志确认 PCM 是否进入 ASR；若没有，就在 relay 侧做 PCM->ASR/Opus 转码，或在 M55/M33 补小型 Opus 编解码。

补充验证：

- 用户不在现场时，现场麦克风可能只有杂音/静音，不能单靠板端无回复判定 PCM 不通。
- 已用 Windows 语音合成生成清晰的 `16 kHz / mono / 16-bit` WAV，再把 PCM 按 v3 WebSocket 包发送到同一平台。
- 结果仍然只收到 `listen start/stop`，没有 `stt/llm/tts`。这基本说明当前平台 relay 还没有把 `pcm_s16le` 二进制帧送入 ASR。
- 继续方向应优先改 relay 侧 PCM ASR/转码，或回到官方 Opus 路线；不要再把时间花在现场杂音、WiFi、LVGL 上。

后续复测：

- relay 更新后，同一个 PC 合成语音 PCM 探针已返回完整链路：`stt -> llm -> chat -> tts start/stop`。
- 这说明平台侧 `pcm_s16le` 兼容分支已经能进 ASR；后续仍需保留“官方 Opus 是长期主路径”的边界。
- 板端复位后 M55 IPC 恢复，`m55qa_xz_reconnect` 返回 `cmd=1003 result=0`，`xz_ws=1 xz_stage=70`。
- 板端再次 `capture_on/off` 后可见 `probe_lwip=386/742664`，说明 M55 采集和上行仍正常。
- 因为现场没人说话，本轮板端无 STT 不能判为失败；需要有人靠近板端麦克风说清晰提示词再验收。

## 25. 2026-06-15 小智交互与 M33 扬声器链路进展

本轮目标：

- 用户说唤醒词后自动开始录音。
- 录音时 LVGL 显示录音状态，长时间低声/静音后自动停止录音并切到“正在思考”。
- 回答不再占用 LVGL 大面积文本，优先走扬声器。

本轮修正：

1. M55 `voice_service.c` 增加自动 EOU 判断：
   - 最短录音约 `900 ms`。
   - 静音约 `1400 ms` 后自动 `listen stop`。
   - 最长录音约 `12000 ms` 防止一直录。
   - 停止后 UI 切到 `XIAOZHI_UI_THINKING`。
2. LVGL 小智面板改成紧凑状态：
   - `在线待唤醒`
   - `我在听`
   - `正在思考`
   - `正在回答`
   - 模型长回复不再默认显示在屏幕上，避免小屏遮挡和动态中文字库继续膨胀。
3. M33 扬声器方向确认根因：
   - 之前 `[audio_playback] ERROR: Cannot find sound0 device` 不是平台没回 TTS，而是 M33 `drv_i2s.c` 里 `M33_SKIP_SOUND0_INIT_FOR_XIAOZHI_QA` 默认置 `1`，启动时跳过了官方 `rt_hw_sound_init()`。
   - 已改为默认 `0`，恢复 `sound0` 注册。
   - 串口 `audio_playback_probe_cmd` 已验证 `sound0 -> found`。
4. M33 TTS 播放层改为走 RT-Thread 官方 `sound0` audio device：
   - 收到 M55 的 `MSG_TYPE_TTS_AUDIO` 后初始化/启动 `audio_playback`。
   - TTS chunk 当前为 `128 B`，直接写入 `sound0`，不再额外攒二级播放线程缓冲，减少阻塞和 `-RT_EFULL` 风险。
   - 单次底层写入不超过 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`。

烧录注意：

- M55 仍使用 `wifi/program_with_resources.bat`，会同时烧 `rtthread.hex` 和 `whd_resources_all.bin`。
- M33 当前 hex 使用 C-AHB 地址 `0x0834xxxx`，OpenOCD 需要加 `0x58000000` offset 写到 SMIF 物理地址：

```sh
flash write_image erase D:/RT-ThreadStudio/workspace/yiliao_m33/build/rtthread.hex 0x58000000
```

验证结果：

- M55 构建通过。
- M33 构建通过，最新尺寸约 `text=280692 data=16076 bss=310744`。
- M55 烧录时应用写入 `1310720 bytes`，WHD 合并资源写入 `466944 bytes`。
- M33 最新烧录写入 `299008 bytes`。
- 复位后 `m55qa_status`：
  - `saved=1 auto=1 storage=0`
  - `wlan=1 ready=1 ip=192.168.3.32`
  - `xz_ws=1 xz_stage=70 xz_errno=0`
  - `wake_on=1 wake_ready=1`
- M33 串口：
  - `audio_playback_probe_cmd` 返回 `sound0 -> found`

剩余风险：

- `sound0` 已注册并可被 `audio_playback` 找到，但真实平台 TTS 语音是否已经从扬声器完整播出，还需要现场说话触发一次 `stt -> llm -> tts` 后听感确认。
- 官方小智长期路线仍建议补 Opus 编解码；当前为 `pcm_s16le` 兼容路线，优先打通完整闭环。

## 28. 2026-06-16 小智板端 ASR 已打通，剩余集中在 TTS 下行/播放

本轮关键结论：

1. WiFi 不再是当前问题：
   - `m55qa_status` 稳定显示 `saved=1 auto=1`、`wlan=1 ready=1`、`ip=192.168.3.32`。
   - 小智 WebSocket 稳定显示 `xz_ws=1 xz_stage=70 xz_errno=0`。
2. M33 内置干净 PCM 探针已经能走到平台 ASR：
   - `m33qa_xz_probe` 从 M33 共享内存连续发布 4 段 16 kHz mono S16LE PCM。
   - CM55 状态里 `xz_last` 增长，例如 `193/370560`。
   - M33 串口能看到平台 ASR 文本，例如 `asr text: 不知道。`。
3. PC 对照验证平台不是瓶颈：
   - 同一 URL、同一 scoped token、同一 `Protocol-Version: 3`、同一 `pcm_s16le` raw PCM 方式，PC 测试返回完整 `stt -> llm -> chat -> tts start -> binary PCM frames -> tts stop`。
   - 这说明平台中转站的 ASR/LLM/TTS 是通的。

本轮修正：

1. CM55 上行 PCM 不再额外加 4 字节本地 v3 wrapper，直接用 WebSocket binary 发送 raw `pcm_s16le`。
2. M33->M55 IPC 不再被桥接线程吞掉共享 PCM，非控制消息转交 `voice_service_handle_ipc_message()`。
3. 共享 PCM 在 `xiaozhi_listening_active` 时也会被接收，适配 `m55qa_capture_on + m33qa_xz_probe` 这种无人现场 QA。
4. 对非 JSON 的 WebSocket text payload 做保护：
   - 像 PCM 的 payload 走音频路径。
   - 非 JSON 非 PCM 不再发给 M33 当 `TTS_REQUEST`，避免 LCD/串口出现乱码回复。

下一步只盯一个问题：

- 平台已经能返回 TTS binary，但板端还没稳定证明 `CM55 WebSocket callback -> MSG_TYPE_TTS_AUDIO -> M33 audio_playback_write -> sound0` 全链路。
- 后续不要再回退查 WiFi 扫描、密码、WHD 资源；除非 `m55qa_status` 里 `wlan/xz_ws` 明确掉线。

## 26. 2026-06-15 LVGL 字库与小智“思考中”兜底

现场症状：

1. LCD 小智区域会长时间停在“正在思考”。
2. 部分中文显示为方框字。

本轮修正：

1. `applications/xiaozhi_ui_state.c` 增加 UI 状态超时兜底：
   - `XIAOZHI_UI_THINKING` 超过约 `20 s` 未收到平台 TTS/文本回复时，回到 `XIAOZHI_UI_READY`，提示“未收到回复，请重试”。
   - `XIAOZHI_UI_SPEAKING` 超过约 `30 s` 未收到结束事件时，回到 `XIAOZHI_UI_READY`。
2. `applications/rehab_wifi_font.c` 将自定义 18px 字体的 `.fallback` 挂到已启用的 `lv_font_simsun_16_cjk`：
   - 常用 UI 字符仍走小型自定义字体。
   - 自定义字体没覆盖到的中文优先用系统 CJK fallback，避免继续出现大量方框字。
   - 这比把所有动态回复都塞进自定义字体更省 M55 空间。

验证结果：

1. M55 构建通过，最新尺寸约 `text=1407424 data=81508 bss=4528996`。
2. 使用 `program_with_resources.bat` 烧录，应用和 `whd_resources_all.bin` 都写入 100%。
3. 串口 `m55qa_status` 复测到稳定态：
   - `saved=1 auto=1`
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wake_on=1 wake_ready=1`
   - `lvgl_flush` 增加且 `lvgl_last=0`

注意：

- COM4 当前是 M33 shell。M55 内部新增的 finsh 命令不会直接出现在 COM4；板端 M55 状态仍以 M33 侧 `m55qa_status` 的 IPC 快照为准。
- 若复位后短时间看到 `xz_stage=80 xz_errno=-13` 或 `lvgl_flush=0`，先等自动连接/刷新线程恢复，再以第二轮 `m55qa_status` 判断，不要立即回退到 WiFi 扫描问题。

## 27. 2026-06-15 小瑞唤醒与回应语音边界

目标体验：

1. 用户说“小瑞”。
2. LCD/LVGL 切到“我在听”，开始录音。
3. 静音/低音量一段时间后自动停止录音，切到“正在思考”。
4. 平台返回 TTS 音频时，M33 `sound0` 扬声器播放。

本轮修正：

1. M55 唤醒词对外统一为“小瑞”：
   - Edge Impulse 后端内部仍可返回 `xiaorui`。
   - Infineon DEEPCRAFT fallback 不再把用户交互显示成 `Okay Infineon`，而是同样映射到“小瑞”。
2. M55 唤醒后按小智 WebSocket 协议先发送：
   - `listen.detect`，`text` 为“小瑞”。
   - 随后 `listen.start`，`mode` 为 `auto`。
3. 明确撤掉本地算法“人声”作为唤醒回应：
   - 现场听感反馈为杂音，不能作为用户回应。
   - `audio_playback_voice_cmd` 只能用于扬声器通路 QA，不能接入正式唤醒回应。
   - 真正的“我在”或回答音色必须来自小智/平台 TTS 音频，或后续准备经过听感验证的小体积真实提示音资源。

官方依据：

- Espressif 小智组件文档说明小智是双向流式语音/文本组件，支持 WebSocket、MQTT+UDP、OPUS/G.711/PCM，并提供离线唤醒词上报 API。
- 小智 WebSocket 协议文档说明设备侧 `listen` 消息包含 `detect/start/stop`，`detect` 表示本地唤醒检测触发。

验证结果：

1. M55 构建通过，最新尺寸约 `text=1407424 data=81508 bss=4528996`。
2. M33 构建通过，最新尺寸约 `text=286892 data=16076 bss=310744`。

待现场验证：

1. 烧录 M55 后，说“小瑞”，确认 LCD/LVGL 进入“我在听”。
2. 继续问一句清晰问题，确认状态顺序为“在线待唤醒 -> 我在听 -> 正在思考 -> 正在回答/在线待唤醒”。
3. 若平台 TTS 仍无声，优先看是否收到 `tts start/sentence_start/stop` 和 `MSG_TYPE_TTS_AUDIO`，再查 M33 播放链路。

## 28. 2026-06-16 小智官方 Opus/WebSocket v3 二进制帧修正

本轮根因：

1. 小智官方 WebSocket 例程的音频主路径是 Opus，不是裸 PCM。
2. 协议版本 3 的二进制帧也不是裸 Opus，而是：
   - `type=0`
   - `reserved=0`
   - `payload_size` 使用大端 `uint16_t`
   - 后面才是 Opus payload
3. 之前把 `hello.audio_params.format` 改为 `opus` 后，M55 上行仍直接发送 60ms PCM，协议字段和真实 payload 不一致，平台不会把它当有效语音处理。
4. 随后只补 Opus 解码还不够；若下行服务器返回 v3 binary，M55 也必须先剥掉 4 字节 v3 头，再把 payload 交给 Opus decoder。

本轮修正：

1. `applications/xiaozhi_opus_decoder.c/.h` 在原有解码器基础上增加本地 Opus encoder：
   - 16 kHz
   - mono
   - 60 ms / 960 samples
   - `OPUS_APPLICATION_AUDIO`
   - bitrate 约 24 kbps
   - complexity 降为 0，优先保证 M55 实时稳定。
2. `applications/voice_service.c` 上行发送链路改为：
   - 先攒满 60ms PCM。
   - 调用 `xiaozhi_opus_encoder_encode()` 编成 Opus。
   - 发送前补官方 v3 头 `00 00 len_hi len_lo`。
3. `applications/voice_service.c` 下行接收链路改为：
   - 收到 binary 后识别 v3 头。
   - 若头合法，剥掉 4 字节头后再 Opus decode。
   - 解码后的 PCM 再通过 `MSG_TYPE_TTS_AUDIO` 交给 M33 `sound0` 播放。
4. `VOICE_DETECT_THREAD_STACK` 从 16 KB 提到 64 KB：
   - 避免 Opus encode 在 `voice_det` 线程里吃栈导致 M55 voice status 停止刷新。
   - 不在 `voice_service_init()` 里预热 encoder，改为发送时懒初始化，避免启动路径卡死。

验证结果：

1. M55 构建通过：
   - `text=1629104 data=81508 bss=4529020`
2. 使用 `program_with_resources.bat` 烧录通过：
   - M55 `rtthread.hex` 写入约 `1712128 bytes`
   - `whd_resources_all.bin` 写入约 `466944 bytes`
3. 复位后串口 `m55qa_status` 可见稳定态：
   - `saved=1 auto=1`
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wake_on=1 wake_ready=1`
   - `lvgl_flush` 持续增加
4. `m55qa_capture_on/off` 后，M55 不再卡死，状态继续刷新。
5. 上行字节数已从 PCM 量级变成 Opus 量级：
   - 例：`xz_last=153/27387`
   - 这表示 153 帧实际只发送约 27 KB Opus，而不是 153 * 1920B 的裸 PCM。

当前边界：

1. 本轮现场/远程环境没有清晰人声，板端仍只看到 `xz_rx=3/0`，即有 hello/listen 控制文本，但未收到平台 TTS binary。
2. 这不能再判为 WiFi 问题：WiFi、token、websocket、上行 Opus 发送都已经有串口证据。
3. 下一步 QA 应让现场靠近麦克风说清晰问题，或在 PC 侧准备可用的 `opus.dll/ffmpeg` 后，用官方 v3 Opus 包做云端 smoke test。
4. 若清晰语音后仍无 `xz_rx` binary，应优先查平台 relay 的 Opus ASR 日志，而不是回退到 WiFi 扫描或资源固件方向。

## 29. 2026-06-20 小智打通到 M33 扬声器后的当前边界

本轮已确认：

1. 这轮主线按官方小智 WebSocket v1/Opus 走：
   - `Protocol-Version: 1`
   - `hello.version=1`
   - `audio_params.format=opus`
   - 16 kHz / mono / 60 ms
   - WebSocket binary frame 为 raw Opus payload
2. WiFi、token、WebSocket 不是当前主 blocker：
   - `saved=1 auto=1 storage=0`
   - `wlan=1 ready=1`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - token 长度为 `442`
3. 手动 QA 流程已修正为官方手动模式：
   - `m55qa_capture_on` 发 `listen/start`，`mode=manual`
   - `m55qa_capture_off` 发 `listen/stop`，`mode=manual`
4. `VOICE_CTRL_STOP_CAPTURE` 必须先停止 CM55 `mic0`：
   - 否则 shell 可能显示 stop 命令已返回，但后台采集/语音处理还在继续，表现为 LVGL 一直“正在思考”或后续命令 pending。
5. 内置 QA `m33qa_xz_probe` 已经证明平台回包和 M33 播放链路至少通了一次：
   - M55 上行 Opus 例：`xz_last=180/32220`
   - M33 下行日志：`tts audio rx total=320`
   - M33 播放日志：`audio_playback Started`、`tts audio write chunk=...`

当前还没彻底收尾的点：

1. 长 `m33qa_xz_probe` 后再发 `m55qa_capture_off`，仍可能看到 `tx_pending=1`。
2. 这更像是 M33/M55 IPC 在 TTS 回放/status 发布期间的队列压力，不是 WiFi 资源、SSID、密码、token 或基础 WebSocket 连接问题。
3. `m55qa_xz_reconnect ret=0` 只表示异步 reconnect worker 已经排队，不表示已经连接成功；必须继续看 `m55qa_status` 里的 `xz_ws/xz_stage/xz_errno`。

下一步建议：

1. 不要再回到 WiFi 扫描/资源固件方向，除非 `wlan=0` 或 `xz_stage` 明确掉线。
2. 优先把 TTS 回放时的 M55->M33 发布和 M33->M55 stop/control 分流或限流，避免 TTS 下行期间控制消息被 IPC 队列拖住。
3. 真机用户路径仍以 CM55 本地 mic 为主，`m33qa_xz_probe` 是确定性 QA 工具，会比真实 mic 路径更容易压爆 IPC。

## 30. 2026-06-20 小智当前真实进展：官方 M55 mic 路径能 start/stop，TTS 还需限流收尾

本轮结论：

1. 不要再把 WiFi/token 当主 blocker：
   - `saved=1 auto=1 storage=0`
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - `token_len=442`
2. 当前官方主线是 CM55 本地麦克风：
   - `CM55 mic0 -> Opus -> XiaoZhi WebSocket -> platform -> M33 TTS audio`
   - 不是 `M33 PCM -> M55 -> XiaoZhi`。
3. `m33qa_xz_probe` 已经证明平台和扬声器链路有进展：
   - M33 串口出现过 `tts audio rx total=640`
   - `audio_playback Started`
   - `tts audio write chunk=...`
4. 但 `m33qa_xz_probe` 同时会给 IPC/TTS/status 造成很大压力，不能作为产品路径继续硬推。

本轮修改：

1. M55 `m55qa_status` 里的 `probe_or_bridge` 临时承载桥接线程诊断：
   - `loops`
   - `consumed`
   - `last_ret`
   - `phase`
2. `xz_bridge` 栈从 16 KB 提到 32 KB，并增加轻量心跳日志。
3. `voice_svc` 栈从 16 KB 提到 24 KB，`xz_stop` 线程栈从 4 KB 提到 8 KB。
4. `m33qa_xz_probe` 默认缩成约 3 秒短样本，原长样本改为 `m33qa_xz_probe full`。
5. M55 默认忽略 M33 PCM probe 作为 XiaoZhi 上行音频，避免把调试 PCM 流混进官方 mic0 主线。
6. TTS pending 处理从一次 drain 全部改为单包节流，避免语音服务线程长时间忙于下行音频。

验证结果：

1. M55 构建通过：
   - `text=1645224 data=68744 bss=4541560`
2. 烧录通过：
   - M55 `rtthread.hex` 写入 `1716224 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. 复位后 `m55qa_status` 健康：
   - WiFi 自动连接成功
   - token 不需要重新输入
   - WebSocket 已连接
4. 不走 M33 probe 的真实 CM55 mic 控制面通过：
   - `m55qa_capture_on` 得到新 `voice_ack cmd=1 result=0`
   - `m55qa_capture_off` 得到新 `voice_ack cmd=2 result=0`
   - 结束后 `tx_pending=0`

仍未完全解决：

1. 完整自然语音问答和完整扬声器回复还未稳定闭环。
2. TTS 下行期间仍需要继续做 IPC/播放限流，避免状态刷新或控制消息被挤压。
3. 下一步优先做 TTS 下行发布和控制消息分流/限流，不要回退到 WiFi 扫描、token 配置或资源固件方向。

## 31. 2026-06-22 M33 QA probe 已节流，后续不要把 probe 队列压力误判为 WiFi/token

本轮结论：

1. 本轮没有改 M55/WiFi 源码；只修了 M33 QA 工具 `m33qa_xz_probe`。
2. WiFi/token/WebSocket 基线仍然健康：
   - `saved=1 auto=1 storage=0`
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `xz_token=1 token_len=442`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
3. `m33qa_xz_probe` 现在默认 100 ms/帧，遇到 M33->M55 IPC 队列满/超时会 150 ms 退避重试，避免 QA 工具把 `m55qa_capture_off` 挤在队列后面。
4. 这不改变产品路径。产品路径仍然是：
   - `CM55 mic0 -> Opus -> XiaoZhi WebSocket/platform -> M33 speaker`
   - `m33qa_xz_probe` 只是确定性 QA 工具。

验证结果：

1. 1200 ms probe：
   - `m33qa_xz_probe 1200` 发完 20 个 1920B 包，共 `38400` bytes。
   - M33 日志：`retries=0 tx_pending=0`。
   - `m55qa_capture_off` 收到新 `voice_ack cmd=2 result=0`。
2. 3000 ms probe：
   - `m33qa_xz_probe 3000` 发完 50 个 1920B 包，共 `96000` bytes。
   - M33 日志：`retries=0 tx_pending=0`。
   - `m55qa_capture_off` 收到新 `voice_ack cmd=2 result=0`。
   - M33 收到平台下行音频：`tts audio rx total=1280`，并出现 `tts audio write chunk=...`。
   - 最终状态：`tx_pending=0`、`xz_ws=1`、`xz_stage=70`、`xz_errno=0`、`xz_last=183/32757`、`xz_rx=5/0`。

仍需注意：

1. 一次 1200 ms 测试后曾出现 `xz_ws=0 xz_stage=80`，手动 `m55qa_xz_reconnect` 后恢复到 `xz_ws=1 xz_stage=70 xz_errno=0`；后续 3000 ms 测试最终保持连接。
2. 这说明下一层仍要盯 XiaoZhi session stop/reconnect、平台事件和 STT/TTS 解析，不要回头重做 WiFi 扫描、token 或资源固件。
3. 当前状态快照里 `srv_stt/srv_tts` 没增长，但 M33 已收到二进制下行音频；下一步要查平台 event 日志和板端 server event 解析。

推荐下一步：

1. 用真实 CM55 mic0 做人工语音 QA，观察 `server event type=stt/tts/error`、`srv_stt`、`srv_tts`、`xz_rx text/binary`、`tts_fwd` 和 M33 `tts audio rx/write`。
2. 如果 stop 后 WebSocket 再次掉到 `stage=80`，优先修 session stop/reconnect 逻辑。
3. 只有当 `wlan=0`、`token_len=0`、或 `xz_ws=0` 持续不能 reconnect 时，才回到 WiFi/token 方向。

## 32. 2026-06-22 M55 自动重连和 M33 QA ACK 等待已补，不要把控制 ACK 时序误判为平台问题

本轮修改：

1. M55 `voice_service` 线程里的自动重连不再只裸调 `websocket_client_connect()`，而是复用完整 `voice_service_reconnect_xiaozhi()`：
   - 重新配置 XiaoZhi socket/header；
   - 清旧 hello/session/listening 状态；
   - connect 成功后重新发送 hello；
   - 成功/失败都会打印 `websocket auto reconnect... stage/errno`。
2. M33 QA 命令现在会等新 ACK 再返回：
   - `m55qa_probe_pcm_on`
   - `m55qa_capture_on`
   - `m55qa_capture_off`
   - `m55qa_probe_pcm_off`
3. `m33qa_xz_probe` 开始前会等 `tx_pending=0`；如果 M33->M55 控制消息还没被消费，它会等待 drain，而不是继续塞 PCM。

关键复现：

1. M55 重烧后 1200 ms probe 通过：
   - `m33qa_xz_probe 1200` 发 20 包 / `38400` bytes；
   - `capture_off` ACK 成功；
   - M33 收到 320B TTS 下行并写入音频；
   - 最终 `xz_ws=1 xz_stage=70`。
2. M33 ACK 等待修复前，3000 ms probe 暴露出真实 QA 时序问题：
   - `m55qa_capture_on` 没等到新 ACK 就继续发 probe；
   - 第 5 包附近队列满，`tx_pending=5`；
   - `m55qa_capture_off ret=-28`。
3. M33 ACK 等待修复并重烧后，3000 ms probe 通过：
   - `probe_pcm_on` 等到 `cmd=11` ACK；
   - `capture_on` 等到 `cmd=1` ACK；
   - `m33qa_xz_probe 3000` 发完 50 包 / `96000` bytes，`retries=0 tx_pending=0`；
   - `capture_off` 等到 `cmd=2` ACK；
   - 最终 `xz_ws=1 xz_stage=70 xz_errno=0`。

烧录踩坑：

1. M33 不能只用泛 `target/infineon/pse84.cfg` 或少了工程 QSPI 配置的 OpenOCD 命令烧外部 flash。
2. 如果日志出现：
   - `no flash bank found for address 0x60340400`
   - `wrote 0 bytes`
   就是不成功。
3. 正确命令必须先加载：
   - `libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource/qspi_config.cfg`
   - 再加载 `target/infineon/pse84xgxs2.cfg`
   这样 `flash banks` 里才会出现 `cat1d.cm33.smif1_ns`。

后续判断：

1. 如果 QA probe 再出 `ret=-28`，先看是否有新 ACK、`tx_pending` 是否为 0，不要先动 WiFi/token。
2. 如果 stop 后 `xz_ws=0 stage=80`，先看 M55 是否打印 `websocket auto reconnected` 或 `websocket auto reconnect failed`。
3. 下一步仍然是 CM55 mic0 真实人声 QA，以及平台 `stt/tts/error` event 和二进制 TTS 下行解析。

## 33. 2026-06-22 COM4 状态已能看 server event payload 形态

本轮修改：

1. M55->M33 `voice_status_msg_t` 增加紧凑 server event 诊断：
   - `srv_lens=text/content/speak` 长度；
   - `srv_err=error/reason/code` 四字节码，其中第三槽当前保留为 `0`；
   - 原 `srv_last=type/state` 保留。
2. 这些字段只用于观测，不改变 XiaoZhi 协议或音频处理。

验证结果：

1. M55 构建通过并烧录：
   - `rtthread.hex` 写入 `1720320 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
2. M33 构建通过并烧录：
   - `build/rtthread_relocated.hex` 写入 `618496 bytes`
3. 1200 ms QA 通过：
   - `m33qa_xz_probe 1200` 发完 20 包 / `38400` bytes；
   - `capture_off` 等到 `cmd=2` ACK；
   - M33 收到并写入 320B binary TTS：`tts audio rx total=320`、`tts audio write chunk=...`；
   - 最终 `xz_ws=1 xz_stage=70 xz_errno=0`。
4. 新状态字段可见：
   - `srv_last=0x7473696c/0x72617473`
   - `srv_lens=0/0/0`
   - `srv_err=0x00000000/0x00000000/0x00000000`

踩坑：

1. 不能随便扩大 `voice_status_msg_t`。第一次加 6 个 `uint32_t` 后，M33 链接失败：
   - `.cy_sharedmem will not fit in region m33_allocatable_shared`
   - `overflowed by 116 bytes`
2. 这里的结构体会进入 M33/M55 IPC 队列，字段增长会被队列深度放大。
3. 后续需要更多观测字段时，优先打包字段或临时复用诊断槽。

后续判断：

1. 如果 `srv_lens` 仍是 `0/0/0` 但 M33 有 `tts audio rx/write`，说明这次回复走 binary audio，不是 text event 里的 `text/content/speak`。
2. 真实 CM55 mic0 人声 QA 时，同时看：
   - `srv_last`
   - `srv_lens`
   - `srv_err`
   - `xz_rx text/binary`
   - `tts_fwd`
   - M33 `tts audio rx/write`

## 34. 2026-06-22 TTS 转发期间也必须 drain M33 控制消息

现象：

1. QA probe/TTS 已经能打通后，切回真实 CM55 mic0 控制路径时，`probe_pcm_off` 能 ACK。
2. 随后 `m55qa_capture_on` / `m55qa_capture_off` 可能超时，`tx_pending` 停在 `1/2`。
3. 同时 `xz_ws=1 xz_stage=70 token_len=442 wlan=1` 仍然健康，所以不是 WiFi/token 问题。

本轮修复：

1. M55 `voice_service` 在每个 TTS audio chunk publish 前后主动调用 `voice_service_drain_ipc_messages()`。
2. 不扩展 IPC 结构体，复用原状态里的 `probe_or_bridge` 四槽作为：
   - `voice_svc=loop/drain/last_consume_ret/phase`
3. M33 `m55qa_status` 打印标签改为 `voice_svc`，方便判断 M55 语音线程是否还活着。

判断方法：

1. `loop` 应持续增长，说明 M55 voice service 主循环还在跑。
2. `drain` 在 M33 发控制命令后应增长，说明 M55 已消费 M33->M55 队列。
3. `last_consume_ret=-3` 通常只是队列空。
4. 如果 `phase` 卡在 `40/41/42/43`，优先查 TTS 下行队列或 M33 speaker 播放压力，不要回退到 WiFi/token/资源固件方向。

- M55 自动重连成功或失败后会立即发布新的 `voice_status`，所以 COM4 `m55qa_status` 不应再长期停留在恢复前的 `xz_ws=0 stage=80` 快照。
- 验证结果：最终重烧后真实 CM55 mic0 控制 QA 通过，`probe_pcm_off` / `capture_on` / `capture_off` 都 ACK，`tx_pending=0`；停止后等待 12 秒，状态自动恢复到 `xz_ws=1 xz_stage=70 xz_errno=0`。

## 35. 2026-06-22 `capture_on ack=-116` 可能是二次 hello 等待，不是 IPC 队列

现象：

1. `m55qa_status` 显示 `xz_ws=1 xz_stage=70 xz_errno=0 srv_hello=1`。
2. `m55qa_probe_pcm_on` 成功，但紧接着 `m55qa_capture_on` 返回 ACK `result=-116`。
3. `tx_pending=0`，说明 M33->M55 控制 IPC 没有卡住。

修复：

1. `voice_service_start_xiaozhi_talk()` 在等待新 hello 超时后，会检查本次运行是否已经有过 server hello 证据。
2. 如果 WebSocket 仍连接且 `srv_hello` 计数大于 0，则恢复 `hello_seen` 并继续启动 manual listen，避免平台不重复发送 hello 时把 capture 卡死。
3. 冷启动/刚重连时，talk-start 的 hello 等待窗口从 3 秒放宽到 8 秒，避免 WiFi/WebSocket 刚恢复但 server hello 尚未到达时误返回 `-116`。

后续判断：

1. 如果还有 `capture_on ack=-116`，优先看 `srv_hello`、`xz_ws/stage/errno` 和 M55 日志里的 `prior hello evidence`。
2. 只有 `srv_hello=0` 且 hello 等待持续超时，才回头查 WebSocket 握手或平台协议。

## 36. 2026-06-22 QA PCM probe 被消费但 `xz_last=0` 时看 `probe_lwip`

现象：

1. `m33qa_xz_probe 3000` 发完 50 包，`tx_pending=0`。
2. `voice_svc drain` 增长，说明 M55 已消费 M33->M55 IPC。
3. 但 `xz_cur/xz_last` 仍是 `0/0`，平台没有收到上行音频。

修复：

1. M55 现在把 M33 QA PCM accepted/ignored 计数临时发布到 `probe_lwip=accepted/ignored`。
2. `voice_service_accept_shared_pcm()` 在更新共享 PCM 后，会在 `xiaozhi_listening_active` 时立即调用 `voice_service_feed_xiaozhi_listening()`，不再只依赖 wake/detect 线程后续处理。

判断：

1. `probe_lwip` accepted 增长但 `xz_last=0`，继续查 websocket binary send/Opus 编码。
2. `probe_lwip` ignored 增长，说明 capture/listen 状态或 `m55qa_probe_pcm_on` 条件不满足。

验证：

1. 3000 ms QA probe 后 `probe_lwip=50/0`，说明 50 包 M33 QA PCM 全部被 M55 接受。
2. `xz_last=193/34547 xz_fail=0`，说明 Opus/WebSocket 上行已恢复。
3. 当前剩余问题是 `xz_rx=2/0`，只有 text 没有 binary TTS，下层应查平台事件 payload 或协议差异。

## 37. 2026-06-22 `capture_on ack=-116` 也可能是重复 hello 窗口

现象：

1. 冷启动或重烧后，`m55qa_status` 可能先短暂显示 `xz_ws=0 xz_stage=30 srv_hello=0`，随后恢复到 `xz_ws=1 xz_stage=70 srv_hello=1`。
2. 基线健康后，`m55qa_probe_pcm_on` ACK 成功，但 `m55qa_capture_on` 仍可能返回 `ack=-116`。
3. 此时后续 `m33qa_xz_probe` 会被 M55 正确忽略，表现为 `probe_lwip=0/50`、`xz_last=0/0`。这不是 QA PCM 上行坏了，而是 capture 没进入 listening。

本轮修复：

1. `voice_service_start_xiaozhi_talk()` 的 repeated-hello fallback 不再要求超时检查那一瞬间 `websocket_client_is_connected()` 必须为真。
2. 只要本运行已经有 `xiaozhi_server_hello_count > 0`，就恢复 `hello_seen` 并继续；真正发送 `listen/start` 前仍由 manual listen 路径检查 WebSocket 是否连接。
3. M55 server text 诊断继续保持紧凑，不扩大 `voice_status_msg_t`：
   - `srv_err=err/reason raw=... hint=...`
   - `raw` 是最近 text JSON 原始长度；
   - `hint` 是最近 text 的低 16 位事件提示，例如 `he`、`li`。

验证：

1. M55 build 通过：`text=1648280 data=68744 bss=4541600`。
2. M33 QA 打印 build 通过：`text=499072 data=15344 bss=311877`。
3. M55 烧录成功：`rtthread.hex` 写入 `1720320 bytes`，`whd_resources_all.bin` 写入 `466944 bytes`。
4. M33 烧录成功并 verify：`build/rtthread.hex` 写入 `618496 bytes`，verify `616740 bytes`。
5. 最终 3000 ms QA：
   - `capture_on ack=0`
   - `m33qa_xz_probe 3000` 发送 50 包 / `96000` bytes，`retries=0 tx_pending=0`
   - `capture_off ack=0`
   - `probe_lwip=50/0`
   - `xz_last=84/15036 xz_fail=0`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - 最近平台 text 为 `srv_last=list/star raw=57 hint=0x696c`

后续判断：

1. 如果 `capture_on ack=0`、`probe_lwip=50/0`、`xz_last` 增长，但 `srv_stt/srv_tts/tts_fwd` 仍为 0，下一层是小智平台事件/协议差异。
2. 不要把这个模式回退到 WiFi 扫描、token 配置或资源固件方向。

## 38. 2026-06-22 M33 QA PCM probe 期间不要让 CM55 mic0 EOU 抢先 stop

现象：

1. `m55qa_capture_on` ACK 成功，但后续 M33 QA PCM 只有一部分被 M55 接受，最终 `probe_lwip` 可能表现为 `accepted/ignored` 混合。
2. 连续跑 QA 时，如果 capture 实际未进入 listening，`m33qa_xz_probe` 仍继续发布 PCM，会把 M33->M55 IPC 队列塞到 `tx_pending=5`，导致 `capture_off ret=-28`。
3. 当时 WiFi/token/WebSocket 基线仍健康，所以不是凭证或资源固件问题。

根因：

1. QA PCM 是 M33 deterministic PCM，但 M55 同时还在用 CM55 mic0 静音 EOU 监控同一个 XiaoZhi listening session。
2. CM55 mic0 静音帧可能在 M33 QA PCM 注入前或注入中触发 auto EOU，提前发送 `listen/stop`。
3. QA 工具之前只看控制命令返回，没有在发 PCM 前确认 M55 当前仍处于 `xz_listening=1`。

本轮修复：

1. M55 `voice_service_update_xiaozhi_eou()` 在 `m33_pcm_probe_enabled` 为 true 时跳过 CM55 mic0 自动 EOU；QA session 只由显式 `m55qa_capture_off` 结束。
2. M33 `m33qa_xz_probe` 发包前读取最新 M55 `voice_status`，如果没有 `VOICE_STATUS_FLAG_XIAOZHI_LISTENING` 就 abort，不再继续塞 IPC 队列。
3. M55 manual listen start 在最后发送 `listen/start` 前若发现 WebSocket 瞬时断开，会先尝试 reconnect。

验证：

1. M55 build 通过：`text=1648488 data=68744 bss=4541600`。
2. M33 build 通过：`text=499256 data=15344 bss=311877`。
3. M33 烧录成功并 verify：`build/rtthread.hex` 写入 `618496 bytes`，verify `616924 bytes`。
4. M55 烧录成功：`rtthread.hex` 写入 `1720320 bytes`，`whd_resources_all.bin` 写入 `466944 bytes`。
5. 最终 3000 ms QA：
   - `capture_on ack=0`
   - `m33qa_xz_probe 3000` 发送 50 包 / `96000` bytes，`retries=0 tx_pending=0`
   - `capture_off ack=0`
   - `probe_lwip=50/0`
   - `xz_last=81/14499 xz_fail=0`
   - `xz_ws=1 xz_stage=70 xz_errno=0`

后续判断：

1. `probe_lwip=50/0` 且 `xz_last` 增长后，如果 `srv_stt/srv_tts/tts_fwd` 仍为 0，下一步只查小智平台/协议，不要回退到 WiFi/token/资源固件。
2. 连续 QA 前若 `m33qa_xz_probe` 打印 `M55 not listening`，先重新跑 `m55qa_capture_on` 并确认 ACK，不要直接塞 PCM。

## 39. 2026-06-22 人声素材无人 QA 已打通到 M33 播放写入

背景：

1. 用户要求先用人声素材自行 QA，不再依赖现场人工说话。
2. M33 内置 `m33qa_xz_probe full` 已替换为约 5.2 秒、16 kHz mono S16LE 中文人声提示：
   - `你好小智，请用一句话介绍一下你自己。`
   - PCM 长度 `166974` bytes。
3. 本轮没有修改 WiFi/token/资源固件，测试前状态健康：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `xz_token=1 token_len=442`
   - `srv_hello=1`

踩坑：

1. 第一轮 `capture_on` ACK 后等了约 6 秒才发 `m33qa_xz_probe full`，M55 已不在 listening。
2. M33 正确打印 `xiaozhi probe abort: M55 not listening ... xz_ws=1 tx_pending=0`，没有继续塞 IPC。
3. 这类 abort 是 QA 时序问题，不是 WiFi/token 问题。

通过证据：

1. 第二轮把 `m33qa_xz_probe full` 紧跟在 `m55qa_capture_on` 后发送：
   - `capture_on ret=0 ack=0`
   - `m33qa_xz_probe full` 发完 `87` 包 / `166974` bytes，`retries=0 tx_pending=0`
   - `capture_off ret=0 ack=0 tx_pending=0`
2. M55 接收和小智上行：
   - `probe_lwip=87/0`
   - `xz_last=313/600960`
   - `xz_fail=0`
3. M33 下行和播放写入：
   - `tts audio rx total=640`
   - `audio_playback Started`
   - `tts audio write chunk=1/2/3`
4. 测后基线仍健康：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wlan=1 ready=1`
   - `token_len=442`

后续判断：

1. 无人 QA 标准流程应为 `m55qa_probe_pcm_on -> m55qa_capture_on -> 立即 m33qa_xz_probe full -> m55qa_capture_off -> 等待 TTS -> m55qa_status`。
2. 如果 `M55 not listening`，先重新 `m55qa_capture_on`，不要直接查 WiFi/token。
3. 后续产品化仍要验证真实 CM55 mic0 路径；当前人声 QA 已证明平台上行、TTS 下行、M33 speaker write 链路至少打通一次。

## 40. 2026-06-22 小智 stop 前要 flush 未满一帧的尾音频

现象：

1. 人声素材 QA 已证明 M33->M55->小智上行能通，且 M33 能收到 TTS 并写入 speaker。
2. 但部分 probe 或短语音在 stop 前可能剩下不足 60 ms 的 PCM staging 数据。
3. 如果直接 stop/listen-stop，这段尾帧不会进入 Opus/PCM WebSocket binary，可能影响平台侧 STT/EOU 稳定性。

本轮修复：

1. M55 新增 `voice_service_flush_xiaozhi_tail_frame()`。
2. `voice_service_stop_xiaozhi_talk()` 在 `listen/stop` 前先把未满 `XIAOZHI_AUDIO_FRAME_BYTES` 的尾帧补零并发送。
3. 满帧发送逻辑收敛到 `voice_service_send_xiaozhi_frame_locked_copy()`，避免 PCM/Opus 两套计数和失败统计分叉。
4. pending TTS binary/raw/ignored 分支处理后立即 publish status，让 `tts_fwd` 等状态更及时。

验证：

1. M55 build 已通过：`text=1533528 data=68744 bss=4541584`。
2. 本轮未能继续烧录和人声 QA，因为板子/调试器没有被 Windows 枚举：
   - `program_with_resources.bat` 在写入前失败：`Error: unable to find a matching CMSIS-DAP device`
   - 串口查询只看到 com0com 虚拟端口，没有板子的 COM/KitProg。

后续判断：

1. 这是 USB/CMSIS-DAP 枚举问题，不是 WiFi/token/WebSocket/小智平台退化。
2. 等板子重新枚举后，先重新烧 M55，再烧 clean M33，然后跑无人 QA：
   - `m55qa_probe_pcm_on`
   - `m55qa_capture_on`
   - 立即 `m33qa_xz_probe full`
   - `m55qa_capture_off`
   - 等 60 秒
   - `m55qa_status`

## 41. 2026-06-22 `probe_lwip` 计数必须按 QA 轮次清零

现象：

1. 连续跑人声 QA 时，状态可能出现 `probe_lwip=87/87` 这种容易误读的结果。
2. M33 侧可能已经打印 `xiaozhi probe done parts=87 sent=166974/166974 retries=0 tx_pending=0`。
3. 但最终状态里的 ignored 可能来自上一轮之后的累计，不一定代表本轮一边接收一边忽略。

根因：

1. `probe_lwip=accepted/ignored` 原本是累计计数。
2. 新一轮 `m55qa_probe_pcm_on` 没有清零 accepted/ignored，导致历史成功/失败计数混在一起。

修复：

1. M55 在处理 `VOICE_CTRL_M33_PCM_PROBE_ENABLE` 时清零：
   - `m33_pcm_probe_accepted_count`
   - `m33_pcm_probe_ignored_count`
2. M55 对 accepted/ignored 计数更新加锁，避免 status 读取中间状态。

验证：

1. M55 build 通过：`text=1533576 data=68744 bss=4541584`。
2. M55 烧录成功：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. M33 clean image 本轮也已烧录并 verify：
   - `build/rtthread.hex` 写入 `593920 bytes`
   - verify `591828 bytes`
4. 干净计数的人声 QA：
   - 日志：`D:\RT-ThreadStudio\workspace\yiliao_m33\.codex_tmp\xiaozhi_qa_20260622_clean_counts_after_tail_flush.log`
   - `m33qa_xz_probe full` 发完 `87` 包 / `166974` bytes，`retries=0 tx_pending=0`
   - `capture_off ret=0 ack=0 tx_pending=0`
   - `probe_lwip=87/0`
   - `xz_last=143/274560`
   - `xz_fail=0`
   - `xz_ws=1 xz_stage=70 xz_errno=0 token_len=442 srv_hello=1`

当前剩余问题：

1. 这轮没有收到平台 STT/TTS/binary：
   - `xz_rx=1/0`
   - `srv_stt=0`
   - `srv_tts=0/0/0`
   - `tts_fwd=0/0`
2. 这不是 WiFi/token/M33 IPC 问题，因为 clean-count QA 已证明完整人声素材进入 M55 并上传到 XiaoZhi WebSocket。
3. 下一步只查 XiaoZhi relay/platform 在 `listen/start -> binary PCM -> listen/stop` 后为什么没有回 STT/TTS。

## 42. 2026-06-23 小智云端 TTS 下行会压满 M55 pending 队列

现象：

1. 云端 ASR/TTS 已验证能真实工作：`qwen3-asr-flash` 返回文本，`qwen-tts` 返回约 10 万字节 16 kHz mono PCM。
2. 但现场仍可能听不到人声，或者只听到一点杂音/短音。
3. M55 原先 TTS pending 只有 `4 * 16384 = 65536` bytes；云端一句 TTS 常见约 106 KB，并按 60 ms/1920 B 连续 WebSocket binary 下发。

根因：

1. WebSocket 回调收包速度远快于 `voice_service_thread_entry()` 向 M33 speaker 转发的速度。
2. 4 个 pending slot 很容易被前几包占满，后续 TTS binary 被丢弃，最终 M33 收不到完整人声。

修复：

1. M55 `applications/voice_service.c` 调整 TTS pending：
   - `VOICE_TTS_PENDING_SLOT_SIZE` 从 `16384` 改为 `4096`
   - `VOICE_TTS_PENDING_SLOT_COUNT` 从 `4` 改为 `64`
2. 总缓冲从 64 KB 提到 256 KB；单 slot 更贴近云端 1920 B PCM 帧，减少浪费并能缓存完整一句 TTS。

验证：

1. M55 build 通过：`text=1534872 data=68744 bss=4542096`。
2. M55 烧录成功：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. 末尾 `kitprog3: failed to acquire the device` 出现在 app/resources 都写完之后，按既有经验不视为烧录失败。

下一步现场判断：

1. 重新连小智后一轮真实说话，先看云端 `xiaozhi_session_latest.json` 是否出现 `asr_ok=true`、`entered_llm=true`、`event=tts`、`audio_bytes>0`。
2. 再看 M55/M33 串口状态：
   - M55 `tts_fwd` 应增长，`tts_fail` 不应持续增长。
   - M33 应打印 `Received TTS audio chunk from M55`、`audio_playback write/flush`。
3. 如果云端已有 TTS audio 但 M33 仍没播放，继续查 M33 `audio_playback_*` 设备选择/音量/写入返回值，不再回退到 WiFi/token。

## 43. 2026-06-23 小智 v3 binary 下行如果 payload 是 PCM，M55 必须剥 header 后透传

现象：

1. 平台 ASR/TTS 已能生成真实 TTS PCM，M55 pending buffer 也已扩到 256 KB。
2. 现场仍可能没有人声、只有短杂音，或者一轮结束后 LVGL 回到“连接中”。
3. 这类现象容易被误判为资源不够或 speaker 设备坏，但更直接的风险在下行协议格式。

根因：

1. 平台当前按 XiaoZhi Protocol-Version 3 binary frame 下发：
   - `[type=0, reserved=0, payload_size_be16, payload]`
2. 但 payload 内容是云端 TTS 生成的 16 kHz mono PCM16，不是官方 Opus。
3. M55 原逻辑看到 v3 header 后优先按 Opus 解码；如果失败，再 fallback 时可能仍把带 4 字节 header 的整包当 PCM 判断/播放。
4. 每 60 ms PCM 前多出 4 字节非音频头，会造成播放错位、杂音，甚至整段被拒绝。

修复：

1. M55 `voice_service_process_pending_tts()` 在 v3 Opus 解码失败后：
   - 调用 `voice_service_strip_v3_audio_header()` 剥掉 4 字节 v3 header
   - 对剥出的 payload 单独做 `voice_service_audio_looks_like_pcm16()`
   - 符合 PCM16 时只把 payload 透传给 M33 speaker
2. 保留官方 Opus 优先路径，后续平台真正下发 Opus TTS 时仍走 Opus 解码。

验证：

1. M55 build 通过：`text=1534872 data=68744 bss=4542096`。
2. M55 烧录成功：
   - `rtthread.hex` 写入 `1605632 bytes`
   - `whd_resources_all.bin` 写入 `466944 bytes`
3. 末尾 `kitprog3: failed to acquire the device` 仍是写完后的已知非关键现象。

下一步现场判断：

1. 一轮小智后看 M55 日志是否出现：
   - `v3 payload fallback to pcm16 len=...`
   - `pending binary audio forwarded`
   - `tts->m33 chunk=...`
2. M33 侧应出现：
   - `Received TTS audio chunk from M55`
   - `audio_playback flush`
3. 若这些都出现但仍无声，再查 M33 `audio_playback_tone_cmd`/codec 输出路径/功放音量，而不是继续改平台 token 或 WiFi。

## 44. 2026-06-23 小智连接跳动和 TTS binary 已收到但 tts_fwd=0

现象：

1. 现场 LVGL 看到“小智连接中/在线”一直跳，但 `m55qa_status` 显示 WiFi/token 基线健康：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_token=1 token_len=442`
   - 自动重连后 `xz_ws=1 xz_stage=70`
2. QA 1200 ms 人声素材已经能完整上行：
   - `probe_lwip=20/0`
   - `xz_last=216/414720`
   - `xz_fail=0`
3. 平台已有下行：
   - `xz_rx=4/3`
   - `srv_last=tts`
4. 但 M55 仍显示：
   - `tts_fwd=0/0`
   - `tts_fail=3`

根因：

1. 当前 M55 hello 协商的是 `Protocol-Version: 1` + `audio_params.format=pcm_s16le`。
2. 平台返回的 binary 应按 PCM 下行处理，不应该先按 Opus 或过度依赖 `voice_service_audio_looks_like_pcm16()` 猜测。
3. websocket 层可能把多个 1920 B binary frame 聚合成大于 4096 B 的回调 payload；原 `voice_service_enqueue_tts_payload()` 单 slot 容量 4096 B，超出就直接丢。
4. thinking timeout 之前在 WebSocket 短暂断开时会把 UI 改成 `CONNECTING`，导致用户看到连接状态跳动、按钮体验不稳定。

修复：

1. `voice_service_enqueue_tts_payload()` 支持把大 binary payload 切成多个 4096 B pending slot，而不是直接 drop。
2. `XIAOZHI_AUDIO_FORMAT_IS_PCM` 为真时，pending binary 直接按协商的 PCM 透传到 M33，不再先做 Opus 解码，也不再用 PCM 猜测挡掉下行人声。
3. thinking timeout 后 UI 统一回到 `READY/平台无回复，请重试`，避免短暂 WebSocket 状态把产品界面锁在“连接中”。

验证计划：

1. 重新 build/flash M55。
2. 再跑：
   - `m55qa_probe_pcm_on`
   - `m55qa_capture_on`
   - `m33qa_xz_probe 1200`
   - `m55qa_capture_off`
   - 等 30 秒 `m55qa_status`
3. 预期：
   - `xz_rx` text/binary 继续增长
   - `tts_fwd` 从 `0/0` 增长
   - `tts_fail` 不再随 binary 包数增长
   - LVGL 不应长期卡在“正在思考”或频繁跳“连接中”

## 45. 2026-06-23 小智连接不稳定时先分清“断线”和“TTS 未下发”

现象：

1. 现场反馈 LVGL 小智连接状态一直跳，一轮后显示连接中。
2. 实测 `m55qa_status` 曾出现：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_token=1 token_len=442`
   - `xz_ws=0 xz_stage=80 xz_errno=0`
   - `srv_stt=1 srv_tts=0/0/0`
   - `tts_fwd=0/0 tts_fail=1`
3. 手动 `m55qa_xz_reconnect` 可恢复：
   - `xz_ws=1 xz_stage=70`
   - `srv_hello` 增长

判断：

1. 这不是 WiFi/token 丢失；WiFi、IP、token 都健康。
2. 当前更像一轮语音 stop 后平台未形成可播放 TTS，随后 WebSocket 进入断开/重连。
3. 产品体验上不应让自动重连失败反复覆盖成“连接中”，否则用户会觉得按键被锁死。

修复：

1. M55 自动重连失败时，LVGL 状态改为 `READY/小智离线，按说话重试`，保留用户操作入口。
2. 平台 XiaoZhi TTS 记录新增：
   - `sent_frames`
   - `sent_bytes`
3. 下一轮 QA 可直接区分：
   - 平台 `audio_bytes>0 sent_bytes==audio_bytes` 但 M55 `tts_fwd=0`：查 WebSocket/M55/M33 下行。
   - 平台 `audio_bytes=0 sent_bytes=0 error=...`：查平台 TTS/ASR/LLM，不再误判为板端喇叭。

验证：

1. 平台小智测试通过：`python -m pytest apps/api/tests/test_rehab_arm_sync.py -k "xiaozhi"`，10 passed。
2. M55 build 通过：`text=1441032 data=68744 bss=4542096`。
3. 手动 `m55qa_xz_reconnect` 后状态恢复到 `xz_ws=1 xz_stage=70`。

## 46. 2026-06-23 平台收到长 PCM 但 ASR 空文本时先裁剪静音

现象：

1. 部署 `dc1442c5` 后，板端连接稳定，最终仍保持：
   - `xz_ws=1 xz_stage=70`
   - `probe_lwip=20/0`
   - `xz_last=159/305280`
2. 云端 `xiaozhi_session_latest` 显示实际收到了约 9.54 秒 PCM：
   - `audio_bytes=305280`
   - `audio_duration_ms=9540`
   - `audio_frame_count=159`
3. 但 ASR 结果为空：
   - `asr_called=true`
   - `asr_ok=false`
   - `asr_error=asr_empty_text`

判断：

1. 此时不是 WiFi/token/WebSocket 问题，也不是 M33 speaker 的第一故障点。
2. 平台已经收到音频，但传给 ASR 的整段 PCM 可能被前后静音或低幅度段稀释。
3. 若 ASR 无文本，平台不会进入有效 LLM/TTS，人声自然不会出来。

修复：

1. 平台 `transcribe_xiaozhi_pcm()` 在送 ASR 前增加 PCM16 前处理：
   - 20 ms 窗口找有效语音段
   - 保留 200 ms 前后 padding
   - 对低峰值语音最多做 8 倍保守增益
2. 平台 session 增加诊断：
   - `asr_audio_prep`
   - `prepared_audio_bytes`

验证：

1. 平台小智测试通过：`python -m pytest apps/api/tests/test_rehab_arm_sync.py -k "xiaozhi"`，11 passed。
2. 下一轮板端 QA 重点看：
   - `asr_ok` 是否变 true
   - `prepared_audio_bytes` 是否小于 `audio_bytes`
   - `srv_stt`、`srv_tts`、`tts_fwd` 是否增长

## 47. 2026-06-24 一直“请再说一遍”不等于没进服务器

现象：

1. 现场听到或看到小智反复说“请再说一遍”。
2. 云端 dashboard 对 `nanopi-m5` 显示仍然有真实链路数据：
   - `audio_format=opus`
   - `asr_called=true`
   - `opus_packet_count=83`
   - `sent_frames=83`
   - `sent_bytes=9202`
3. 旧会话里有一次 ASR 已识别出 `嗯，你是什么模型？`，但平台模型中转返回：
   - `classification.type=none`
   - `operator_facing_reply=请再说一遍。`
   - `provider.configured=false`

判断：

1. 这不是 WiFi/token/WebSocket 没连上。
2. 根因在云端平台：模型中转缺专用 key 时，把普通语音问题兜底成 `none`。
3. 不要回到 WiFi 扫描、token 重配、WHD resources，除非同时出现 `wlan=0`、`token_len=0` 或 `xz_ws` 长时间恢复不了。

修复：

1. 平台仓库 `D:\ai合作产品` 已提交并部署：
   - `1764e91b Fix XiaoZhi voice relay chat fallback`
   - 云端健康检查：`deployment.build_sha=1764e91b140b`
2. 模型中转现在可安全复用服务端 XiaoZhi ASR/TTS key，不会暴露给板端。
3. `vla_language_from_voice` 中有有效文本的普通问句现在兜底为 `daily_chat`。
4. 云端 smoke `你是什么模型` 已返回：
   - `classification.type=daily_chat`
   - `external_call_ok=true`
   - qwen-plus 自然回复。

下一轮现场验证：

1. 直接用 LVGL 再按一次说话/停止，不需要重配 token。
2. 若还有“请再说一遍”，先看平台 `asr_ok/asr_error/asr_text`：
   - `asr_text` 为空：查采集/音量/ASR timeout。
   - `asr_text` 有内容但回复错：查平台分类/LLM。

## 48. 2026-06-24 Opus TTS 下行要按 frame_duration 节奏发

现象：

1. 平台显示已经合成并发送 TTS：
   - `audio_format=opus`
   - `opus_packet_count>0`
   - `sent_frames>0`
2. 现场仍可能听不到人声或只有一点杂音。
3. 旧 dashboard 曾出现 `tts_send_timeout:frame=61`。

判断：

1. 官方 XiaoZhi Opus session 声明 `frame_duration=60`。
2. 平台原来每包固定 sleep 20 ms，会把 60 ms 音频按 3 倍速压给板端。
3. 这会让 M55/M33 speaker buffer 更容易超时或播放异常。

修复：

1. 平台 commit `1764e91b` 已把 TTS 下行 pacing 改成 `audio_params.frame_duration`，并限制在 10-120 ms。
2. 官方 60 ms Opus TTS 现在按 60 ms 间隔发包。

验证：

1. 本地平台 6 个关键小智测试通过。
2. 云端 3 个关键小智测试通过。
3. 下一轮现场如果仍无声，优先比较平台 `sent_frames/sent_bytes/error` 与 M55 `tts_fwd/tts_fail`，再看 M33 speaker 日志。

## 49. 2026-06-24 LVGL 点停止卡死时，不要在 stop 路径同步发 WebSocket

现象：

1. 现场 LVGL 点“停止”后界面卡住，像是程序死在“正在结束录音/正在思考”。
2. WiFi/token/WebSocket 基线仍健康，不应回退到 WiFi/token 调试。

根因：

1. 手动停止路径 `voice_service_stop_xiaozhi_talk()` 原来会先同步 `voice_service_flush_xiaozhi_tail_frame()`，再同步发 `listen stop`。
2. `websocket_client_send_text()` / binary send 内部使用 `tcpip_callback_with_block(..., 1)`，如果 lwIP/tcpip 线程正忙，UI 后台 worker 会被卡住。
3. 对产品体验来说，停止按钮不能为了补最后不足 60 ms 的尾帧而阻塞 UI。

修复：

1. M55 实际烧录树和 M55 镜像均已改为：
   - `voice_service_stop_xiaozhi_talk()` 不再同步 flush tail frame。
   - 手动/LVGL stop 直接走 `voice_service_stop_xiaozhi_listening_async()`。
   - `xz_stop` 线程负责后台发送 `listen stop`。
2. 自动 EOU 路径仍保留 tail flush，不影响自动断句时的完整性。

验证：

1. M55 实际树构建生成新 `rtthread.hex`。
2. `program_with_resources.bat` 烧录成功：
   - `rtthread.hex wrote 1720320 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
   - 末尾写完后的 `failed to acquire the device` 属已知非关键现象。
3. 串口 QA：
   - `m55qa_capture_on` -> `voice_ack cmd=1 result=0`
   - `m55qa_capture_off` -> `voice_ack cmd=2 result=0`
   - `tx_pending=0`
   - shell 没卡死
   - 5 秒后 `xz_listening=0`
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `srv_stt=1 srv_tts=1/1/0`
   - `tts_fwd=58/237568 tts_fail=0`

现场下一步：

1. 直接在 LVGL 再按“说话/停止”验证；预期停止按钮不再卡死。
2. 若界面仍卡住，先查串口 `m55qa_status` 的 `lvgl_flush` 是否增长、`xz_listening` 是否归零，再看是否是 LVGL 刷新/触摸层问题，而不是 XiaoZhi WebSocket stop。

## 50. 2026-06-24 TTS 下行会卡死时，先关闭 M55/M33 播放路径保稳定

现象：

1. 平台 ASR/TTS 已打通，`m55qa_xz_text 你好，请说一句你已经准备好了` 能返回：
   - `asr text: 你好，请说一句你已经准备好了`
   - `tts text: 我已经准备好了。`
2. 但一旦 M55 侧直接写 `sound0`，M55 状态发布会停止，现场表现为 LVGL/呼吸灯像卡死。
3. 改为发给 M33 后，M33 打印 `audio_playback unavailable: M55 owns sound0 for Xiaozhi`，说明 M33 播放路径当前配置关闭，继续灌 TTS audio 只会挤占 IPC。

当前稳定修复：

1. M55 保留官方 XiaoZhi Opus/WebSocket/文本链路，但默认关闭 TTS 音频播放：
   - `VOICE_TTS_PLAYBACK_TO_M33=0`
   - `VOICE_TTS_PLAYBACK_TO_M55=0`
2. 播放关闭时，TTS 二进制包在进入 Opus decode 前直接静音丢弃，避免解码/播放路径再次卡住 M55。
3. 唤醒 UI 立即显示 `我在`，主界面提示使用 `xiaorui`，避开当前自定义中文字库未覆盖的“瑞”等字。

验证：

1. M55 build 通过。
2. `program_with_resources.bat` 烧录成功：
   - `rtthread.hex wrote 1683456 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 串口 QA 后状态仍刷新：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `srv_hello=1 srv_stt=1 srv_tts=0/1/0`
   - `xz_rx=7/29`
   - `voice_svc` 从 `704` 继续增长到 `924`
   - `lvgl_flush` 从 `342` 继续增长到 `363`

下一步：

1. 扬声器不要再同时半开 M55/M33 两条路径。
2. 单独修复播放路径：
   - 若坚持 M55 speaker：先修 `sound0` replay/Opus decode 卡死问题，再打开 `VOICE_TTS_PLAYBACK_TO_M55`。
   - 若改 M33 speaker：先真正启用/验证 M33 `BSP_USING_AUDIO` 和 `audio_playback_probe_cmd`，再打开 `VOICE_TTS_PLAYBACK_TO_M33`。
3. 播放路径未独立验证前，不要把“没有人声”误判为 WiFi/token/平台问题。

## 51. 2026-06-24 M55 sound0 播放有声但卡顿时，优先看 replay 预缓冲

现象：

1. XiaoZhi 平台链路已通，`srv_hello=1`、`srv_stt` 增长、TTS 文本返回正常。
2. M55 `sound0` 已能播出人声，但听感卡顿、偶尔听不清。
3. 本地 `m55qa_speaker_tone 200` 正常，说明 ES8388/I2S 基础硬件不是完全坏。

根因：

1. 之前 TTS 写入策略每写一个 4096B replay 块就等待 replay queue 清空，并额外 `VOICE_TTS_CHUNK_GAP_MS` 延时。
2. 这会让播放器几乎没有预缓冲；Opus 解码、网络包到达或线程调度稍有抖动，I2S 中断侧就会插零，听起来就是断续/卡。
3. RT-Thread audio 会把 4096B replay 块拆成两个 2048B 送给 I2S，因此重点不是改协议或云端，而是让 replay queue 保持少量连续数据。

修复：

1. `VOICE_TTS_CHUNK_GAP_MS=0`，去掉人为块间停顿。
2. `VOICE_TTS_REPLAY_QUEUE_HIGH_WATER=2`，只在 replay queue 已有 2 块及以上时等待，允许保留预缓冲。
3. `RT_AUDIO_REPLAY_MP_BLOCK_COUNT=4`，给 replay memory pool 留出队列余量。
4. 保持 `VOICE_TTS_PLAYBACK_TO_M55=1`，M55 继续作为 XiaoZhi speaker owner。

验证：

1. M55 实际烧录树 `python -m SCons -j1` 通过。
2. `program_with_resources.bat` 烧录成功：
   - `rtthread.hex wrote 1720320 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 串口 QA：
   - `m55qa_speaker_tone 200` 成功。
   - `m55qa_capture_on` / `m55qa_capture_off` 均 ACK，`tx_pending=0`。
   - 平台返回 `asr text: 嗯。`、`tts text: 嗯，收到。需要我帮您做些什么吗？`
   - `tts_fwd` 从 `112/458752` 增长到 `141/577536`，`tts_fail=0`。
   - `xz_ws=1 xz_stage=70 xz_errno=0`，`lvgl_flush` 持续增长到 `1262`。

边界：

1. 若仍“有声但不清楚”，下一步看音量/削波/采样率，而不是 WiFi/token。
2. 若 `tts_fail` 增长或出现 `M55 sound0 queue busy timeout`，再调 replay high-water 或 block count。

## 52. 2026-06-24 M55 TTS 后不能影响唤醒，sound0 写入不能无限等

现象：

1. 用户反馈人声仍有卡顿，并且一轮说话/停止后唤醒词没用了。
2. 串口状态显示 TTS 后 `wake_on=0`，所以后续喊唤醒词不会进入本地唤醒检测。
3. 之前还出现过 TTS 后 `voice_svc`、`frames`、`lvgl_flush` 长时间不增长，说明播放写入可能阻塞语音服务相关线程。

修复：

1. `rt-thread/components/drivers/audio/audio.c`
   - `_audio_dev_write()` 中 replay memory pool 分配从 `RT_WAITING_FOREVER` 改为 100 ms 有限等待。
   - replay queue push 同样改为 100 ms 有限等待。
   - 拿不到 buffer/queue 时丢弃当前写入并返回，避免为了播放音频拖死唤醒/UI/状态发布。
2. `applications/voice_service.c`
   - 手动/LVGL stop 后重新布防 wake listening。
   - `wake_hit_streak` 清零，并设置短暂 `wake_skip_windows`，避免刚 stop 的残留窗口误触发。
3. `libraries/HAL_Drivers/drv_i2s.c`
   - 去掉 `BSP_USING_XiaoZhi` 下强制 TDM divider=15 的覆盖。
   - XiaoZhi 官方 Opus 当前声明为 16 kHz / mono / 60 ms，M55 `sound0` 也按 16 kHz / mono 配置，I2S 应走原 16 kHz divider。

验证：

1. M55 实际树两次 build 均通过，最后一次重编 `drv_i2s.o` 并生成 `rtthread.hex`。
2. `program_with_resources.bat` 烧录成功：
   - `rtthread.hex wrote 1720320 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 串口 QA：
   - 开机状态 `wake_on=1 wake_ready=1 xz_ws=1`。
   - `m55qa_capture_on` / `m55qa_capture_off` ACK 正常，`tx_pending=0`。
   - stop 后状态保持 `wake_on=1 wake_ready=1`。
   - TTS 后 15 秒 `voice_svc` 从 `627` 增长到 `976`，`lvgl_flush` 从 `299` 增长到 `521`。
   - `tts_fwd` 从 `16/65536` 增长到 `35/143360`，`tts_fail=0`。

边界：

1. 若用户仍觉得人声不清，下一步优先调播放音量/增益/削波，或在平台侧确认 TTS Opus 包本身音质；不要回退到 WiFi/token。
2. 若“唤醒词没用”，先查 `m55qa_status` 中 `wake_on`、`wake_ready`、`frames/windows` 是否增长。

## 53. 2026-06-25 capture stop 不能停掉 M55 mic0，否则第二轮和唤醒都会假在线

现象：

1. 用户反馈唤醒词不行，且第二次提问时容易卡死。
2. 串口状态一度显示 `wake_on=1 wake_ready=1`，但 `frames/windows/pcm_seq` 长时间不增长。
3. 这说明 wake 标志已打开，但 M55 `mic0` 采集线程没有继续给 wake engine 输入 PCM。

根因：

1. M33 bridge 的 `VOICE_CTRL_STOP_CAPTURE` 以及 UI/shell stop 路径会调用 `m55_mic_stop_internal()`。
2. 之后 `voice_service` 重新把 `wake_listening` 置 1，但 `mic0` 已被停掉，所以唤醒处于“假在线”。
3. 第二轮 capture 也可能遇到状态不一致：云端会话停了，但本地 mic/wake 流水线被 stop 破坏。

修复：

1. XiaoZhi capture stop 不再停 `mic0`。
2. stop 后显式 `voice_service_set_wake_listening_direct(RT_TRUE)`，并调用 `m55_mic_start_internal()` 做 mic keepalive/stale restart。
3. 只有真正的 `wake_off` / `VOICE_CTRL_STOP_LISTEN` 才停 M55 mic。

验证：

1. M55 build 通过，`program_with_resources.bat` 烧录成功：
   - `rtthread.hex wrote 1720320 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
2. 连续两轮 QA：
   - 第 1 轮 stop 后：`wake_on=1 wake_ready=1`，`frames 2301 -> 3400`，`lvgl_flush 275 -> 422`。
   - 第 2 轮 stop 后：`wake_on=1 wake_ready=1`，`frames 5332 -> 6420`，`windows 5191 -> 6236`，`lvgl_flush 679 -> 825`。
   - `tts_fail=0`，`xz_ws=1 xz_stage=70 xz_errno=0`。

边界：

1. 如果现场仍说唤醒词没反应，但 `frames/windows` 增长，下一步查 wake engine 词表/门限/置信度。
2. 如果 `frames/windows` 不增长，优先查 `m55_mic` 线程和 `mic0` 设备，不要查 WiFi/token。

## 54. 2026-06-25 本地唤醒反馈和第二轮 capture_on 不能阻塞控制线程

现象：

1. 用户要求唤醒词触发后本地立即回复“我在”，这个反馈不应进服务器。
2. 一轮说话/停止后，第二次 `m55qa_capture_on` 曾出现 ACK 超时、`tx_pending=1`，严重时 shell 也短时间不回显。
3. `xz_ws=1 token_len=442 wlan=1` 仍健康，所以不是 WiFi/token 问题。

修复：

1. 新增 `applications/xiaozhi_wake_feedback_audio.c/.h`，内置 16 kHz/16-bit/mono 的“我在”PCM。
2. wake hit 后优先调用 `official_voice_speaker_play_pcm()` 播本地“我在”，失败时退回短 beep。
3. `official_voice_speaker_play_pcm()` 增加 speaker 互斥；若 `sound0` 正忙则立即返回，避免提示音抢占 TTS 或拖死控制线程。
4. M55 bridge 的 `VOICE_CTRL_START_CAPTURE` 改为快速 ACK，然后由后台 `xz_cap_on` 线程执行 `voice_service_start_xiaozhi_talk()` 和 `m55_mic_start_internal()`。
5. WebSocket 已连接但 hello 晚到时，不再把 start 视为硬失败；使用本地 session 继续发送 listen_start，hello 到达后自然刷新状态。
6. 回退 1920B/60ms 底层 replay/I2S 几何实验，保持已验证稳定的 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`、`PLAYBACK_DATA_FRAME_SIZE=2048`、`TX_FIFO_SIZE=4096`。当前要优化卡顿，优先做队列/水位/音量，不要再直接改底层块大小。

验证：

1. M55 build 通过，烧录成功：
   - `rtthread.hex wrote 1744896 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
2. 串口验证第二次 capture 不再卡死：
   - `m55qa_capture_on` ACK：`voice_ack cmd=1 result=0`，`tx_pending=0`
   - capture_on 后状态：`xz_listening=1 xz_ws=1`
   - `m55qa_capture_off` ACK：`voice_ack cmd=2 result=0`，`tx_pending=0`
   - stop 后状态：`wake_on=1 wake_ready=1 xz_ws=1`
   - TTS 继续转发：`tts_fwd=94/385024`，`tts_fail=0`

边界：

1. 若现场仍觉得人声卡，但 `tts_fail=0`、`lvgl_flush` 增长、shell 可回显，下一步调 M55 播放队列水位/音量/削波，不改 WiFi/token。
2. 若喊唤醒词没有听到“我在”，先看是否有 wake hit；有 wake hit 但无声音再查 `sound0` 忙状态和本地 PCM 播放日志。

## 55. 2026-06-25 对齐官方音频节奏，不要靠更大缓存掩盖问题

现象：

1. 声音卡、唤醒词不稳、多轮后更差。
2. 串口仍旧很难读到，但 OpenOCD 显示核在跑，不是直接死机。
3. 之前用过更大的 replay 缓存，但体验没有本质改善。

确认到的官方方向：

1. M55 继续负责 `mic0` / `sound0`。
2. 上行还是 Opus / 16 kHz / 60 ms。
3. 播音期间暂停 wake，播完后再冷却重启 wake，更接近官方例程的节奏。

本轮收口：

1. replay 参数回到 `4096/4`。
2. TTS 期间暂停 wake，TTS stop 后再 re-arm。
3. 本地“我在”走 speaker 互斥，避免和 TTS 抢声卡。

## 56. 2026-06-26 LVGL stop 不要进入“正在思考”状态

现象：

1. 现场反馈按 LVGL 停止后容易卡住，严重时看起来像白屏/程序不动。
2. 这类问题不一定是 LCD 初始化失败；历史状态里 `lvgl_flush` 曾持续增长，说明更像 UI 状态机被卡在错误阶段。

根因：

1. stop 按钮之前把 UI 置为 `XIAOZHI_UI_THINKING` / “正在结束录音”。
2. `THINKING` 是“已发给平台、等待模型/TTS”的状态，不适合本地 stop。
3. 如果 stop 的平台通知或会话收尾被延迟，用户会误以为小智一直在思考，按钮体验也像卡死。

修复：

1. stop 按钮改为 `XIAOZHI_UI_CONNECTING` / “正在停止录音”，只表达本地控制动作正在执行。
2. UI worker 调用 `m55_xiaozhi_talk_stop_from_ui()` 后，无论成功或失败都回到 `XIAOZHI_UI_READY`：
   - 成功：`已停止，等待唤醒词`
   - 失败：`停止失败，请重试`
3. 曾尝试把 LVGL 线程栈从 16 KB 提到 18 KB，build/link 可通过；但现场随后反馈白屏，内存布局风险优先级高于栈余量，本轮已回退到 16 KB。

验证：

1. M55 实际树 build 通过：
   - `SCons exit=0`
   - `text 1677260 data 81404 bss 4535232 dec 6293896`
2. 22 KB / 32 KB LVGL 栈会让 M55 internal RAM 链接溢出；18 KB 虽能链接，但白屏排查阶段不保留，回到此前稳定的 16 KB。
3. `program_with_resources.bat` 烧录成功：
   - `rtthread.hex wrote 1761280 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`

边界：

1. M55 当前默认 `M55_DETACH_CONSOLE_FOR_M33_QA=1`，会主动 detach console，不能仅凭 COM4 沉默判断 M55 死机；需要现场看屏幕和呼吸灯，或用 OpenOCD/调试链路确认核是否在跑。
2. 如果白屏仍复现，下一步先查 LVGL 线程活性、flush 计数、LCD reset/backlight 和 UI 状态转换，不要回退到 WiFi/token 或平台协议。

## 57. 2026-06-26 白屏继续复现时先做显示分层，不要继续猜小智协议

现象：

1. 回退 LVGL 栈到 16 KB 后，现场仍反馈白屏。
2. `drv_lcd.c` 的硬件 framebuffer 默认值是 `0xFF`，也就是 LCD/LVGL 首帧没有覆盖时，现场看到的就是纯白。

修复：

1. LCD framebuffer 硬件兜底从白底改成黑底：
   - `graphics_buffer` 初值从 `0xFF` 改为 `0x00`
   - `drv_lcd_hw_init()` 中 fallback `memset` 从 `0xFF` 改为 `0x00`
2. `lv_user_gui_init()` 先显示一个极简深色启动屏：
   - `XiaoZhi`
   - `starting...`
3. 800 ms 后再进入原来的完整 WiFi/XiaoZhi 面板。

验证：

1. M55 build 通过，`rtthread.hex` 更新时间为 2026-06-26 04:39:41。
2. 烧录成功：
   - `rtthread.hex wrote 1761280 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`

判定：

1. 若现场看到深色 `XiaoZhi starting...`，说明 LCD 和 LVGL 线程已活，后续问题在完整面板创建/刷新。
2. 若仍纯白，说明新固件未运行到 LCD fallback/首帧，优先查烧录生效、复位、LCD init、backlight/reset 或 CM55 是否启动。

## 58. 2026-06-26 M33 watchdog 不要把小智瞬时重连误杀成 CM55 死机

现象：

1. 小智停止、播放、第二轮说话时可能显示连接中/离线跳变。
2. 这不一定是 M55 WiFi/token/WebSocket 主链路坏了，也可能是 M33 侧 watchdog 在 `tx_pending` 和旧 `voice_status` 同时出现时自动重启 CM55。

处理：

1. M33 `applications/main.c` 新增 `M33_CM55_AUTO_RESTART_ENABLE=0`，默认只打印诊断，不自动 reset/enable CM55。
2. watchdog 日志补充 `stage`、`errno`、`flags`、`tx_pending`、`auto_restart`，方便区分真正卡死和小智短暂重连窗口。
3. 保留手动 `m33_cm55_restart`，只在确认 CM55 真的无 LVGL/LED/voice_status 活性时使用。

边界：

1. 后续如果又看到“小智离线/连接中”，先看 M33 watchdog 日志是否出现 `auto_restart=0` 的 stale/tx stuck 诊断，再决定是否查 M55。
2. 不要因为短暂 `xz_ws=0` 或 UI 连接中就回退 WiFi 扫描、token、资源固件方向。

## 59. 2026-06-26 唤醒“我在”反馈只保留一个入口

现象：

1. 用户喊“小瑞/xiaorui”后希望立即得到本地固定“我在”反馈，再继续说问题。
2. 现场反馈唤醒和播放仍有卡顿感，speaker 被短时间重复占用会放大这个体验问题。

修复：

1. `voice_service_process_audio_buffer()` 检测到 wake 后不再先直接调用 `xiaozhi_feedback_wake_local()`。
2. 统一由 `voice_service_start_xiaozhi_listening()` 内部执行：
   - `xiaozhi_ui_state_mark_wake(...)`
   - `xiaozhi_feedback_wake_local()`
   - `listen/start`
3. 这样一次唤醒只播放一次“我在”，避免重复抢 `sound0`。

边界：

1. 这只修本地反馈重复播放，不改变 wake engine 阈值、关键词、Opus/WebSocket 协议。
2. 如果仍唤醒不了，下一步看 `wake_ready/wake_stage/wake_xiaorui/noise/threshold`，不要先改平台。

## 60. 2026-06-26 M55 “我在”重复播放修复已全量构建并刷入实际树

验证：

1. 因 `.sconsign.dblite` 曾异常，备份为 `.sconsign.dblite.codexbak` 后触发 M55 全量重建。
2. 全量 SCons 最终生成新产物：
   - `rt-thread.elf` 更新时间：2026-06-26 15:20:07
   - `rtthread.hex` 更新时间：2026-06-26 15:20:16
   - `.sconsign.dblite` 恢复到约 11 MB，说明 SCons 数据库已重建完成。
3. `program_with_resources.bat` 已刷入实际 M55 树：
   - `rtthread.hex wrote 1765376 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
4. 刷写完成后末尾仍出现 `kitprog3: failed to acquire the device`，但发生在 app 和 WHD resources 都写完之后，仍按非关键现象处理。
5. OpenOCD 观察双核均处于 Thread 态：
   - M33 `pc=0x08391ca8 msp=0x240fcfe0 psp=0x240c4058 xpsr=0x61000000`
   - CM55 `pc=0x6068d09c msp=0x2003ffe0 psp=0x2003c350 xpsr=0x61000000`
6. 读寄存器会 halt 核心，验证后已执行 `reset run` 让板子回到运行态。

边界：

1. 这轮只验证 M55 新固件已构建、刷入、双核能跑；不代表现场声学链路已经人工听感验收。
2. 如果现场仍反馈唤醒不稳定或 TTS 卡顿，下一步优先看 M55 侧 `wake_ready/wake_stage/wake_xiaorui`、本地反馈播放占用、TTS 播放缓冲和 WebSocket reconnect 事件，不要回退 WiFi/token。

## 61. 2026-06-26 M55 XiaoZhi project_id 已从旧项目切到当前 VLA 项目

现象：

1. 云端看到 M55 XiaoZhi 连接旧 project：`fd6a55ed-a63c-44b3-b123-96fb3c154966`。
2. 当前 VLA 页面使用新 project：`e201f41c-25a6-46e1-baf8-be6dcb83284c`。
3. `device_id=nanopi-m5` 只是平台路由标签，小智物理仍运行在 M55，不要因此改 NanoPi agent、摄像头、CAN 或 M33 运动控制。

修复：

1. M55 `applications/xiaozhi_voice_relay.h` 的 `XIAOZHI_PROJECT_ID` 已改为 `e201f41c-25a6-46e1-baf8-be6dcb83284c`。
2. M55 LVGL/BLE 配网 payload 中的 `project_id` 同步改为新 project。
3. 实际烧录树 `wifi` 与 Git 镜像 `_m55_ref_repo` 已同步同一改动。
4. 本地 `token.txt` 解码确认也是新 project token，已通过 `m55qa_xz_token_begin/part/commit` 分 8 段刷新到板端，未打印 token 内容。

验证：

1. M55 `python -m SCons -j8` 构建通过，`rtthread.hex` 重新生成。
2. `program_with_resources.bat` 已写入：
   - `rtthread.hex wrote 1769472 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 尾部 `kitprog3: failed to acquire the device` 仍发生在两段写完之后，按已知非关键现象处理。
4. 烧录后 WiFi 配置曾丢失为 `saved=0/wlan=0`，已用 `m55qa_wifi_ssid/password/auto/save/connect` 恢复到：
   - `saved=1 auto=1`
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `cloud_tcp=0/1`
5. 新 project dashboard 已能看到 `project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c` 下的 `xiaozhi_ws_input` / `model_relay_request` 历史事件，包含官方 Opus 16 kHz 路径。

剩余问题：

1. 当前板端网络和 token 健康，但 `xz_ws=0`、`srv_hello=0`，WebSocket 阶段仍在 `xz_stage=30/80` 间跳，曾见 `xz_errno=-3`。
2. 这已不是旧 project、WiFi、token 长度或 NanoPi 摄像头链路问题。
3. 下一步只查 M55 WebSocket 握手/认证失败细节、运行时 URL 是否被配置命令覆盖、服务端是否拒绝新 token；不要回退到旧 project，也不要改服务器核心协议。

## 62. 2026-06-27 新 project relay token 已写入 M55 并完成 WebSocket hello

现象：

1. M55 源码和 URL 已切到新 project，但板端仍使用旧的 442 字节 token 时，WebSocket/HTTP relay 会被云端拒绝。
2. PC 侧用旧 token 直连 WebSocket 返回 `403 Forbidden`，HTTP model relay 返回 `401 Unauthorized`。
3. 这不是 WiFi、NanoPi 摄像头、CAN、M33 运动控制或服务器核心协议问题。

修复：

1. 通过云端设备 relay-token 接口重新签发 `project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c`、`device_id=nanopi-m5` 的新 token。
2. 新 token 保存到工作区 `D:\RT-ThreadStudio\workspace\token.txt`，字符长度 468。不要在日志或文档中打印 token 内容。
3. 用 COM4 QA 命令慢速写入 M55：
   - `m55qa_xz_token_begin`
   - `m55qa_xz_token_part <chunk>`，56 字符一片，每片间隔约 1 秒
   - 遇到 `ret=-28` 要等待 1-3 秒重试同一片，不要继续压队列
   - `m55qa_xz_token_commit`
4. 如果串口或 IPC 静默，先 OpenOCD `reset run`，再查询 `m55qa_status`。本次 reset 后 token 已持久化，无需重签。

验证：

1. PC 侧 raw WebSocket handshake 使用新 token 返回 `HTTP/1.1 101 Switching Protocols`。
2. M55 reset 后 `m55qa_status` 已确认：
   - `xz_token=1 token_len=468`
   - `wlan=1 ready=1`
   - `ip=192.168.3.32`
   - `xz_ws=1`
   - `xz_stage=70`
   - `xz_errno=0`
   - `srv_hello=1`
3. 新 project dashboard：
   `http://106.55.62.122:8011/api/rehab-arm/v1/devices/dashboard?project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c`
   已看到 `device_id=nanopi-m5` 的最新 `xiaozhi_session`，payload 内 `project_id` 为新 project。
4. VLA 页面：
   `http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/rehab-arm-control`
   HTTP 访问返回 200。

边界：

1. “小智连接到当前 VLA project”这一项已验证通过，后续不要再回到旧 project 或旧 token。
2. 下一步若用户反馈卡顿、听不清、唤醒不灵，应查 M55 声学路径、TTS 播放缓冲、wake `xiaorui` 置信度和多轮 reconnect，不要改 NanoPi V 链路或服务器核心 relay。

## 63. 2026-06-27 M55 多轮 TTS 卡顿和本地“我在”反馈音修复

现象：

1. 现场反馈第一轮扬声器输出基本不卡，但后续轮次可能重新变卡、发糊或不清晰。
2. 唤醒后的本地固定反馈音不像准确的“我在”。
3. 同时 `m55qa_status` 已能恢复到 `wlan=1 ready=1 xz_ws=1 xz_stage=70 srv_hello=1`，所以这轮不要回退 WiFi、token、project_id、NanoPi 摄像头或服务器核心 relay。

原因和修复：

1. M55 下行 TTS 走官方 Opus 路径，Opus decoder 是有状态的；之前每轮 `tts start` 没有显式 reset，可能把上一轮状态带到下一轮，造成多轮后听感变差。
2. 增加 `xiaozhi_opus_decoder_reset()`，并在 M55 收到 server `tts/start` 时重置解码器，同时清空本地 TTS pending 队列和半包。
3. TTS 预缓冲线程等待从 1 秒级 sem timeout 改为 20 ms 周期检查，避免少量首包场景把播放节奏拖断。
4. 唤醒重启条件收紧为 `tts_pending_count == 0` 后再 re-arm，避免 TTS 还在本地播放时唤醒/麦克风提前抢音频链路。
5. `xiaozhi_wake_feedback_audio.*` 改为用 zh-CN SAPI 对中文文本 `U+6211 U+5728` 生成的 16 kHz/16-bit/mono PCM，替换此前容易读成拼音感的资源。

验证：

1. `python -m SCons -j8` 构建通过，生成 `rtthread.hex`，仅保留既有 warning。
2. `program_with_resources.bat` 已完整写入：
   - `rtthread.hex wrote 1769472 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 烧录后约 15 秒查询 COM4，M55 已恢复：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 xz_errno=0 srv_hello=1`
   - `wake_on=1 wake_ready=1`

现场验证重点：

1. 连续唤醒/提问 3 轮以上，确认第二轮以后 TTS 不再明显卡顿。
2. 喊 `xiaorui` 后确认本地反馈音更接近清晰“我在”。
3. 若仍卡顿，优先看 `TTS prebuffer ready slots=... elapsed=...`、`tts_fwd`、`tts_fail`、`M55 sound0 queue busy timeout`，不要改 WiFi/token。

## 64. 2026-06-27 M55 sound0 4096B replay block 会导致 mono->stereo 越界

现象：

1. 现场继续反馈：第一轮 TTS 还能接受，后续仍卡；本地“我在”仍听起来不对。
2. `m55qa_status` 显示 `tts_fwd` 持续增长且 `tts_fail=0`，说明平台下行和 M55 写 speaker 没有失败，问题在本地播放几何/缓冲。

根因：

1. RT audio replay block 原为 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`。
2. `sound_transmit()` 把 4096B 当成 `2048` 个 mono int16 sample。
3. `drv_i2s.c::convert_mono_to_stereo()` 会把 N 个 mono sample 扩成 2N 个 stereo sample。
4. 但底层 `PLAYBACK_DATA_FRAME_SIZE=2048` 是 stereo buffer 长度；4096B replay block 会尝试写 4096 个 int16 到 2048 个 int16 buffer，存在越界/覆盖，足以造成多轮卡顿、杂音或状态不稳。
5. 本地“我在”短 PCM 还存在尾包不足一个 replay block 时不会被 RT audio push 的问题，导致末尾可能丢失或听起来不完整。

修复：

1. `rtconfig.h` 将 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE` 从 `4096` 改为 `2048`，即每个 block 是 `1024` 个 mono sample，扩成 stereo 后刚好匹配 `PLAYBACK_DATA_FRAME_SIZE=2048`。
2. `official_voice_speaker_play_pcm()` 在短句 PCM 播完后补零到 replay block 边界，确保“我在”尾包被送到底层。
3. 这条结论覆盖旧文档中“保持 4096B”的经验记录；旧记录是在没有检查 mono->stereo 扩展目标 buffer 的情况下得到的。

验证：

1. `python -m SCons -j8` 增量构建通过。
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1769472 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 烧录后 `m55qa_status`：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 srv_hello=1`
   - `wake_hit=1 wake_xiaorui=976/1000`

现场继续验证：

1. 连续 3-5 轮对话，重点听第二轮以后是否还卡。
2. 真实喊 `xiaorui` 后听本地“我在”是否完整、准确。

## 65. 2026-06-27 中文 TTS 长回复卡顿还要避开串口日志阻塞

现象：

1. 现场反馈英文版本一直不卡；切到中文后前两句不卡，后面又卡。
2. 这说明 speaker 硬件和基础连接不是根因，更像中文 TTS 长回复数据量更大后，播放线程被额外工作拖出空洞。
3. COM4 日志里中文轮次 `tts_fwd` 持续增长、`tts_fail=0`，平台音频确实到了 M55。

修复：

1. `voice_service.c` 的 TTS 热路径日志节流：
   - `server binary audio`
   - `v3 opus frame`
   - `v3 opus frames done`
   - `pending binary audio forwarded`
   只打印前 3 个包和每 50 个包，避免中文长音频期间串口 `rt_kprintf` 阻塞播放。
2. `voice_tts` 线程优先级从 `18` 提到 `8`，让 Opus decode + sound0 enqueue 更接近音频播放线程，不再被普通业务线程轻易抢占。

验证：

1. `python -m SCons -j8` 构建通过。
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1769472 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 烧录后 `m55qa_status`：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 srv_hello=1`

现场继续验证：

1. 用中文连续 3-5 轮对话，重点听第三句以后是否还出现断续。
2. 若仍卡，下一步不要再调 WiFi/token/project；优先加播放侧低开销计数：TTS pending 高水位、sound0 replay queue 高水位、Opus decode 耗时。

## 66. 2026-06-27 回退 voice_tts 高优先级并给 speaker 锁加超时

现象：

1. 将 `voice_tts` 优先级从 18 提到 8 后，现场第二轮中文对话直接卡死。
2. 卡死时 COM4 一度无有效回显，说明不是简单的音质差，而是调度/锁等待层面的系统卡住风险。

修复：

1. `voice_tts` 线程优先级回退到 18，保留 TTS 热路径日志节流。
2. `voice_service_stream_pcm_to_m55_speaker()` 和 flush 路径中获取 `official_voice_speaker_take()` 的等待从 `RT_WAITING_FOREVER` 改为 `VOICE_TTS_REPLAY_WAIT_MS`，避免 speaker 锁异常时永久阻塞。
3. 后续不要再用提高 `voice_tts` 优先级当首选方案；中文卡顿应优先做低开销水位/耗时诊断。

验证：

1. `python -m SCons -j8` 构建通过。
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1769472 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 烧录后 `m55qa_status` 恢复：
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `xz_ws=1 xz_stage=70 srv_hello=1`

## 67. 2026-06-27 M55 中文 TTS 第二轮卡死根因是 v3 Opus 大包边界，不是 WiFi/project

现象：

1. 现场反馈“英文那版一直不卡，中文前两句不卡，后面又卡”，本轮 QA 复现到第二轮 `m55qa_xz_text test2` 后 M33 连续报：
   - `cm55 tx stuck pending=1 flags=0x27 stage=80 errno=-3`
   - 后续重连阶段可见 `stage=20 errno=-1`
2. 第一轮同固件可播放，`tts_fwd` 增长且 `tts_fail=0`，说明不是 WiFi、token、project_id 或平台没回音频。
3. 旧的 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=2048` 判断不可靠；RT audio 写入使用实际 block size，2048 反而更容易触发重启。当前稳定基线应保持 `4096`。

修复：

1. `rtconfig.h` 保持 `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`，不要再按 2048 方向继续实验。
2. WebSocket 单消息上限从 `4096` 提到 `8192`，但接收 buffer 改为 `mem_malloc()` 按需分配，避免 8KB 静态 `.bss` 造成 M55 内部 RAM 链接溢出。
3. TTS pending 总缓冲仍保持约 256KB：`8192 * 32`，不增加总 heap 压力。
4. TTS 入队不再把一个 WebSocket audio payload 硬切成多个 4096 片，避免破坏官方 v3 Opus 帧边界。
5. `voice_service_decode_v3_opus_frames_to_m55_speaker()` 增加边界检查：`offset + 4 + frame_len <= len`，异常帧只记录 `phase=5103` 后跳出，不再越界送 Opus decoder。
6. 增加 M55 侧 `m55qa_tts_diag`/`m55qa_xz_cn`/`m55qa_xz_en` 命令和 TTS 水位计数；注意 COM4 默认是 M33 shell，看不到 M55 直连命令，现场仍主要用 M33 的 `m55qa_status` / `m55qa_xz_text`。

验证：

1. `python -m SCons -j8` 构建通过，最终大小：
   - `text=1686956 data=81404 bss=4528864`
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1769472 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 烧录后健康状态：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `token_len=468 srv_hello=1`
4. 串口 QA 连续 3 轮通过：
   - `m55qa_xz_text hi`：`tts_fwd=47/192512 tts_fail=0 xz_ws=1`
   - `m55qa_xz_text test2`：`tts_fwd=85/348160 tts_fail=0 xz_ws=1`
   - `m55qa_xz_text zhongwen`：平台返回 `你好！请问有什么我可以帮您的？`，`tts_fwd=106/434176 tts_fail=0 xz_ws=1`
5. 启动状态曾看到 `wake_xiaorui=957/1000`，说明 xiaorui/小瑞唤醒模型本身仍能命中；后续若现场喊不醒，应优先看环境噪声/阈值/麦克风输入，而不是回退 TTS。

补充修正：

1. 复位后现场又反馈语音卡，COM4 状态显示 heap 曾接近满载：`heap=1411856/1429160`，只剩约 17KB。
2. 将 TTS pending 总缓冲从 `8192*32` 降到 `8192*16`，保留 8192 单包能力但释放约 128KB heap。
3. WebSocket 临时接收 buffer 不能只按第一个 frame 的 `paylen` 分配后复用；同一个 TCP pbuf 里可能先来短 text frame，再来更大的 binary frame。修复为按当前最大 payload 自动释放并重新分配，避免短 text buffer 被后续 binary audio 写爆。
4. 复位后重新 QA：
   - 初始 `heap=1230920/1429160`
   - `m55qa_xz_text hi`: `tts_fwd=22/90112 tts_fail=0 xz_ws=1`
   - `m55qa_xz_text zhongwen`: `tts_fwd=98/401408 tts_fail=0 xz_ws=1 tx_pending=0`

## 68. 2026-06-27 “我在”资源替换和 QA text 状态污染修复

现象：

1. 现场确认云端 TTS 已不卡，但本地唤醒反馈“我在”听起来不准确。
2. 替换资源时又发现 `m55qa_xz_text` 会污染验证状态：如果平台只先回 text，旧 QA 路径会先进入 manual listening，使 `wake_on=0`，后续命令可能排队等待，表现为 status stale。

修复：

1. 将本地 `g_xiaozhi_wake_feedback_wozai_pcm` 替换为新的 16 kHz / 16-bit / mono 短资源：
   - 来源：Windows zh-CN SAPI `Microsoft Yaoyao`
   - 文本：`我在`
   - 裁剪：保留约 40ms 前导和 120ms 尾部，轻微 fade，峰值限制到 20000
   - 长度：`8623 samples`，约 `539ms`
2. `voice_service_qa_xiaozhi_text_turn()` 不再先进入真实 manual listening 状态；QA text 只直接发送带文本的 listen stop，避免把 wake/listening 状态拉乱。
3. 正常 LVGL/唤醒/手动说话路径不改变。

验证：

1. `python -m SCons -j8` 构建通过，`rtthread.hex` app 写入 `1765376 bytes`。
2. 烧录后 `m55qa_status`：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `heap=1248984/1429160`
   - `wake_on=1`
3. `m55qa_xz_text hi` 后状态不再 stale：
   - `tx_pending=0`
   - `wake_on=1`
   - `xz_ws=1`
   - `tts_fwd=23/94208`
   - `tts_fail=0`

现场验证：

1. 喊 `xiaorui/小瑞` 后听本地“我在”是否比旧 Huihui 版本更像自然中文。
2. 如果仍不满意，下一步只换音频资源，不再动 TTS/WebSocket/heap 修复。

## 69. 2026-06-27 服务器 TTS 卡顿复位后排查和播放线程节流

现象：

1. 现场反馈复位后服务器返回语音仍有卡顿，偶尔第二轮卡死。
2. 复位后健康检查显示 WiFi/token/project 仍正常，自动重连后可恢复到：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `wlan=1 ready=1 ip=192.168.3.32`
   - `token_len=468 srv_hello=1`
3. 连发 `m55qa_xz_text` 不再适合作为播放压测证据：本轮观察到平台只回 text、不回 binary audio，`tts_fwd=0`，还可能把 M33->M55 QA 控制队列顶成 `tx_pending>0`。真实体验验证应优先用 LVGL 按说话/停止或 `xiaorui` 唤醒后的产品路径。

修复：

1. TTS prebuffer 保持更稳的播放侧缓冲：
   - `VOICE_TTS_REPLAY_QUEUE_HIGH_WATER=4`
   - `VOICE_TTS_PREBUFFER_MIN_SLOTS=8`
   - `VOICE_TTS_PREBUFFER_MAX_MS=520`
2. 增加 M55 TTS 本轮诊断计数，不扩展 M33/M55 IPC 结构，避免只烧 M55 时和旧 M33 固件 ABI 错位：
   - pending 高水位
   - sound0 replay 队列高水位
   - Opus decode 最大耗时
   - sound0 write 最大耗时
3. 为了让 COM4 旧 `m55qa_status` 能看到诊断，TTS 播放后临时复用已有字段：
   - `srv_lens=pending/high/replayq`
   - `srv_err=decode_ms/wait_timeout`
   - `raw=speaker_busy`
   - `hint=write_ms`
4. `voice_tts` 线程优先级从 18 小幅调到 16，略高于 `xz_bridge` 的 17，避免服务器音频到达时播放线程被桥线程挤压；不要回到过激的 8。

验证：

1. `python -m SCons -j8` 构建通过，当前大小：
   - `text=1681644 data=81404 bss=4528752`
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1765376 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 烧录后启动健康检查通过：
   - 第 1 次状态 WiFi 仍在启动：`wlan=0 xz_ws=0 stage=30`
   - 第 2 次状态 WiFi ready：`wlan=1 ready=1 ip=192.168.3.32`
   - 第 3 次状态 WebSocket ready：`xz_ws=1 xz_stage=70 srv_hello=1 tx_pending=0`

后续现场验证：

1. 不要连发 `m55qa_xz_text` 判断卡不卡；用 LVGL 按说话/停止或唤醒词走真实链路。
2. 如果仍卡，先贴最近一条 `m55qa_status`，重点看：
   - `tts_fwd` 是否增长、`tts_fail` 是否为 0
   - `srv_lens` 三段是否出现 replayq 高水位
   - `srv_err/raw/hint` 是否显示 decode/write/wait/busy 异常
   - `tx_pending` 是否保持 0

补充修正：

1. 复位后曾出现 WiFi/token 正常但小智长期停在：
   - `xz_ws=0 xz_stage=20 xz_errno=-1/0`
   - 主状态仍刷新，说明不是系统死机，而是 WebSocket connect 过早进入 `CONNECT_START` 后没有及时退出。
2. 自动重连改为异步短线程 `xz_reconn`，voice service 主线程不再同步执行 `websocket_client_connect()`，避免连接阶段阻塞状态刷新、唤醒和后续重试。
3. 新增 `voice_service_network_ready_for_xiaozhi()`：只有 `rt_wlan_is_ready()` 且默认 netdev 已有非零 IP 后才启动 WebSocket connect，避免 DHCP 未 ready 时抢连。
4. 验证：
   - 复位初期 `wlan=0/ready=0` 时 `xz_stage=5`，不再抢到 `stage=20`
   - WiFi 关联但 DHCP 未 ready：`wlan=1 ready=0 ip=0.0.0.0`，仍不抢连
   - DHCP ready 后自动恢复：`xz_ws=1 xz_stage=70 srv_hello=1`
   - 空闲 25 秒后仍保持：`xz_ws=1 xz_stage=70 tx_pending=0`

## 70. 2026-06-27 TTS 播放时仍在 listening 导致云端语音卡顿

现象：

1. 现场反馈服务器回来的中文语音仍然卡，且“之前有段时间不卡”。
2. 实时 `m55qa_status` 抓到 TTS 播放期间：
   - `xz_ws=1`
   - `tts_fwd=56/229376`
   - `tts_fail=0`
   - `srv_lens=0/8/4`
   - `srv_err=0x0003/0x0000 raw=0 hint=0x0001`
3. 这说明 Opus 解码最大约 3ms、sound0 write 最大约 1ms，没有解码/写声卡阻塞；真正异常是同一条状态里 `xz_listening=1`，也就是云端 TTS 播放时 M55 还在继续上行录音/编码。

修复：

1. `voice_service_pause_wake_for_tts()` 不再只关 wake listening；现在收到服务器 binary audio 或 TTS start 时会同时：
   - `xiaozhi_tts_speaking = RT_TRUE`
   - `xiaozhi_listening_active = RT_FALSE`
   - 清 `xiaozhi_voice_seen`
   - 清 `xiaozhi_voice_seen_frames`
2. 这样即使平台没有发标准 TTS start，只发 binary audio，也能立刻停止“边播边听”，避免采集/Opus 上行和 TTS 下行播放抢 M55 音频/CPU。

验证：

1. `python -m SCons -j8` 构建通过，当前大小：
   - `text=1682460 data=81404 bss=4528760`
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1765376 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 现场触发真实链路后，TTS 期间状态变为：
   - `xz_listening=0`
   - `xz_ws=1 xz_stage=70`
   - `tts_fwd=35/143360`
   - `tts_fail=0`
   - `srv_lens=0/8/0`
   - `srv_err=0x0002/0x0000 raw=0 hint=0x0000`
   - `tx_pending=0`

结论：

1. 这轮卡顿根因更像“播放时仍在上行采集/编码”的资源竞争，不是 WiFi、token、project、Opus decoder 或 sound0 write 阻塞。
2. 若后续仍主观卡顿，再看 `srv_lens` 的 replayq 高水位和 `srv_err/hint` 的 decode/write 峰值；如果这些仍低，就需要进一步查 sound0 底层 DMA/I2S 时钟或功放侧，而不是继续调 WebSocket。

## 71. 2026-06-27 中文 TTS 复位后仍卡：降低突发预缓冲和热路径状态上报

现象：

1. 现场反馈复位后服务器回来的中文语音仍然卡，且第二轮以后更明显。
2. 复位后状态仍健康：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `srv_hello=1`
   - `tts_fail=0`
3. 连续 QA 文本回合可复现本地播放压力：
   - 调整前连续 3 轮后 `srv_lens=0/8/0`
   - `tts_fwd=87/356352`
   - `srv_err=0x0002/0x0000`
   - 说明解码和 sound0 write 不慢，但 TTS pending 高水位被 8 包预缓冲顶满，播放线程以突发方式追赶，主观容易听成卡顿。

修复：

1. 保留 RT audio replay 底层增强：
   - `RT_AUDIO_REPLAY_MP_BLOCK_COUNT=8`
   - `CFG_AUDIO_REPLAY_QUEUE_COUNT=8`
   - `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096` 不改小，避免驱动写入块/flush 语义重新出问题。
2. M55 `voice_service.c` 调整 TTS 调度：
   - `VOICE_TTS_PREBUFFER_MIN_SLOTS 8 -> 4`
   - `VOICE_TTS_PREBUFFER_MAX_MS 520 -> 300`
   - `VOICE_TTS_PENDING_SLOT_COUNT 16 -> 24`
   - 每批最多处理 4 个 TTS payload 后 `rt_thread_mdelay(1)` 让出 CPU。
   - 播放热路径 `voice_service_publish_status()` 改为每 8 个转发 chunk 或失败时上报，避免每包状态上报抢播放时间。

验证：

1. `python -m SCons -j8` 构建通过，当前大小：
   - `text=1682476 data=81404 bss=4528824`
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1765376 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 启动状态：
   - `xz_ws=1 xz_stage=70 srv_hello=1`
   - `heap=1330928/1429160 max=1352904`
4. 连续两轮 `m55qa_xz_text` 后：
   - `xz_ws=1 xz_stage=70`
   - `srv_stt=2 srv_tts=0/2/0`
   - `xz_rx=10/107`
   - `tts_fwd=51/208896`
   - `tts_fail=0 pcm_reject=0`
   - `srv_lens=0/4/0`
   - `srv_err=0x0002/0x0000 raw=0 hint=0x0001`
   - `tx_pending=0`

结论：

1. 这版把 TTS pending 高水位从 8 压到 4，链路和连续回合保持稳定。
2. 该修复会增加 TTS pending heap 预算；当前启动后 heap 仍有约 96KB 余量，后续不要再盲目加大缓存。
3. 若现场仍听到卡顿，但上述字段仍保持低延迟/无失败，应继续查底层 I2S DMA/功放/供电或实际音频样本质量，不要回退到 WiFi/token/project 方向。

## 72. 2026-06-27 LVGL 跟着 TTS 一起卡：不是继续加缓存，而是释放 heap 和降低 TTS 侵占

现象：

1. 现场反馈服务器 TTS 仍卡，并且 LVGL 也一起卡。
2. 这说明问题不只是扬声器播放队列，而是 M55 用户体验线程也被拖慢。
3. 出问题状态：
   - `xz_ws=0 xz_stage=30` 曾在播放后掉线
   - `tts_fwd=151/618496`
   - `tts_fail=0`
   - `heap=1358464/1429160 max=1381400`
   - 只剩约 70KB heap 余量
4. 上一版把 `VOICE_TTS_PENDING_SLOT_COUNT` 从 16 加到 24 后，虽然 pending 高水位下降，但 heap 压力过大，LVGL/WebSocket/Opus/TTS 同时运行时反而卡。

修复：

1. 回收 TTS pending heap：
   - `VOICE_TTS_PENDING_SLOT_COUNT 24 -> 12`
2. 降低 TTS 线程对 UI/连接维护的侵占：
   - `VOICE_TTS_THREAD_PRIORITY 16 -> 21`
   - 低于 LVGL 的 20
   - `VOICE_TTS_PROCESS_MAX_PER_BATCH 4 -> 1`
3. 保留：
   - `VOICE_TTS_PREBUFFER_MIN_SLOTS=4`
   - `VOICE_TTS_PREBUFFER_MAX_MS=300`
   - replay pool/queue count 为 8

验证：

1. `python -m SCons -j8` 构建通过，当前大小：
   - `text=1682476 data=81404 bss=4528728`
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1765376 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 启动后状态：
   - `xz_ws=1 xz_stage=70 srv_hello=1`
   - `heap=1232624/1429160 max=1254600`
   - 空闲余量从约 70KB 恢复到约 196KB
4. 连续两轮 `m55qa_xz_text`：
   - `xz_ws=1 xz_stage=70`
   - `tts_fwd=77/315392`
   - `tts_fail=0 pcm_reject=0`
   - `srv_lens=1/4/0`
   - `tx_pending=0`
   - `lvgl_flush=932` 持续增长
5. 现场反馈：语音不卡了。

结论：

1. 本轮根因是 M55 上 TTS pending 缓存过大加上 `voice_tts` 优先级过高，导致 heap 和调度都压住了 LVGL/连接维护。
2. 不要再用“继续加缓存”修这个问题；M55 当前需要给 LVGL、WebSocket、Opus、wake 和后续小模型留余量。
3. 如果后续再次卡，先看 heap 余量、`lvgl_flush` 是否增长、`xz_ws` 是否保持 1，再看 `srv_err` 的 decode 峰值；不要直接回退 WiFi/token/project。

## 73. 2026-06-30 冷上电后 TTS 又卡：TTS 线程优先级 21 热态可用但冷启动余量不足

现象：

1. 现场反馈前一天调到“不卡”后，第二天重新上电服务器 TTS 又变卡。
2. 冷启动后检查确认配置没有回退：
   - `VOICE_TTS_PENDING_SLOT_COUNT=12`
   - `VOICE_TTS_PROCESS_MAX_PER_BATCH=1`
   - `RT_AUDIO_REPLAY_MP_BLOCK_COUNT=8`
   - `CFG_AUDIO_REPLAY_QUEUE_COUNT=8`
   - project 仍为 `e201f41c-25a6-46e1-baf8-be6dcb83284c`
3. 状态也不是 WiFi/token/project 问题：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `tts_fail=0 pcm_reject=0`
   - `srv_lens=0/4/0`
4. 真正异常是解码峰值：
   - 冷启动卡顿时 `srv_err=0x001e/0x0000` 或 `0x0021/0x0000`
   - 即 Opus 解码峰值约 30-33ms，一帧只有 60ms，留给 LVGL/wake/network/sound0 的余量太小。

排查：

1. 试过在 `voice_service_start()` 里提前初始化 Opus decoder 和 open M55 `sound0`，但首轮 QA 后 `srv_err` 仍可到 `0x0021/0x0000`，说明预热不是关键根因。
2. 关键变量是 `voice_tts` 优先级：前一版为了避免 LVGL 卡顿把 `VOICE_TTS_THREAD_PRIORITY` 降到 21，低于 LVGL 的 20；热态可用，但冷启动/忙态下 TTS 解码和喂声卡不够及时。

修复：

1. 保留资源安全设置：
   - `VOICE_TTS_PENDING_SLOT_COUNT=12`
   - `VOICE_TTS_PROCESS_MAX_PER_BATCH=1`
   - `VOICE_TTS_PREBUFFER_MIN_SLOTS=4`
   - `VOICE_TTS_PREBUFFER_MAX_MS=300`
2. 把 `VOICE_TTS_THREAD_PRIORITY` 从 21 调到 19：
   - 让 TTS 略高于 LVGL，避免 30ms 解码峰值后不能及时写入 sound0。
   - 仍保持每批只处理 1 个 payload，避免长时间饿住 LVGL。

验证：

1. `python -m SCons -j8` 构建通过，大小保持：
   - `text=1682476 data=81404 bss=4528728`
2. `program_with_resources.bat` 完整写入：
   - `rtthread.hex wrote 1765376 bytes`
   - `whd_resources_all.bin wrote 466944 bytes`
3. 连续两轮 `m55qa_xz_text` 验证过中间版本：
   - `xz_ws=1 xz_stage=70`
   - `tts_fwd=61/249856`
   - `tts_fail=0 pcm_reject=0`
   - `srv_lens=0/4/0`
   - `srv_err=0x0002/0x0000`
   - `lvgl_flush=973`
4. 撤掉无效预热后最终烧录版再跑一轮：
   - `xz_ws=1 xz_stage=70`
   - `tts_fwd=29/118784`
   - `tts_fail=0 pcm_reject=0`
   - `srv_lens=0/4/0`
   - `srv_err=0x0002/0x0000`
   - `lvgl_flush=547`

结论：

1. 这次“重新上电又卡”不是配置丢失，也不是平台/WiFi/token 退化。
2. 根因是 M55 冷启动/忙态下 Opus 解码峰值占用过高，而 `voice_tts` 优先级 21 低于 LVGL，导致 TTS 喂声卡调度余量不足。
3. 当前平衡点是：12 槽、每批 1 帧、`voice_tts` 优先级 19、replay pool/queue 8。

## 74. 2026-06-30 继续排查 TTS 卡顿：不要把 RT-Audio/I2S block 改成 2048，正确收敛点是 TTS 调度节拍

现象：

1. 现场继续反馈服务器回来的 TTS “还是很卡”，且曾出现越改越卡。
2. 云端链路本身健康：两轮 `m55qa_xz_text` 都能拿到 STT/TTS 文本，`tts_fail=0`、`pcm_reject=0`。
3. 曾尝试把 M55 TTS 写块从 4096B 改成 2048B，并尝试 TTS stop 后强制 close `sound0`，但现场反馈更卡。

关键结论：

1. 2048B 不是正确方向。`sound0` 的 `buffer_info.block_size` 虽是 2048B，但 I2S 驱动内部会把 mono PCM 转成 stereo playback buffer；应用层和 RT-Audio mempool 仍应保持 4096B 对齐，避免半帧/尾帧节奏变碎。
2. 不要在每轮 TTS stop 后粗暴 close/deinit `sound0`。这会引入收尾时序风险，可能让播放队列还没完全排空就被打断。
3. 本轮保留了只读诊断计数：
   - RT-Audio replay zero frame / partial underrun / queue push fail / mempool alloc fail
   - I2S TX underflow / zero fill / ready frame
   - 通过 `m55qa_status` 的 `srv_lens` / `srv_err` 和 `m55qa_tts_diag` 辅助定位。

最终修复：

1. 回到 4096B 播放写块：
   - `VOICE_TTS_M55_WRITE_BLOCK_SIZE=4096`
   - `RT_AUDIO_REPLAY_MP_BLOCK_SIZE=4096`
2. 不再修改 `sound_stop()` 的实际关停行为，只保留 I2S/RT-Audio 播放层计数器。
3. 调整 TTS 线程节拍，减少云端 60ms Opus 包到本地 4096B replay 块之间的排队空洞：
   - `VOICE_TTS_PREBUFFER_MIN_SLOTS=2`
   - `VOICE_TTS_PREBUFFER_MAX_MS=180`
   - `VOICE_TTS_THREAD_WAIT_MS=5`
   - `VOICE_TTS_PROCESS_MAX_PER_BATCH=4`
   - `VOICE_TTS_THREAD_PRIORITY=19` 保持不变。
4. 自动重连间隔从约 2s 收到 500ms，并在 TTS stop 后若发现 WebSocket 断开立即触发异步重连，减少 LVGL “连接中/离线”的可见窗口。

验证：

1. `python -m SCons -j8` 构建通过，最终 size：`text=1682924 data=81404 bss=4528756`。
2. `program_with_resources.bat` 烧录通过：`rtthread.hex wrote 1765376 bytes`，`whd_resources_all.bin wrote 466944 bytes`。
3. 两轮间隔 50s 的 `m55qa_xz_text`：
   - 两轮都有 `voice_ack cmd=1015 result=0`
   - 两轮都有 STT/TTS 文本
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `tts_fwd=51/208896`
   - `tts_fail=0 pcm_reject=0`
   - `srv_lens=0/0/194`
   - `srv_err=0x0002/0x0000`
   - `lvgl_flush=948`，说明 UI 仍在刷新。
## 75. 2026-06-30 M55 多轮卡死根因：不要在 WebSocket 回调里解析/转发服务器文本

现象：

1. 现场继续反馈“第二次直接卡死”“LVGL 跟着卡”“扬声器服务器语音卡”。
2. 串口两轮 `m55qa_xz_text` 复现到：
   - 第一轮能看到 `voice_ack cmd=1015 result=0`、ASR/TTS 文本；
   - 第一轮后 `voice_svc`、`frames/windows` 不再增长；
   - 第二轮命令表现为 `tx_pending=1`，M33 侧持续报 `cm55 voice status stale`。
3. WiFi/token/project/WebSocket 并没有退化：`xz_ws=1 xz_stage=70 xz_errno=0`、`token_len=468`、`srv_hello=1`。

根因：

1. 服务器文本消息原先直接在 WebSocket 收包回调里执行 `voice_service_handle_server_text()`。
2. 该处理会解析 JSON、更新 UI、向 M33 发布 ASR/TTS 文本、收尾 wake/listening 状态；这些重活不应放在网络回调上下文里。
3. 第一轮服务器文字/事件回来后，M55 `voice_svc` 停止推进，导致后续 M33->M55 控制消息排队，看起来像第二轮小智卡死或扬声器卡。

修复：

1. 增加 M55 服务器文本 ring buffer：`VOICE_SERVER_TEXT_SLOT_SIZE=384`、`VOICE_SERVER_TEXT_SLOT_COUNT=4`。
2. WebSocket 回调只复制服务器 JSON 文本入队，不再直接解析/转发。
3. `voice_service_thread_entry()` 每轮最多处理 2 条 pending server text，让 JSON 解析、M33 文本发布、UI 状态更新都回到 `voice_svc` 线程。
4. QA text 发送保持异步，避免 M33->M55 config/control 线程被 WebSocket send 阻塞。
5. 停止使用本地 Baidu TTS fallback；产品语音播放只认 XiaoZhi 平台返回的 binary audio/Opus 流，文字只用于 LVGL/M33 可视化。

验证：

1. `python -m SCons -j8` 构建通过，最终 size：`text=1683324 data=81404 bss=4530324`。
2. `program_with_resources.bat` 烧录通过：`rtthread.hex wrote 1769472 bytes`，`whd_resources_all.bin wrote 466944 bytes`。
3. 两轮 `m55qa_xz_text` 均通过：
   - 第一轮：`voice_svc=681`，`xz_rx=7/34`，`tts_fwd=15/61440`；
   - 延时后状态继续增长：`voice_svc=745`；
   - 第二轮：`voice_ack cmd=1015 result=0`，`voice_svc=1115`；
   - `tx_pending=0`，`xz_ws=1 xz_stage=70 xz_errno=0`，`tts_fail=0 pcm_reject=0`，`lvgl_flush` 持续增长。

后续判断顺序：

1. 如果再出现“第二轮卡死/连接跳/状态 stale”，先看 `voice_svc` 是否增长；若不增长，优先查回调上下文、锁、IPC publish，不要先改 WiFi/token/project。
2. 如果 `voice_svc` 增长且 `tts_fwd` 增长但听感仍卡，再回到 M55 sound0/I2S 平滑播放和本地 ring buffer。
3. 若平台只回文字不回 binary，板端不再伪造本地 TTS；应查平台 XiaoZhi relay 是否按官方 Opus 二进制返回音频。

## 76. 2026-06-30 现场再次卡顿：保留回调解耦时必须同步保留 31b696d 的播放节拍

现象：

1. 修完 WebSocket 回调重活后，现场先反馈“不卡了”，随后又反馈“又卡了”。
2. 对照 M55 镜像 diff 发现：server text queue 修复保住了，但 TTS 节拍仍是较保守的 `4 slots / 300ms / wait 20ms / batch 1`。
3. 这会降低 voice_tts 喂 `sound0` 的及时性，和云端 60ms Opus 包到本地 4096B replay 块之间产生空洞；表现为语音卡，但不一定伴随 WiFi/token/project 异常。

修复：

1. 保留第 75 节的 WebSocket 回调解耦，禁止回到回调里直接解析/转发 server text。
2. 同步恢复 commit `31b696d` 已验证过的播放平滑节拍：
   - `VOICE_TTS_PREBUFFER_MIN_SLOTS=2`
   - `VOICE_TTS_PREBUFFER_MAX_MS=180`
   - `VOICE_TTS_THREAD_WAIT_MS=5`
   - `VOICE_TTS_PROCESS_MAX_PER_BATCH=4`
   - `VOICE_TTS_M55_WRITE_BLOCK_SIZE=4096`
3. `m55qa_xz_text` 必须先发 `listen start(manual)` 再发带 text 的 `listen stop`，不能只发单条 stop；否则第一轮可能成功，后续轮次可能因为平台会话状态不在 listening 而只看到板端 ack、没有 STT/TTS/binary。
4. 这个组合的目标是同时解决两类问题：
   - 回调解耦解决第二轮卡死、`voice_svc` 不增长、`tx_pending=1`；
   - 31b696d 节拍解决播放空洞和服务器 TTS 卡顿。

后续判断：

1. 如果再次卡，先跑 `m55qa_status` 或 `m55qa_tts_diag` 看 `voice_svc`、`tts_fwd`、`tts_fail`、`pcm_reject`、`srv_err`、`lvgl_flush`。
2. `voice_svc` 不增长优先查线程/锁/回调上下文；`voice_svc` 增长但听感卡，优先查 `sound0`/I2S/RT-Audio 喂数平滑。
3. 不要因为听感卡直接回到 WiFi 扫描、token、project_id 或 NanoPi 方向。

## 77. 2026-06-30 现场反馈连接更不稳：恢复 31b696d 的快速重连收尾

现象：

1. 现场反馈“小智连接也不太稳定，而且语音贼卡”。
2. 烧录后状态复现到：WiFi/token 正常，`wlan=1 ready=1 token_len=468`，但 `xz_ws` 会短暂从 1 掉到 0，`xz_stage=30/80`，`xz_errno=-14`。
3. 这不是 WiFi 扫描、token 或 project_id 问题，而是 WebSocket 断开后的恢复窗口被拉长，导致用户看到连接跳和后续语音轮次不稳。

根因：

1. 第 76 节合并 QA text 完整轮次时，误把 commit `31b696d` 中的快速重连逻辑冲掉：
   - `XIAOZHI_RECONNECT_INTERVAL_MS=500` 被移除；
   - 线程自动重连退回约 2s；
   - TTS stop 后如果 WebSocket 已断开，不再立即触发 `voice_service_start_async_reconnect()`。
2. 这会让平台在 TTS/会话收尾后关闭连接时，板端可见的“连接中/离线”窗口变长。

修复：

1. 恢复 `XIAOZHI_RECONNECT_INTERVAL_MS=500`。
2. 恢复自动重连判断按 500ms 间隔触发，而不是固定约 2s。
3. 恢复 TTS `state=stop` 后的立即异步重连检查：
   - 如果 stop 后 `websocket_client_is_connected()==false`，立刻 `voice_service_start_async_reconnect()`。
4. 保留第 75 节 server text queue 和第 76 节播放节拍，不继续改扬声器参数。

验证：

1. `python -m SCons -j8` 构建通过，最终 size：`text=1683564 data=81404 bss=4530324`。
2. `program_with_resources.bat` 烧录通过：`rtthread.hex wrote 1769472 bytes`，`whd_resources_all.bin wrote 466944 bytes`。
3. 烧录后最初一次可见短暂 `xz_ws=0 stage=80 errno=-14`，随后 500ms 重连恢复。
4. 连续 6 次状态采样稳定：
   - `xz_ws=1 xz_stage=70 xz_errno=0`
   - `voice_svc` 持续增长
   - `lvgl_flush` 持续增长
   - `tx_pending=0`
   - `tts_fail=0 pcm_reject=0`

后续：

1. 如果现场继续反馈“语音卡”，先确认 `xz_ws` 是否持续 1；如果连接还在跳，优先查平台 close reason/心跳，不要继续调 TTS。
2. 如果 `xz_ws=1` 稳定且 `tts_fwd` 增长但听感仍卡，再查 `sound0`/I2S 播放平滑。
