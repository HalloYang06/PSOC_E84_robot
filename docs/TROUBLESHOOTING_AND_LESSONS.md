# Troubleshooting And Lessons

## 2026-06-24 - XiaoZhi Has Text Reply But No Speaker Voice Is A Playback Owner Issue

Symptoms:
- `m55qa_xz_text` triggers a real platform turn and the console shows:
  - `asr text: 你好，请说一句你已经准备好了`
  - `tts text: 我已经准备好了。`
- The speaker still has no intelligible human voice, or only a little noise.
- M55 direct `sound0` playback can stop M55 status/LVGL progress after TTS audio starts.

Root cause:
- This is not a WiFi/token/WebSocket/platform-entry failure.
- The platform path reaches ASR and TTS text successfully.
- The current speaker ownership is inconsistent:
  - M55 `sound0` direct playback can freeze the CM55 voice service path.
  - M33 `audio_playback_init()` returns `-RT_ENOSYS` because `BSP_USING_AUDIO` is disabled and logs `M55 owns sound0 for Xiaozhi`.

Fix / trick:
- Do not keep both M55 and M33 playback paths half-enabled.
- Current M55 stable build mutes binary TTS before Opus decode/playback, preserving UI, WebSocket, ASR text, and TTS text stability.
- If choosing M33 speaker, first enable/flash M33 `BSP_USING_AUDIO` and validate `audio_playback_probe_cmd`, then enable M55 `VOICE_TTS_PLAYBACK_TO_M33`.
- If choosing M55 speaker, first fix `sound0` replay/queue/tx-complete behavior with a local PCM/tone test, then enable M55 `VOICE_TTS_PLAYBACK_TO_M55`.

## 2026-06-23 - Connection jumping is not automatically WiFi/token failure

Symptoms:
- LVGL shows XiaoZhi reconnecting or jumps back to “连接中” after a voice turn.
- M55 status can still show healthy WiFi/token:
  - `wlan=1 ready=1`
  - `xz_token=1 token_len=442`
  - manual `m55qa_xz_reconnect` restores `xz_ws=1 xz_stage=70`
- A failing turn may show `srv_stt=1` but `srv_tts=0/0/0`, `tts_fwd=0/0`, `tts_fail=1`.

Root cause:
- This state means the link reached the platform side far enough for STT/event handling, but did not complete a playable TTS downlink.
- Treating every post-turn disconnect as WiFi/token loss wastes time and can hide the real TTS/platform issue.

Fix / trick:
- Keep WiFi/token untouched unless the known baseline really regresses.
- Use the new platform XiaoZhi telemetry fields:
  - `audio_bytes`
  - `sent_frames`
  - `sent_bytes`
- If `sent_bytes==0`, debug platform ASR/LLM/TTS. If `sent_bytes>0` but M55 `tts_fwd` stays zero, debug WebSocket/M55/M33 downlink.
- M55 now shows a retryable ready prompt after auto reconnect failure instead of repeatedly locking LVGL in “连接中”.

## 2026-06-23 - Official Protocol Reference Does Not Mean Changing The Custom Platform

Symptoms:
- The operator asked to reference the official Infineon/XiaoZhi behavior but still connect to the team's own platform.
- A risky M55 async reconnect experiment made the board stay at `xz_stage=20` after WiFi came back, and `m55qa_xz_reconnect` queued but did not recover the session.
- Reverting that experiment restored the known custom-platform baseline: `wlan=1`, `ip=192.168.3.32`, `xz_ws=1`, `xz_stage=70`, `token_len=442`.

Root cause:
- "Follow official XiaoZhi" is a protocol/audio-shape requirement, not a request to switch URLs/tokens.
- The M55 `voice_service` auto reconnect path is sensitive. Moving reconnect into a quick async thread without a full bridge/queue ownership audit can leave commands pending and prevent session recovery.

Fix:
- Keep the existing custom platform token/url untouched.
- Use official XiaoZhi protocol shape only for payload handling: JSON events plus Opus binary frames, including v3 framed binary payloads.
- Revert the M55 async reconnect experiment and keep the previously proven synchronous reconnect path.
- Add safer TTS handling instead: larger pending audio slots, v3 Opus frame splitting, slower M55->M33 TTS IPC pacing, and publish retry.

Validation:
- M55 stable build passed and was flashed. Final COM4 status returned to `xz_ws=1 xz_stage=70 xz_errno=0 token_len=442`.
- Real mic/v3 testing reached the custom platform and M33 speaker path: `xz_last=114/218880`, `xz_rx=3/3`, `tts audio rx total=1920`, and M33 wrote several speaker chunks.

Lesson:
- When the user says "official XiaoZhi, but my own platform", keep platform identity stable and only align protocol behavior. Do not change token/url while debugging voice-link robustness.
- If a reconnect refactor changes `xz_stage` from known-good `70` to stuck `20`, revert first and preserve the field baseline before deeper refactoring.

## 2026-06-23 - WebSocket Can Be Healthy While The M55 Mic Thread Is Stale

Symptoms:
- The operator reported LVGL still showed XiaoZhi not connected, while COM4 `m55qa_status` showed `xz_ws=1`, `xz_stage=70`, `xz_errno=0`, `token_len=442`, and `srv_hello` increasing after reconnect.
- After the M33 single-consumer change, one real-mic run ACKed `m55qa_capture_on` but did not upload audio: `xz_last=0/0`, `tts_fwd=0/0`.
- Status also showed mic counters no longer moving after capture: `frames` and `pcm_seq` stayed fixed, even though WiFi/token/WebSocket were healthy.

Root cause:
- M33 had two consumers for the M55 IPC RX queue: `main.c` and `voice_manager.c`. The `voice_manager` consumer could steal `VOICE_STATUS/ACK` frames before QA/status code saw them.
- Disabling the second consumer exposed a separate M55-side issue: `g_m55_mic.running` could remain true even when the mic thread was no longer producing frames. A later capture start then treated mic0 as busy and did not recreate the reader thread.

Fix:
- Keep M33 `main.c` as the single M55 IPC RX owner; `voice_manager_start()` now starts playback/wake init but does not start a second consumer thread.
- M55 mic0 now records `frame_count` and `last_frame_tick`.
- `m55_mic_start_internal()` treats a running mic with no frames for over 2 seconds as stale, clears the stale state, and recreates the mic reader thread.

Validation:
- M55 build passed and flash wrote `rtthread.hex` `1605632 bytes` plus WHD resources `466944 bytes`.
- After burn, `m55qa_status` showed `wake_on=1`, `xz_ws=1`, `srv_hello=1`, and moving mic counters: `frames=3380`, `pcm_seq=3380`.
- Real CM55 mic0 QA produced upload and downlink again: `xz_last=188/360960`, `xz_rx=3/7`, `tts_fwd=20/2432`.
- M33 printed platform TTS playback writes: `tts audio rx total=320`, `tts audio write`, then another `tts audio rx total=640`; final `tx_pending=0`.

Lesson:
- Do not diagnose this state as WiFi/token failure when `xz_ws=1`, `token_len=442`, and `srv_hello` are healthy. If capture ACKs but `frames/pcm_seq/xz_last` do not move, inspect the CM55 mic0 reader thread first.

## 2026-06-22 - Do Not Let Initial Silence End Real Mic XiaoZhi Capture

Symptoms:
- `m55qa_capture_on` ACKed successfully, but if the operator waited a few seconds before speaking, final status showed `xz_last=0/0`.
- In a lucky timed run, real mic speech did produce ASR text and `xz_last=57/109440`, proving mic0 and platform STT were basically alive.
- The reliable QA WAV path already returned TTS, so the remaining failure was product capture timing, not WiFi/token/platform reachability.

Root cause:
- M55 EOU used `xiaozhi_last_voice_tick = start_tick` and allowed silence-based EOU after the minimum record time.
- That meant initial silence after pressing capture could close the XiaoZhi session before the human started speaking.

Fix:
- Add an M55 `xiaozhi_voice_seen` session flag.
- Reset it on every XiaoZhi listen start.
- Only allow silence-based EOU after at least one voice frame has been observed. The max-record timeout still stops a truly silent session.

Validation:
- After rebuild/flash, field QA with real CM55 mic0 produced `xz_last=188/360960`, `xz_fail=0`.
- M33 received and wrote TTS audio: `tts audio rx total=640`, `audio_playback Started`, `tts audio idle flush chunks=5 bytes=640 ret=0`.
- Final status stayed healthy with `tx_pending=0`, `xz_ws=1`, `xz_stage=70`, `xz_errno=0`.

Lesson:
- For user-facing voice capture, distinguish "no speech yet" from "speech ended." Initial silence is common in manual tests and must not trigger EOU.

## 2026-06-22 - Compact Listen Diagnostics And Human QA Prove Downlink

Symptoms:
- A clean human WAV probe could upload all audio, but earlier status did not prove whether `listen/start` and `listen/stop` text frames were sent successfully.
- Expanding `voice_status_msg_t` to add more counters previously overflowed `.cy_sharedmem`.

Root cause:
- `voice_status_msg_t` is part of the fixed M33/M55 shared IPC message footprint. Adding fields there is unsafe on the current memory map.
- The missing proof was observability, not WiFi/token/IPC. The board baseline already had `xz_ws=1`, `token_len=442`, and accepted every QA frame.

Fix:
- Keep listen diagnostics internal to M55 and reuse existing status fields only while `srv_stt` and `srv_tts` are still zero:
  - `srv_lens = listen_start_count/listen_stop_count/start_ret`
  - low `srv_err = stop_ret`
- Do not grow shared structs for temporary diagnostics.

Validation:
- M55 build passed after the compact diagnostic change: `text=1533768 data=68744 bss=4541600`.
- M33 build passed with no shared-memory overflow: `text=474160 data=15344 bss=311877`.
- Human WAV QA sent `87` parts / `166974` bytes with `retries=0 tx_pending=0`.
- M55 accepted every packet and uploaded it: `probe_lwip=87/0`, `xz_last=151/289920`, `xz_fail=0`.
- M33 received and played the platform downlink: `tts audio rx total=320`, three `tts audio write` chunks, and `tts audio idle flush chunks=3 bytes=320 ret=0`.

Lesson:
- For this link, M33 `tts audio rx/write` is currently stronger proof than `srv_tts/tts_fwd`, because status counters lag the observed audio-forward path. Fix status accounting later, but do not block product validation on it.

## 2026-06-22 - Current Platform Accepts PCM Compatibility Better Than Opus

Symptoms:
- With `hello.audio_params.format=opus`, QA PCM was accepted by M55, encoded and uploaded, but the platform returned only listen/control text.
- PC smoke test logs showed the same e201 relay successfully returned STT when the client declared `pcm_s16le` and sent raw 1920-byte PCM frames.

Root cause:
- The board was following the official Opus route, but the current project relay/platform path already had a proven PCM compatibility contract.
- The board-side PCM attempt still differed from the PC smoke shape until the hello/start/stop payloads were matched exactly.
- M55 auto reconnect could also reset an active listening session during transient WebSocket state changes, causing QA to see `M55 not listening`.

Fix:
- Defaulted M55 to `pcm_s16le` for the current platform.
- In PCM mode, hello/start/stop now match the PC smoke test: `features.mcp` only, `listen/start mode=auto`, bare `listen/stop`.
- Auto reconnect no longer resets the XiaoZhi session while `xiaozhi_listening_active` is true.
- M33 QA waits longer for listening status after capture ACK.

Validation:
- Final COM4 QA produced real platform downlink to M33: `tts audio rx total=640`, `audio_playback Started`, and `tts audio write chunk=1/2/3`.
- Uplink evidence: `probe_lwip=50/0`, `xz_last=197/378240`, `xz_fail=0`, `tx_pending=0`.
- Link health stayed `xz_ws=1 xz_stage=70 xz_errno=0`.

Next lesson:
- For this relay, use PCM compatibility to finish product behavior first. Treat Opus as a later official-route upgrade unless platform relay logs prove Opus STT/TTS support is active.

## 2026-06-22 - XiaoZhi Stop Must Match The Start Mode

Symptoms:
- A healthy QA session could upload Opus (`probe_lwip=50/0`, `xz_last` grew, `xz_fail=0`) but the platform returned only listen/control text and no STT/TTS/binary audio.
- Prior project notes recorded successful manual QA around `listen start mode=manual` and `listen stop mode=manual`, but the current M55 stop builder had drifted back to a bare `{"type":"listen","state":"stop"}`.

Root cause:
- The stop message no longer preserved the active listening mode. Manual QA therefore ended with a stop shape that did not match the manual start shape.
- The stop builder also ignored the existing byte/chunk counters, leaving platform relay logs harder to correlate with board-side uplink evidence.

Fix:
- M55 now records `xiaozhi_listening_source` when a session starts.
- `xiaozhi_voice_relay_build_listen_stop()` now receives the source and emits `mode`, `audio_bytes`, and `audio_chunks`.
- Manual QA stop is `mode=manual`; realtime/local wake stop remains non-manual.

Validation:
- M55 build passed after the change: `text=1648696 data=68744 bss=4541600`.
- M33 build passed after QA wait hardening: `text=499512 data=15344 bss=311877`.
- M33 flash wrote `618496 bytes` and verified `617180 bytes`; M55 flash wrote app `1720320 bytes` plus WHD resources `466944 bytes`.
- Final QA sent the full 3000 ms deterministic PCM: `50` parts, `96000` bytes, `retries=0`, `tx_pending=0`.
- M55 accepted all frames and uploaded Opus: `probe_lwip=50/0`, `xz_last=207/37053`, `xz_fail=0`.
- Final link health stayed `xz_ws=1 xz_stage=70 xz_errno=0`, but there was still no STT/TTS/binary audio: `srv_stt=0`, `srv_tts=0/0/0`, `xz_rx=2/0`, `tts_fwd=0/0`.

Next diagnostic boundary:
- If the next burned QA still shows no `srv_stt/srv_tts/tts_fwd`, keep investigating XiaoZhi relay/protocol/platform logs. Do not fall back to WiFi scan, token reload, or resource firmware unless the known health indicators regress.

Additional QA lesson:
- `m55qa_capture_on` previously returned as soon as ACK arrived, but M33 could start `m33qa_xz_probe` before the fresh M55 status with `xz_listening=1` was consumed. Publish M55 status before ACK and make M33 QA wait briefly for `VOICE_STATUS_FLAG_XIAOZHI_LISTENING`; otherwise a valid capture start can be mistaken for `M55 not listening`.

## 2026-06-22 - M33 QA PCM Must Not Let CM55 Mic0 EOU Stop The Session

Symptoms:
- `m55qa_capture_on` ACKed successfully, but M55 accepted only part of the following QA PCM, or later showed `probe_lwip=accepted/ignored`.
- In some repeated runs `m33qa_xz_probe` continued after a failed capture and filled M33->M55 IPC (`tx_pending=5`), making `capture_off` fail with `ret=-28`.
- WiFi/token/WebSocket baseline remained healthy before the failed probe.

Root cause:
- The QA PCM path uses M33 deterministic PCM, but M55 was still running CM55 mic0 automatic EOU on the same XiaoZhi listening session.
- Silent CM55 mic0 frames could stop the platform session before or during M33 QA PCM injection.
- The QA tool also trusted the previous control command too much; if M55 was no longer listening, probe audio could still be published into the IPC queue.

Fix:
- While `m33_pcm_probe_enabled` is true, M55 skips CM55 mic0 automatic EOU and leaves session termination to explicit `m55qa_capture_off`.
- `m33qa_xz_probe` now reads M55 `voice_status` before sending PCM and aborts unless `VOICE_STATUS_FLAG_XIAOZHI_LISTENING` is set.
- M55 manual listen start attempts reconnect if the WebSocket is disconnected at the final send point.

Validation:
- Final 3000 ms QA had `capture_on ack=0`, `capture_off ack=0`, and `tx_pending=0`.
- M55 accepted all 50 M33 QA PCM packets: `probe_lwip=50/0`.
- XiaoZhi uplink advanced: `xz_last=81/14499`, `xz_fail=0`.
- Final link health stayed `xz_ws=1 xz_stage=70 xz_errno=0`.

Next diagnostic boundary:
- If `probe_lwip=50/0` and `xz_last` grows but `srv_stt/srv_tts/tts_fwd` stay zero, stop debugging IPC/WiFi/token and inspect XiaoZhi platform protocol after `listen/start`.

## 2026-06-22 - `capture_on ack=-116` Can Be A Repeated-Hello Race

Symptoms:
- `m55qa_status` showed the baseline was healthy after startup: `xz_ws=1`, `xz_stage=70`, `xz_errno=0`, `srv_hello=1`, `token_len=442`, `wlan=1`.
- `m55qa_probe_pcm_on` ACKed, but `m55qa_capture_on` returned `ack=-116`.
- Because capture never entered active listening, the following QA PCM was correctly ignored: `probe_lwip=0/50` or higher ignored counts, and `xz_last=0/0`.

Root cause:
- Talk start sent or waited for another hello even though the current runtime had already received server hello.
- The fallback previously required `websocket_client_is_connected()` to be true at the exact timeout check. A transient false during the wait could still return `-RT_ETIMEOUT` even though later status showed `xz_ws=1`.

Fix:
- `voice_service_start_xiaozhi_talk()` now treats `xiaozhi_server_hello_count > 0` as sufficient prior-hello evidence after repeated hello timeout, restores `hello_seen`, and then lets `voice_service_start_xiaozhi_manual_listening()` perform the live WebSocket check before sending `listen/start`.

Validation:
- After the fix, 3000 ms QA returned `capture_on ack=0`, `capture_off ack=0`, `tx_pending=0`.
- M55 accepted all 50 QA PCM packets: `probe_lwip=50/0`.
- XiaoZhi uplink counters advanced: `xz_last=84/15036`, `xz_fail=0`.
- Final link health remained `xz_ws=1 xz_stage=70 xz_errno=0`.

Next diagnostic boundary:
- If `capture_on ack=0` and `probe_lwip=50/0` but `srv_stt/srv_tts/tts_fwd` stay zero, inspect XiaoZhi platform event/protocol behavior.
- Do not treat this pattern as WiFi/token/resource regression unless `wlan`, `xz_ws`, `token_len`, or reconnect health also degrade.

## 2026-06-22 - Keep M33/M55 Voice Status Compact

Symptoms:
- Adding six new `uint32_t` server-event fields to `voice_status_msg_t` made the M33 build fail during link:
  - `.cy_sharedmem will not fit in region m33_allocatable_shared`
  - `region m33_allocatable_shared overflowed by 116 bytes`

Environment:
- M33 repo: `D:\RT-ThreadStudio\workspace\yiliao_m33`, branch `M33`.
- M55 active burn tree: `D:\RT-ThreadStudio\workspace\wifi`.
- Shared queue payload uses `m33_m55_message_t`, so every field added to `voice_status_msg_t` affects shared-memory queue footprint.

Root cause:
- `voice_status_msg_t` is carried inside `m33_m55_message_t`, and the IPC queue stores several messages in shared memory. A small field increase is multiplied by queue depth and can overflow the fixed shared-memory region.

Fix:
- Compressed the new event diagnostics:
  - packed `text/content/speak` lengths into one `uint32_t`;
  - kept compact four-byte `error` and `reason` codes;
  - left the third printed error-code slot as `0` for now.

Validation:
- M33 build passed after compaction: `text=495660 data=16076 bss=311144`.
- M55 build passed and a 1200 ms QA run showed the new `srv_lens` / `srv_err` fields on COM4.

Reusable trick:
- Before adding fields to M33/M55 IPC structs, estimate queue footprint and build both sides.
- Prefer packed counters or reusing existing diagnostic fields for temporary QA observability.

Status:
- Fixed. New event observability is available without overflowing shared memory.

## 2026-06-22 - Wait For XiaoZhi QA Control ACK Before Sending Probe PCM

Symptoms:
- A 3000 ms `m33qa_xz_probe` run failed at part 4 with repeated `ret=-28` even after probe pacing had been slowed.
- In that failing run, `m55qa_capture_on` returned before a fresh `cmd=1` ACK appeared, then probe PCM filled the 5-deep M33->M55 queue. `m55qa_capture_off` then returned `ret=-28`.
- WiFi/token/WebSocket were still healthy: `xz_ws=1`, `xz_stage=70`, `token_len=442`, `wlan=1`.

Environment:
- M33 repo: `D:\RT-ThreadStudio\workspace\yiliao_m33`, branch `M33`.
- M55 active burn tree: `D:\RT-ThreadStudio\workspace\wifi`.
- Bench shell: COM4 KitProg3 USB-UART at 115200.

Root cause:
- `m55qa_capture_on` and related QA commands only waited for publish success, not for a fresh M55 `voice_ack`.
- The shell script could start `m33qa_xz_probe` while START_CAPTURE was still queued. Because the queue depth is 5, four PCM packets plus a pending control command were enough to starve STOP_CAPTURE.

Fix:
- `m55qa_probe_pcm_on`, `m55qa_capture_on`, `m55qa_capture_off`, and `m55qa_probe_pcm_off` now wait for a fresh matching `voice_ack` before returning.
- `m33qa_xz_probe` now waits for `tx_pending=0` before sending PCM, and aborts after a bounded drain wait instead of filling an already busy queue.

Validation:
- After the fix, `m55qa_probe_pcm_on` ACKed `cmd=11`, `m55qa_capture_on` ACKed `cmd=1`, and `m55qa_capture_off` ACKed `cmd=2`.
- `m33qa_xz_probe 3000` sent 50 parts / `96000` bytes with `retries=0 tx_pending=0`.
- Final status stayed healthy: `xz_ws=1 xz_stage=70 xz_errno=0`, and `tx_pending=0`.

Reusable trick:
- In this QA flow, publish success is not enough. Wait for fresh `voice_ack` before sending probe PCM.
- If OpenOCD reports `wrote 0 bytes` and `no flash bank found for address 0x60340400`, the command missed the board `qspi_config.cfg`; source `libs/TARGET_APP_KIT_PSE84_EVAL_EPC2/config/GeneratedSource/qspi_config.cfg` before `target/infineon/pse84xgxs2.cfg` so `cat1d.cm33.smif1_ns` exists.

Status:
- QA sequencing race is fixed. Remaining product work is real CM55 mic0 human-speech QA and platform event/downlink interpretation, not WiFi/token.

## 2026-06-22 - Throttle `m33qa_xz_probe` Before Blaming XiaoZhi WiFi Or Token

Symptoms:
- Before this fix, a short deterministic `m33qa_xz_probe` could fail after only a few 1920-byte PCM notifications with `ret=-28`.
- When that happened, `m55qa_capture_off` could also fail or remain queued, even while `m55qa_status` still showed healthy WiFi/token/WebSocket fields.

Environment:
- M33 repo: `D:\RT-ThreadStudio\workspace\yiliao_m33`, branch `M33`.
- Active M55 burn tree remained `D:\RT-ThreadStudio\workspace\wifi`.
- Bench shell: COM4 KitProg3 USB-UART at 115200.
- Baseline health in this pass: `wlan=1 ready=1`, `xz_token=1 token_len=442`, `xz_ws=1`, `xz_stage=70`, `xz_errno=0`.

Root cause / current hypothesis:
- `m33qa_xz_probe` was sending 60 ms / 1920-byte shared-PCM notifications into a shallow M33->M55 IPC queue.
- The probe is a deterministic stress tool, not the product audio path; when sent too fast it can compete with stop/control/status traffic and make a good XiaoZhi baseline look broken.

Fix:
- M33 `m33qa_xz_probe` now waits 100 ms between frames.
- On transient queue full/timeout/no-space returns, it backs off 150 ms and retries up to 4 times before failing.
- Probe logs now report retry attempts, `tx_pending`, and final sent/retry totals.

Validation:
- `m33qa_xz_probe 1200` sent 20 parts / `38400` bytes with `retries=0 tx_pending=0`; `m55qa_capture_off` returned fresh `voice_ack cmd=2 result=0`.
- `m33qa_xz_probe 3000` sent 50 parts / `96000` bytes with `retries=0 tx_pending=0`; `m55qa_capture_off` returned fresh `voice_ack cmd=2 result=0`.
- The 3000 ms run also produced M33 downlink evidence: `tts audio rx total=1280` and `tts audio write chunk=...`.
- Final status after the 3000 ms run stayed at `xz_ws=1 xz_stage=70 xz_errno=0`, with `tx_pending=0`.

Reusable trick:
- If `m33qa_xz_probe` shows `ret=-28`, check probe pacing and `tx_pending` before touching WiFi, token, WHD resources, or platform credentials.
- If `wlan=1`, `token_len=442`, `xz_ws=1`, and `xz_stage=70` are present, stay on the audio/session/IPC layer.
- Product validation should still prefer real CM55 mic0; use M33 probe only for deterministic platform/downlink QA.

Status:
- QA probe starvation is fixed for 1200 ms and 3000 ms probe lengths in this pass.
- Remaining open issue: one 1200 ms run left `xz_ws=0 xz_stage=80` until explicit `m55qa_xz_reconnect`; the later 3000 ms run stayed connected. Treat this as XiaoZhi session stop/reconnect behavior, not WiFi/token failure.

## 2026-06-20 - XiaoZhi Downlink Reached M33, But Generic Async Speaker Worker Asserted

Symptoms:
- QA-only XiaoZhi probe produced platform downlink audio on M33: `tts audio rx total=1280`, `audio_playback Started`, and `tts audio write chunk=...`.
- The experimental async playback worker then hit `(rt_object_get_type(&timer->parent) == RT_Object_Class_Timer) assertion failed at function:rt_timer_stop, line number:546`.
- After the assertion, the shell stopped responding until reset/reflash.

Root cause / current hypothesis:
- The platform/model path is not the blocker once M33 logs `tts audio rx total=...`; downlink audio reached M33.
- The generic async worker changed the timing/threading model around the RT-Thread audio device and likely violated the sound driver timer/thread expectations.

Fix/status:
- Rolled back the async playback worker and reflashed the stable M33 image.
- Keep the M55 TTS truncation removal and QA probe controls; do not keep the generic async speaker worker.

Reusable trick:
- Do not assume `rt_device_write(sound0, ...)` is safe from an arbitrary worker thread on this board.
- If XiaoZhi sits at "thinking" but M33 shows `tts audio rx total=...`, debug M33 speaker playback before changing WiFi, token, or WebSocket protocol again.

## 2026-06-20 - Use M33 PCM Probe Only Behind An Explicit QA Gate

Symptoms:
- With no现场人声, CM55 mic0 uploads mostly low-energy frames and the platform may not return STT/TTS.
- The deterministic `m33qa_xz_probe` is useful for proving cloud/downlink but can confuse the product architecture and pressure IPC queues.

Fix/status:
- Added `m55qa_probe_pcm_on` / `m55qa_probe_pcm_off`.
- M55 accepts M33 PCM probe audio only when the QA gate is enabled and a XiaoZhi listening session is active.
- `m55qa_probe_pcm_on` was validated with `voice_ack cmd=11 result=0`.

Reusable trick:
- Use `m55qa_probe_pcm_on -> m55qa_capture_on -> m33qa_xz_probe -> m55qa_capture_off` only for deterministic QA.
- Product path remains CM55 local `mic0 -> Opus -> WebSocket -> platform -> M33 TTS audio`.

## 2026-06-19 - Rehab Bench Motion Needs Current Mode And Bounded Adaptive PID

Symptoms:
- `cmd_motor_speed` or speed-hold commands returned success, but joint 5 barely moved or did not move under the real elbow load.
- Raising the speed command's `limit_cur` did not behave like commanding motor current.
- Fixed assist/resist gains felt too flat when load and velocity changed.

Root cause:
- `limit_cur` is a speed/position limit, not a forced current output.
- For the current joint 5 RS00 bench setup, the useful low-level actuator proof is current mode: set `run_mode=current` and write `iq_ref(0x7006)`, with an explicit current cap.
- Plain fixed gain cannot distinguish sustained load from faster motion, so it needs either manual gain scheduling or a bounded adaptive outer loop.

Fix:
- Added `control_motor_current_control()` and `cmd_motor_current_hold` for local MSH bench validation.
- Changed rehab active, assist, and resist strategies to output `REHAB_STRATEGY_OUTPUT_CURRENT`.
- Added runtime rehab service parameters for follow direction, active/assist current gain, resist damping gain, and current caps.
- Added optional load/speed scheduled adaptive PID for assist/resist. It is default-off, resets integral state on mode/parameter changes, and limits PID trim current separately from the hard mode current cap.

Reusable trick:
- When motor feedback is fresh and command return is `0` but loaded motion is absent, separate "command accepted" from "actuator produced useful torque/current".
- For RS00 current-mode tests, prove motion first with `cmd_motor_current_hold 5 0.5 500 20`, then move up to rehab modes.
- If assist/resist feels weak, check `sat`, `pid_trim_x1000`, `pid_load_x1000`, and `pid_speed_x1000` before raising gains.
- Keep MSH bench bypass separate from NanoPi heartbeat bypass: bench may bypass heartbeat, but it must not bypass fresh feedback, current limits, stop, or memory playback calibration.

## 2026-06-20 - Do Not Use M33 PCM Probe As The Product XiaoZhi Audio Path

Symptoms:
- Wi-Fi, token, and WebSocket can all be healthy while `m33qa_xz_probe` later causes `m55qa_capture_off` to queue up with no fresh ACK.
- Typical healthy baseline before the stress case: `wlan=1 ready=1`, `xz_ws=1`, `xz_stage=70`, `xz_errno=0`, `token_len=442`.
- After probe/TTS pressure, `m55qa_status` can stop refreshing at a fixed `probe_or_bridge` value while `tx_pending` grows.

Evidence:
- The real CM55 mic path passed start/stop control after reset: fresh `voice_ack cmd=1`, fresh `voice_ack cmd=2`, and `tx_pending=0`.
- The probe path can prove cloud and speaker wiring because M33 saw `tts audio rx` and `tts audio write`, but it also pushes many PCM notifications through the same IPC queues used by control/status.

Root cause / current hypothesis:
- `m33qa_xz_probe` is useful as a deterministic stress/bring-up tool, but it is not the official product audio route. It competes with control/status/TTS traffic on M33/M55 IPC and can expose queue/priority issues that a CM55-local mic flow avoids.

Fix / lesson:
- Keep product XiaoZhi on CM55 `mic0` capture and official Opus WebSocket uplink.
- Keep `m33qa_xz_probe` short by default and use `m33qa_xz_probe full` only when deliberately stress-testing IPC/TTS behavior.
- When diagnosing "waiting platform" after the baseline is healthy, check `voice_ack`, `tx_pending`, `xz_last`, `xz_rx`, `tts_fwd`, and M33 `tts audio rx/write` before going back to Wi-Fi resources.

Status:
- Product control path improved; full stable TTS playback remains open.

## 2026-06-20 - XiaoZhi Reached Speaker Playback; Remaining Stall Is IPC/TTS Cleanup Pressure

Symptom:
- Earlier runs stayed at `已发送，等待平台模型` / `正在思考`, and `m55qa_capture_off` sometimes returned from the shell while `tx_pending` stayed nonzero and no fresh `cmd=2` ACK arrived.
- After a long `m33qa_xz_probe`, the platform could reply and M33 could play TTS, but a later manual `m55qa_capture_off` still left `tx_pending=1`.

Evidence:
- Wi-Fi/token/WebSocket were healthy during the failing runs: `saved=1 auto=1 storage=0`, `wlan=1 ready=1`, `xz_ws=1`, `xz_stage=70`, `xz_errno=0`, token length `442`.
- Short capture start/stop passed after stopping `mic0`: fresh `voice_ack cmd=1 result=0`, fresh `voice_ack cmd=2 result=0`, and `tx_pending=0`.
- Built-in deterministic probe passed upstream and downlink once: `m33qa_xz_probe` completed all PCM parts, CM55 uploaded Opus (`xz_last=180/32220`), and M33 printed `tts audio rx total=320`, `audio_playback Started`, and `tts audio write` chunks.
- The post-reply stall appears only after TTS/downlink traffic and follow-up control messages, not during Wi-Fi association or token loading.

Root cause / current hypothesis:
- The old manual stop path did not stop CM55 `mic0`, so capture and voice processing could continue after a UI/QA stop.
- Auto EOU previously sent `listen.stop` synchronously from the voice detection path, which could block behind WebSocket/lwIP send work.
- After the new fixes, the remaining long-probe stall is likely M33<->M55 IPC pressure while CM55 publishes TTS audio/status back to M33 and M33 sends a follow-up stop control. It is a queue/priority cleanup issue, not the original Wi-Fi scan/resource/token problem.

Fixes applied:
- `VOICE_CTRL_STOP_CAPTURE` now calls `m55_mic_stop_internal()` before local XiaoZhi stop/abort.
- Manual QA capture uses official `listen start` with `mode=manual`; `listen stop` also carries `mode=manual`.
- Auto EOU now clears local listening state and sends `listen.stop` in an `xz_stop` background thread.

Lessons:
- Do not judge `m55qa_xz_reconnect ret=0` as a successful WebSocket connection; it only means the async reconnect worker was queued. Confirm with `m55qa_status` fields `xz_ws=1`, `xz_stage=70`, `xz_errno=0`.
- Once `m33qa_xz_probe` produces M33 `tts audio rx/write`, the cloud model and speaker path are no longer theoretical. Continue from IPC/TTS cleanup, not from Wi-Fi provisioning.
- For user-facing XiaoZhi, CM55-local mic capture is still the main path. The M33 built-in probe is a deterministic QA tool and can stress the IPC queues more than the real mic path.

## 2026-06-19 - XiaoZhi Stayed In "Waiting Platform Model" While Device Identity Was Still Hardcoded

Symptom:
- CM55 could connect Wi-Fi, but XiaoZhi still sat at `已发送，等待平台模型` / `正在思考`.
- The UI looked frozen because the panel had no real server progress to display after the wake/listen transition.

Evidence:
- The CM55 WebSocket client was still sending fixed `Device-Id: nanopi-m5` and `Client-Id: rehab-arm-alpha` in the handshake headers.
- Official XiaoZhi docs say `Device-Id` must be the physical MAC and `Client-Id` must be a generated UUID.
- The official reference implementation also uses the MAC/UUID split in its WebSocket setup.

Root cause:
- The device-side handshake identity was only partially aligned with the official contract, so the session could get stuck in a state that looked like a model wait rather than a local Wi-Fi failure.

Fix:
- Generate `Device-Id` from the current netdev MAC.
- Generate a persistent `Client-Id` once and store it on flash.
- Keep the official `hello` payload at `version=1`, `transport=websocket`, and `audio_params.format=opus`.

Lesson:
- When XiaoZhi appears to be "thinking forever", check the handshake contract first: headers, `hello`, and server `hello` sequencing before blaming LVGL.

## 2026-06-19 - LVGL Looked Frozen Because XiaoZhi Start/Stop Ran In The UI Callback

Symptom:
- On the XiaoZhi Wi-Fi/LVGL screen, tapping `说话` left the page stuck in `正在思考` / `正在启动小智`, and touch input on the whole panel felt dead.

Evidence:
- `rehab_wifi_panel.c` called `m55_xiaozhi_talk_start_from_ui()` and `m55_xiaozhi_talk_stop_from_ui()` directly from the LVGL click callbacks.
- `voice_service_start_xiaozhi_talk()` can reconnect Wi-Fi/WebSocket and wait for server `hello`, so it is not a safe thing to do inside the UI thread.

Root cause:
- The panel was not truly “thinking”; the LVGL event callback was synchronously running the XiaoZhi bring-up path, which can block long enough to starve touch redraw and make the screen feel frozen.

Fix:
- Move XiaoZhi panel start/stop into a small background worker thread and let the LVGL callback only queue the action.
- Keep the UI state update immediate, but do not let the click handler itself wait on hello/reconnect.

Lesson:
- Any button that may reconnect, wait for hello, or start audio capture should be queued to a worker. LVGL callbacks must stay quick.

## 2026-06-17 - CM55 XiaoZhi Assert Was Status/IPC Pressure, Not Wi-Fi

Symptom:
- After XiaoZhi probe or repeated `m55qa_capture_on` / `m55qa_capture_off`, M33 shell stayed alive but `m55qa_status` showed stale `voice_status age_ticks` and new commands accumulated in `tx_pending`.
- OpenOCD showed CM55 halted in `rt_assert_handler`.

Evidence:
- One CM55 stack mapped through `addr2line` to `voice_service_publish_status -> voice_service_refresh_netdev_snapshot_locked -> rt_wlan_dev_get_rssi -> WHD ioctl -> rt_mutex/IPC`.
- A later stack mapped to `voice_service_publish_status -> m33_m55_comm_publish -> mtb_ipc_queue_put`, where the MTB IPC library asserts if a blocking timeout is used from an invalid context.

Root cause:
- The voice/status hot path was doing too much work: live Wi-Fi driver queries and blocking IPC queue publish from the same control/audio bring-up loop.
- This looked like "小智没回话" or "Wi-Fi卡住", but the actual failure was CM55 falling into an RT-Thread assert after status/IPC pressure.

Fix:
- `voice_service_publish_status()` now uses the Wi-Fi config snapshot and no longer calls live WLAN/RSSI queries while publishing status.
- CM55 `m33_m55_comm_publish()` now calls `mtb_ipc_queue_put(..., 0)` so queue full/invalid timing returns an error instead of asserting the core.
- TTS binary payload handling remains deferred out of the lwIP WebSocket callback and is drained by the voice service thread.

Validation:
- After rebuild/burn, repeated `m55qa_capture_on` / `m55qa_capture_off` over COM4 returned ACKs, `tx_pending` returned to 0, and status remained fresh.
- Wi-Fi auto-connect still recovered after reset with saved credentials and `xz_ws=1`.

Next diagnostic:
- Re-run a prompt that reliably causes platform binary TTS. Pass criteria are `xz_rx` binary increment, `tts_fwd` increment, M33 `tts audio rx/write`, and audible speaker output.

## 2026-06-17 - CM55 Speaker Init Can Kill The Voice Service Before Mic QA Starts

Symptom:
- CM55 would boot into an assert instead of staying alive for XiaoZhi status and wake/capture QA.
- `m55qa_status` could fall back to shallow or stale output, and control commands would stop getting consumed.

Root cause:
- The M55 `sound0` / I2S init path asserted inside `ifx_i2s_init()` when `Cy_AudioTDM_Init()` failed.
- That speaker path is not required for the CM55-local XiaoZhi mic-first workflow, but it was still part of the CM55 boot path.

Fix:
- Remove `drv_i2s.c` from the M55 build for now.
- Keep CM55 on `mic0` / PDM capture for XiaoZhi uplink audio.
- Let the M33 side own speaker playback and keep CM55 focused on status, wake, capture, and network control.

Lesson:
- When a board has separate capture and playback responsibilities, do not let a failing speaker init block microphone bring-up.
- For this project, CM55 should be the audio input worker, not the whole audio stack.

## 2026-06-16 - Board ASR Is Proven; Remaining Gap Is TTS Downlink/Playback

Symptom:
- After Wi-Fi and WebSocket were stable, XiaoZhi still looked stuck or silent from the user perspective.
- Earlier board runs either produced no reply or forwarded garbled bytes as `tts text`.

Findings:
- The CM55 Wi-Fi/WebSocket path is healthy when `m55qa_status` shows `wlan=1 ready=1`, `xz_ws=1`, `xz_stage=70`, and `xz_errno=0`.
- Sending raw `pcm_s16le` from M33 via `m33qa_xz_probe` now reaches cloud ASR. Board logs show ASR text on M33 and `xz_last` byte/chunk counters increase.
- A PC-side control test using the same platform endpoint, scoped token, `Protocol-Version: 3`, `hello.audio_params.format=pcm_s16le`, and raw PCM frames returns the complete cloud sequence: `stt`, `llm`, `chat`, `tts start`, binary PCM TTS frames, `tts stop`.
- Therefore the current blocker is not Wi-Fi, token, WebSocket connect, or upstream ASR. The remaining gap is board-side TTS downlink classification/forwarding and `sound0` playback validation.

Fixes applied:
- CM55 no longer prefixes outbound raw PCM with a fake local v3 header.
- The M33-to-M55 shared PCM route now forwards non-control IPC messages into `voice_service_handle_ipc_message()`.
- Shared PCM is accepted while XiaoZhi listening is active, not only while wake listening is active.
- Non-JSON text-opcode WebSocket payloads are no longer published to M33 as `MSG_TYPE_TTS_REQUEST` garbage. PCM-looking payloads are routed as audio instead.

Next diagnostic:
- Run `m55qa_capture_on`, `m33qa_xz_probe`, then watch for `xz_rx` binary count and M33 `MSG_TYPE_TTS_AUDIO` / `audio_playback_write()` logs.
- If PC still receives binary TTS but board does not, instrument the CM55 lwIP WebSocket callback around opcode/text/binary classification.
- If board receives `MSG_TYPE_TTS_AUDIO` but no sound, focus only on M33 `audio_playback` and `sound0`, not cloud or Wi-Fi.

## 2026-06-15 - XiaoZhi Binary Frames Stayed Silent Because The PCM Path Was Still Wrapped Wrong

Symptom:
- XiaoZhi stayed in `connecting` / `thinking` with no reliable `listen -> send -> reply` progress.
- Status counters showed mic activity, but there was no clear evidence that the platform actually received binary audio.

Findings:
- The M55 WebSocket client already sends binary frames with `OPCODE_BINARY`; adding a fake 4-byte v3 header on top of raw PCM made the send path harder to reason about.
- The official XiaoZhi WebSocket reference supports binary protocol v1 as raw audio frames, while v2/v3 framing is only needed when both sides explicitly agree on that binary protocol.
- The current board-side practical path is raw `pcm_s16le` over binary WebSocket frames, with explicit JSON `hello`/`listen` control messages and status counters.

Fix:
- Remove the extra binary header and send the raw 16 kHz mono PCM bytes directly.
- Expose `xiaozhi_listening_bytes`, `xiaozhi_listening_chunks`, `xiaozhi_last_sent_bytes`, `xiaozhi_last_sent_chunks`, `xiaozhi_send_fail_count`, `xiaozhi_rx_text_count`, `xiaozhi_rx_binary_count`, and `xiaozhi_audio_frame_len` in `m55qa_status`.

Lesson:
- When the platform contract already says `pcm_s16le`, do not stack another framing layer unless the server explicitly requires it.
- Make the audio path observable before tuning wake/EOU thresholds; otherwise every failure looks like the same "still connecting" symptom.

Status:
- Fixed in the working tree; board QA still needed after the next burn.

## 2026-06-15 - XiaoZhi Cloud Blocker Is WebSocket Transport, Not Wi-Fi

Symptom:
- CM55 Wi-Fi auto-connect is stable and `m55qa_status` shows a valid IP/gateway/DNS, but XiaoZhi remains in connecting state.
- Early diagnostics made it look like `connect()` was hanging forever.

Findings:
- A dedicated CM55 TCP probe to `106.55.62.122:8011` succeeds, proving basic Wi-Fi association, DHCP, gateway, and outbound TCP are working.
- A PC-side raw WebSocket Upgrade using the same URL and scoped token returns `HTTP/1.1 101 Switching Protocols`, so the cloud endpoint, token, and path are valid.
- The CM55 hand-written socket client can send the HTTP Upgrade request, then reaches handshake receive (`xz_stage=50`) and blocks/timeouts in the RT-Thread/lwIP socket receive path.
- `select()`, `fcntl(O_NONBLOCK)`, `MSG_DONTWAIT`, `SO_RCVTIMEO`, direct `lwip_recv`, and `FIONBIO` did not produce a dependable nonblocking receive on this BSP path.

Lesson:
- Do not keep debugging this as a Wi-Fi scan/firmware-resource issue once `wlan=1 ready=1 ip=192.168.3.32` and the TCP probe passes.
- Avoid building the XiaoZhi production transport on the POSIX/SAL socket receive path for this board. Use the bundled lwIP callback WebSocket client (`lwip/apps/websocket_client.h`) or a netconn/raw callback API.

Validation notes:
- M55 image and WHD resources were flashed together after each iteration.
- COM4 QA showed Wi-Fi auto-connect remained stable after reset.
- The scoped relay token must not be printed or committed.

## 2026-06-10 - LVGL Code In Image Does Not Mean The GUI Thread Started

Symptom:
- CM55 firmware built successfully with `BSP_USING_LVGL`, `rehab_wifi_panel_cmd` existed in the symbol table, but no LVGL screen appeared on boot.

Root cause:
- The RT-Thread LVGL port had `INIT_ENV_EXPORT(lvgl_thread_init)` commented out.
- `lvgl_thread_init()` was only exported as the shell command `thread_init`, so the GUI thread did not start automatically.

Fix:
- CM55 `main()` now calls `lvgl_thread_init()` during boot when `BSP_USING_LVGL` is enabled.
- `lvgl_thread_init()` now has a duplicate-start guard so manually typing `thread_init` remains safe.
- The LVGL RT-Thread port now includes `<lvgl.h>` directly to avoid implicit LVGL API declarations.

Validation:
- M55 reference repo and actual RT-Thread Studio `wifi` project both build with `scons -j4`.

Reusable trick:
- If LVGL is compiled in but the screen is blank, first type `thread_init` in the shell. If the screen appears, the issue is GUI-thread startup, not the Wi-Fi panel code.
- If `thread_init` starts but the screen remains blank, run `lcd_test` next to separate display hardware/driver issues from LVGL widget issues.

Status:
- Built. Physical verification requires flashing the new M55 image and watching for `[m55] LVGL thread init ret=0`.

## 2026-06-10 - LVGL Wi-Fi Scan Should Use WLAN Scan Report Events

Symptom:
- The touchscreen Wi-Fi page needed a selectable nearby-network list, but the obvious synchronous scan helper was not a safe implementation target in this BSP baseline.

Root cause:
- `rt_wlan_scan_sync()` is declared in the RT-Thread WLAN headers, but this project source does not provide a usable implementation path for the current BSP.
- The RT-Thread shell `wifi scan` command already uses `RT_WLAN_EVT_SCAN_REPORT` callbacks with `rt_wlan_scan_with_info(RT_NULL)`.

Fix:
- CM55 Wi-Fi config service now registers a temporary `RT_WLAN_EVT_SCAN_REPORT` handler, starts `rt_wlan_scan_with_info(RT_NULL)` in a background thread, caches up to 12 AP records, and exposes the cache to LVGL through `wifi_config_get_scan_count()` and `wifi_config_get_scan_ap()`.
- The LVGL panel shows a selectable list and keeps manual SSID entry for hidden networks.

Validation:
- M55 reference repo and actual RT-Thread Studio `wifi` project both build with `scons -j4`.

Reusable trick:
- For this BSP, follow the known-working RT-Thread `wifi scan` event-callback pattern instead of assuming every declared WLAN helper is linked and usable.

Status:
- Built. Physical scan/touch/connect QA still needs the board flashed with the new M55 image.

## 2026-06-10 - CM55 Wi-Fi Provisioning Must Use One Shared Service

Symptom:
- Wi-Fi configuration was available through shell commands, but SSID/password were RAM-only and would be lost after reset.
- Adding LVGL or App provisioning directly on top of WLAN APIs would create several independent Wi-Fi state machines.

Root cause:
- The first bring-up path was debug-oriented. It did not persist credentials and did not expose save/forget/auto-connect state to M33/App.

Fix:
- Added a shared CM55 Wi-Fi config service used by local shell, LVGL touchscreen, and M33/CM55 IPC.
- Saved credentials live at `/flash/rehab_wifi.cfg` and contain only SSID/password/auto-connect state.
- Added M33 QA commands `m55qa_wifi_save`, `m55qa_wifi_forget`, and `m55qa_wifi_auto <0|1>`.
- Added status fields so `m55qa_status` prints Wi-Fi `saved`, `auto`, and `storage` state.

Validation:
- M55 actual `wifi`, M55 Git reference `_m55_ref_repo`, and M33 `yiliao_m33` all build with `scons -j4`.

Reusable trick:
- Put Wi-Fi provisioning behind one service before adding UI/BLE/App entry points. UI code should not own connection state.

Status:
- Built. Physical LVGL touch/save/connect and reboot auto-connect still need board-side QA after flashing.

## 2026-06-10 - RT-Thread DFS Build Does Not Always Provide `dfs_posix.h`

Symptom:
- Adding Wi-Fi config persistence failed to build with:
  `fatal error: dfs_posix.h: No such file or directory`

Root cause:
- This BSP enables DFS and newlib stdio, but does not expose a `dfs_posix.h` header at the expected include path.

Fix:
- Use standard `stdio.h` file APIs (`fopen`, `fgets`, `fprintf`, `remove`) for `/flash/rehab_wifi.cfg`.
- Keep the code guarded by `RT_USING_DFS` so it degrades cleanly if DFS is disabled.

Validation:
- Rebuilt the M55 actual `wifi` project and `_m55_ref_repo` successfully after removing the `dfs_posix.h` include.

Reusable trick:
- On this RT-Thread Studio BSP, check which POSIX headers actually exist before including RT-Thread DFS wrapper headers. If stdio works, prefer it for simple config files.

Status:
- Fixed.

## 2026-06-10 - XiaoZhi Endpoint Moved Under The Existing Command Center

Symptom:
- Device firmware still pointed at the older `/voice/xiaozhi/ws` path while the cloud platform implemented the production XiaoZhi-compatible WebSocket under the existing medical rehab-arm command center.

Root cause:
- The platform contract was finalized after the first CM55 XiaoZhi bridge was added.

Fix:
- CM55 default WebSocket URL is now:
  `ws://106.55.62.122:8011/api/rehab-arm/v1/projects/fd6a55ed-a63c-44b3-b123-96fb3c154966/devices/nanopi-m5/xiaozhi/ws?robot_id=rehab-arm-alpha`
- CM55 accepts server `listen stop` as a local stop signal without echoing another stop back to the platform.

Validation:
- M55 reference tree and actual `wifi` working tree both build with `scons -j4`.
- Platform side reports 101 handshake, hello/listen/audio/reply, scoped-token auth, and safety filtering have been validated.

Reusable trick:
- Keep the default firmware endpoint aligned with the command-center contract, and reserve `m55qa_xz_url` for temporary diagnostics.

Status:
- Device build is aligned. Physical spoken end-to-end validation still requires loading a valid scoped relay token into CM55.

## 2026-06-10 - Decode XiaoZhi Status Before Live Token Testing

Symptom:
- `m55qa_status` previously printed only a raw `flags=0x...` value, so it was hard to tell whether a failure was wake backend, token, WebSocket, or active audio streaming.

Root cause:
- CM55 status flags did not expose token/connect/listening state, and M33 did not decode the existing bits.

Fix:
- Added shared voice status bits for XiaoZhi listening, WebSocket connected, and scoped token loaded.
- M33 `m55qa_status` now prints `wake_on`, `wake_ready`, `wake_hit`, `xz_listening`, `xz_ws`, and `xz_token`.

Validation:
- After burning both cores, COM26 showed `wake_on=1 wake_ready=1 wake_hit=0 xz_listening=0 xz_ws=0 xz_token=0`.
- `m55qa_xz_reconnect` returned ACK `cmd=1003 result=-255` with no scoped relay token loaded, which matches `xz_token=0`.

Reusable trick:
- Before testing a cloud voice path, expose local token/connect/streaming state in firmware status. Otherwise HTTP/WebSocket failures all look the same.

Status:
- Fixed. Next live test should first load a scoped token and confirm `xz_token=1`, then reconnect and confirm `xz_ws=1`.

## 2026-06-10 - Do Not Load Wrong-Scope Relay Tokens

Symptom:
- A `rehab-relay.v1...` token may look structurally valid but still fail XiaoZhi WebSocket auth.

Root cause:
- Scoped relay tokens are bound to a specific project/device. The active device contract is `project_id=fd6a55ed-a63c-44b3-b123-96fb3c154966`, `device_id=nanopi-m5`, and `robot_id=rehab-arm-alpha`.

Fix:
- Use `tools/load_xiaozhi_token.ps1` only with a platform-generated token for the active project/device.
- The tool rejects non-`rehab-relay.v1.` values so vendor LLM API keys are not accidentally loaded onto CM55.

Validation:
- `tools/load_xiaozhi_token.ps1 -ReconnectOnly` reached COM26 and confirmed the expected no-token state: `xz_token=0`, `xz_ws=0`, and `cmd=1003 result=-255`.

Reusable trick:
- Treat `xz_token=1` as "a scoped token is loaded", not proof the token belongs to the current project/device. `xz_ws=1` is the real device-side sign that auth and handshake have passed.

Status:
- Tooling is ready. End-to-end chat remains blocked until a correct-scope relay token is generated and loaded.

## 2026-06-10 - XiaoZhi PCM Binary Frames Must Match The Platform Contract

Symptom:
- M33 status showed local `latest_pcm_len=320` while the platform contract says 16 kHz mono PCM S16LE at 20 ms, which is 640 bytes per WebSocket binary frame.

Root cause:
- The local mic driver can deliver smaller chunks than the platform's logical XiaoZhi audio frame. Forwarding each local chunk directly can create half-frame binary messages.

Fix:
- CM55 now accumulates local PCM into `XIAOZHI_AUDIO_FRAME_BYTES=640` before each `websocket_client_send_binary` call.
- The hello audio parameters and frame byte calculation share constants in `xiaozhi_voice_relay.h`.

Validation:
- M55 reference repo and actual `wifi` working tree both build with `scons -j4` after the change.

Reusable trick:
- Keep local audio-driver chunk size separate from cloud protocol frame size. The bridge should reframe audio before sending it over WebSocket.

Status:
- Built, pushed, and burned to CM55. COM26 confirms M33/M55 IPC and wake status still run. Needs WebSocket/audio test with a valid scoped token.

## 2026-06-10 - Test XiaoZhi Cloud Without Someone Near The Microphone

Symptom:
- Live wake-word/chat testing cannot always proceed because nobody is physically near the CM55 microphone.

Root cause:
- Physical wake-word validation depends on local audio, but platform WebSocket compatibility can be tested independently.

Fix:
- Added `tools/xiaozhi_ws_smoke_test.ps1` to simulate the device-side WebSocket flow from a Windows PC:
  `hello` -> `listen start` -> synthetic 640-byte PCM binary frames -> `listen stop`.

Validation:
- The script loads and attempts to connect.
- HTTP access to `106.55.62.122:8011` is reachable from the PC.
- Running with a dummy `rehab-relay.v1.fake.fake` token fails before a full XiaoZhi flow, which is expected for invalid auth/test data.

Reusable trick:
- Split voice bring-up into two tests: PC smoke test for cloud XiaoZhi contract, then physical CM55 wake-word test for local microphone and wake model.

Status:
- Tooling is ready. A valid scoped relay token is required for a real cloud pass.

## 2026-06-10 - Long XiaoZhi Tokens Exceed FinSH Command Length

Symptom:
- Platform relay tokens can be around 410 characters, while the RT-Thread FinSH command line is only about 80 characters.
- A single `m55qa_xz_token <token>` paste is truncated before it reaches CM55, so WebSocket auth cannot be configured reliably.

Root cause:
- The shell line limit is smaller than real platform-scoped relay tokens.
- The old CM55 token buffer and WebSocket header/request buffers were sized for short test tokens, not production relay credentials.

Fix:
- Keep `m55qa_xz_token <short_token>` for short debug tokens.
- Use chunked M33 shell commands for real relay tokens:
  - `m55qa_xz_token_begin`
  - repeated `m55qa_xz_token_part <chunk>` with chunks around 48 to 60 characters
  - `m55qa_xz_token_commit`
  - `m55qa_xz_token_clear` when clearing stale credentials
- CM55 now stages token chunks, commits atomically, and then reconnects XiaoZhi WebSocket.
- CM55 token storage is 768 bytes; WebSocket extra headers are 1024 bytes; the HTTP Upgrade request is 2048 bytes with truncation checks.

Validation:
- COM26 showed `m55qa_xz_token_begin` -> `voice_ack ... cmd=1004 result=0`.
- COM26 showed `m55qa_xz_token_part abc123` -> `voice_ack ... cmd=1005 result=0`.
- COM26 showed `m55qa_xz_token_commit` -> `voice_ack ... cmd=1006 result=-255` with a dummy token, proving the token reached CM55 and commit triggered reconnect.
- The dummy token was cleared with `m55qa_xz_token_clear`.

Reusable trick:
- Never paste long platform credentials directly into a small embedded shell command. Add a chunked config protocol and keep secrets out of source control.

Status:
- Fixed in M33/M55 firmware. End-to-end platform auth still depends on a valid platform token and XiaoZhi-compatible server endpoint.

## 2026-06-10 - OpenOCD Tcl Paths Need Forward Slashes On Windows

Symptom:
- `flash banks` did not register the external SMIF flash bank, and OpenOCD printed a corrupted path such as `D:RT-ThreadStudio...OpenOCD-Infineon...PSE84_SMIF.FLM`.

Root cause:
- Passing Windows backslash paths through OpenOCD `-c "set QSPI_FLASHLOADER ..."` lets Tcl treat backslashes as escapes.
- The SMIF flash-loader path becomes invalid, so `cat1d.cm33.smif1_ns` at `0x60000000` is not created.

Fix:
- Use forward slashes in OpenOCD command strings, for example:
  `D:/RT-ThreadStudio/repo/Extract/Debugger_Support_Packages/Infineon/OpenOCD-Infineon/2.0.0/flm/cypress/cat1d/PSE84_SMIF.FLM`.
- Keep the generated QSPI config directory in the OpenOCD search path.

Validation:
- `flash banks` showed `cat1d.cm33.smif1_ns (cmsis_flash) at 0x60000000`.
- Subsequent burns wrote `847872 bytes` for CM55 and `569344 bytes` for M33.

Reusable trick:
- For OpenOCD on Windows, prefer `/` paths inside all Tcl `-c` snippets even when PowerShell accepts `\` paths.

## 2026-06-10 - XiaoZhi Flow Should Follow The Official Streaming State Machine

Symptom:
- A naive wake implementation can detect the wake word and then upload only the wake frame or a fixed-length PCM clip, but this does not match the official XiaoZhi behavior and is brittle for real conversation.

Root cause:
- The official `Edgi_Talk_M55_XiaoZhi` flow is stateful and streaming: wake callback, reconnect if needed, `hello`, `listen start`, microphone binary audio stream, server-controlled `listen stop`/reply/TTS, then return to wake listening.

Fix:
- Keep the firmware client aligned to the official state machine.
- Adapt only endpoint URL, auth headers, platform device scope, and server response parsing for the rehab-arm command center.
- Do not store LLM vendor API keys in firmware; CM55 uses only platform-scoped relay configuration.

Validation:
- M55 builds and burns with the official-sequence client path.
- M33 shell can bridge `m55qa_xz_reconnect` to CM55; CM55 returns an ACK, proving the configuration command path works.

Status:
- Firmware-side foundation is in place. Platform WebSocket compatibility and live chat response remain to be validated.

## 2026-06-10 - Relocate Every M33 Intel HEX Segment

Symptom:
- OpenOCD wrote only `65536 bytes` from a freshly relocated M33 hex and printed `no flash bank found for address 0x08350000`.

Root cause:
- Only the first Intel HEX extended linear address record was changed from `0x0834` to `0x6034`.
- Later records such as `0x0835`, `0x0836`, ... remained unrelocated, so OpenOCD skipped those runtime-alias addresses.

Fix:
- Relocate every type-04 extended linear address in the M33 image from `0x0834..0x083C` to `0x6034..0x603C`, recomputing the Intel HEX checksum for each record.

Validation:
- The corrected relocated file begins with `:02000004603466` and contains subsequent records `6035`, `6036`, etc.
- OpenOCD then reported `wrote 569344 bytes`, confirming the full M33 image was programmed.

Reusable trick:
- For PSoC Edge E84 external flash images, trust the OpenOCD `wrote N bytes` count more than command exit code. A suspiciously small write means relocation or flash-bank mapping is still wrong.

## 2026-06-10 - CM55 DEEPCRAFT Wake Blocked By EthosU Stub

Symptom:
- `m55qa_status` reported CM55 IPC alive, but DEEPCRAFT wake init failed with `wake_stage=37` and `err=138280962`.

Root cause:
- `138280962` is `0x083E0002`, matching `MTB_ML_RESULT_ALLOC_ERR`.
- The current TensorFlow Lite Micro package has `tensorflow/lite/micro/kernels/ethosu.cc` implemented as a stub; `Register_ETHOSU()` returns `nullptr`, so the DEEPCRAFT U55 model cannot allocate/run correctly in this firmware baseline.

Fix:
- Do not keep debugging DEEPCRAFT as the active product wake path in this baseline.
- Use the official XiaoZhi Edge Impulse TFLite model as the current CM55 wake backend, with a local lightweight MFCC-like extractor and existing repo TFLM.

Validation:
- M55 SCons build passes.
- After OpenOCD burn, COM26 `m55qa_status` shows `wake_stage=20 err=0`, proving the new backend enters inference processing without the EthosU allocation error.

Status:
- Fixed for bring-up. Acoustic recognition quality still needs live `xiaorui` validation.

## 2026-06-10 - Short PCM Frames Can Starve Wake Inference

Symptom:
- CM55 voice status showed `frames` increasing but `detected=0`; before the fix, the wake backend stayed at init stage and did not receive enough PCM to infer.

Root cause:
- `voice_service_submit_local_pcm()` receives local mic data as short 640-byte frames, roughly 20 ms at 16 kHz mono 16-bit.
- The pre-wake heuristic gate required `WAKE_GATE_MIN_ACTIVE_FRAMES=28`, which is impossible for a single 20 ms frame. The gate returned before calling `xiaozhi_wake_engine_process_pcm16()`, so the wake backend never accumulated its 1 second model window.

Fix:
- Feed every listening PCM frame to `xiaozhi_wake_engine_process_pcm16()`.
- Let the wake backend own the rolling 16000-sample model window and inference cadence.

Validation:
- After rebuild and burn, `m55qa_status` shows `wake_stage=20 err=0` while listening. This means PCM reaches the backend and the backend runs inference.

Reusable trick:
- For streaming audio, do not apply full-window speech gates to a single short device read. Either aggregate first or let the model backend own the rolling window.

## 2026-06-10 - CM55 Stuck In `rt_assert_handler`

Symptom:
- M33 `m55qa_status` showed `ipc_ready=1` but M33-to-CM55 `tx_pending` increased after `m55qa_wake_on`; CM55 was not consuming the queue.
- OpenOCD showed CM55 PC at `0x6059f766`, which resolved to `rt_assert_handler`.

Root cause:
- GDB backtrace showed CM55 asserted in `libraries/HAL_Drivers/drv_uart.c:199` while `rt_hw_board_init()` called `rt_console_set_device("uart2")`.
- The visible serial shell belongs to M33. CM55 binding `uart2` during board init is not a valid mainline path for this product architecture.

Fix:
- Guarded console binding in `libraries/HAL_Drivers/drv_common.c` with `!defined(COMPONENT_CM55)`.
- CM55 is now observed and controlled through M33 shell commands and M33/CM55 IPC ACKs.

Validation:
- After rebuild, burn, and reset, CM55 no longer stops in `rt_assert_handler`.
- `m55qa_wake_on`, `m55qa_capture_on`, and `m55qa_wake_off` all return CM55 voice ACK frames with result `0`.

Reusable trick:
- If CM55 appears dead but M33 shell is alive, first check CM55 PC with OpenOCD and run `addr2line`/GDB before changing voice or IPC code.
- Do not treat `tx_pending=0` alone as full validation; require `MSG_TYPE_VOICE_CONTROL_ACK` for command handling confirmation.

## 2026-06-13 - Do Not Drift From Official XiaoZhi WebSocket Fields

Symptom:
- The M55 XiaoZhi relay path had drifted into a custom `hello.version=3`, `audio_params.format=pcm_s16le`, `frame_duration=20`, and `listen.mode=auto_stop` shape.
- This differed from the official XiaoZhi ESP32 WebSocket example and made it unclear whether board-side failures were network issues, protocol incompatibility, or relay-specific behavior.

Official reference:
- `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32\docs\websocket.md`
- `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32\main\protocols\websocket_protocol.cc`
- `D:\RT-ThreadStudio\workspace\_external_refs\xiaozhi-esp32\main\protocols\protocol.cc`

Fix:
- Realign M55 and the PC smoke test to official-style WebSocket fields:
  - `hello.version=1`
  - `audio_params.format=opus`
  - `sample_rate=16000`
  - `channels=1`
  - `frame_duration=60`
  - `listen.mode=auto`

Validation:
- PC smoke test using the scoped relay token received hello ACK, listen ACK, and a chat/VLA reply from the relay with the official-style message shape.
- M55 builds after the JSON/protocol change.

Remaining gap:
- M55 still lacks a real Opus encoder. Current relay testing accepted the binary frame path, but full official parity requires adding Opus encoding on M55 or documenting relay PCM compatibility explicitly.

Reusable trick:
- Before debugging wake word, ASR, or platform model logic, first compare the exact JSON fields against the official XiaoZhi example. A single mode or audio format mismatch can look like a networking or model failure.

## 2026-06-13 - NanoPi Camera QA SSH Port Open But No Banner

Symptom:
- Windows host can detect `192.168.2.66:22` as open with `Test-NetConnection`.
- `ping 192.168.2.66` times out.
- Paramiko fails with `Error reading SSH protocol banner`.
- OpenSSH exits with `Connection closed by 192.168.2.66 port 22`.
- Direct TCP read from port 22 returns an empty byte string instead of an `SSH-2.0...` banner.

Impact:
- The established NanoPi USB camera QA path for photographing the Infineon LCD cannot be used, even though the host sees the TCP port as open.

Current best hypothesis:
- The NanoPi is reachable at the TCP layer, but the SSH daemon is not serving a valid SSH session, is immediately closing new connections, or another service/socket is occupying port 22.

Fix/status:
- Unfixed in this pass. Do not assume NanoPi camera QA is available solely because port 22 is open.

Reusable trick:
- For camera QA, verify the SSH banner first. A successful `Test-NetConnection` is not enough; require an actual SSH login before planning remote `v4l2-ctl`/`ffmpeg` capture.

## 2026-06-10 - M33 Hex Relocation

Symptom:
- M33 post-build may print `arm-none-eabi-objcopy: interleave must be positive` and ignore the post-build error.

Fix:
- Manually run `arm-none-eabi-objcopy -O ihex Debug\rtthread.elf Debug\rtthread.hex`.
- Then run `tools\edgeprotecttools\bin\edgeprotecttools.exe run-config -i config\boot_with_extended_boot.json` from `Debug`.
- Confirm the first line of `Debug\rtthread.hex` is `:02000004603466` before burning.

Status:
- Fixed workflow, still a manual step until the generated post-build command is corrected.

## 2026-06-13 - LVGL Font Symbols Must Come From Fixed UI Source

Symptom:
- After adding more XiaoZhi status text, the LCD could still show square glyphs even though a previous font regeneration had added several manually guessed Chinese characters.

Root cause:
- `lv_font_conv --symbols` only includes the exact glyphs listed. Hand-written symbols lists drift whenever UI text changes.

Fix:
- Extract the fixed Chinese UI/status characters from M55 source files and regenerate `applications/rehab_wifi_font.c` from that set.
- Keep the generated include as `#include "lvgl.h"` for the current RT-Thread Studio LVGL include path.

Status:
- Fixed for fixed UI/status text. Dynamic XiaoZhi model replies can still contain arbitrary Chinese outside the static font.

Reusable trick:
- Before regenerating a small LVGL C font, scan the actual display source strings and build the symbols list from source, not memory.

## 2026-06-13 - XiaoZhi Speaker Path Is Not Complete Without Opus Decode

Symptom:
- The screen can show XiaoZhi text/status, but speaker output may still be silent or invalid even when the platform sends audio.

Root cause:
- Official XiaoZhi WebSocket binary audio is Opus. The current local M33 playback path writes PCM/WAV-like chunks to `sound0`; it does not decode Opus yet.
- M33 `sound0` initialization had also been skipped by default for earlier M55 QA, so playback code could not find a real speaker device.

Fix:
- Re-enabled `sound0` initialization by default on M33.
- Wired M33 main IPC handling for `MSG_TYPE_TTS_AUDIO` to `audio_playback_write()`.
- Updated `audio_playback` to open/configure `sound0` and call `rt_device_write()`.

Status:
- PCM/WAV-compatible playback path is compiled and burned after M33 hex relocation.
- Official Opus decode is still unimplemented and must be added, or the relay must explicitly return PCM/WAV chunks for this board.

Reusable trick:
- Treat “platform returned audio” and “speaker can play it” as two separate checks: verify codec format first, then verify `sound0` write path.

## 2026-06-13 - Do Not Eagerly Initialize M33 Speaker During XiaoZhi Bring-up

Symptom:
- After flashing a freshly built M33 image, COM4 produced no boot logs.
- OpenOCD showed M33 halted in `Handler HardFault` with `pc=0x1400267c`.
- Flashing an older full M33 image restored COM4 and `m55qa_status`, proving the board, UART, and CM55 IPC were not the primary failure.

Root cause:
- The current best fix confirmed that eager `audio_playback_init()`/`audio_playback_start()` during M33 framework startup was too risky for this bring-up baseline.
- The failure looked similar to a bad M33 hex relocation at first, but the post-fix image ran in Non-secure Thread mode, so startup hardware audio init was the actionable cause for this pass.

Fix:
- Do not initialize `sound0` during `m33_init_framework()`.
- Attempt speaker playback initialization lazily only when `MSG_TYPE_TTS_AUDIO` arrives.
- Keep `M33_SKIP_SOUND0_INIT_FOR_XIAOZHI_QA=1` while validating WiFi, WebSocket, ASR, and text/model response.

Validation:
- M33 built with `python -m SCons -j4`.
- The rebased M33 hex started with `:02000004603466`.
- After flashing, OpenOCD showed M33 in Non-secure Thread mode at `pc=0x08365d84`, not HardFault.

Reusable trick:
- When XiaoZhi network/voice QA depends on M33 shell, keep speaker hardware init out of the boot path. Validate audio output as a later, isolated step after WiFi and WebSocket are proven.

## 2026-06-15 - lwIP ERR_RTE During XiaoZhi WebSocket Connect Means Routing/Netif Context, Not WiFi Scan

Symptoms:
- M55 WiFi auto-connect is stable after reset.
- `m55qa_status` shows `saved=1 auto=1`, `wlan=1 ready=1`, and a valid DHCP lease.
- XiaoZhi still does not connect; serial shows `xz_ws=0 xz_stage=20 xz_errno=-4`.
- The cloud WebSocket URL/token/path had already been proven valid from PC with HTTP `101 Switching Protocols`.

Root cause / best current hypothesis:
- `-4` is lwIP `ERR_RTE`.
- The failure happens while starting `wsock_connect()` / `altcp_connect()`, before hello or audio.
- This points to lwIP routing/default-netif context or explicit PCB binding, not WiFi scanning or password storage.

Fix / next diagnostic move:
- Keep the WebSocket client on the official lwIP callback path.
- Before guessing at higher-level XiaoZhi logic, inspect `netif_default`, `ip_route()`, and the active WiFi netif binding.
- If needed, bind the WebSocket PCB to the live WiFi interface/local IP before connecting.

Reusable trick:
- Once WiFi DHCP works but lwIP TCP connect returns `ERR_RTE`, stop chasing SSID/password/UI. The bug is below the app layer, usually in netif selection or route context.

## 2026-06-15 - XiaoZhi Connected But No Reply: Separate Transport From Audio Codec/ASR

Symptoms:
- Board status shows stable WiFi and a connected XiaoZhi WebSocket: `xz_ws=1 xz_stage=70 xz_errno=0`.
- Manual capture starts M55 mic successfully and sends many binary frames: examples include `frames=2326 pcm_seq=2326 probe_lwip=387/744588`.
- After `m55qa_capture_off`, no `stt`, `llm`, `tts`, or binary audio reply is observed; only server hello/listen control text is counted.
- A PC-side synthetic speech WAV converted to 16 kHz mono S16LE PCM and sent through the same v3 WebSocket path also received only `listen start/stop`, with no STT/TTS within the wait window.

Root cause / current best hypothesis:
- Transport is no longer the blocker. WebSocket, mic capture, M33->M55 command path, and binary upstream have all been proven.
- The remaining boundary is audio format handling. Official XiaoZhi expects Opus frames, while the current M55 path sends raw `pcm_s16le` wrapped in v3 binary framing.
- A PC `ClientWebSocket` probe showed the platform can echo `pcm_s16le` in hello, but the synthetic speech probe indicates the downstream relay still may not perform PCM ASR.

Fix/status:
- M55 now declares `Protocol-Version: 3`, `hello.version=3`, and `audio_params.format=pcm_s16le` so the protocol matches the current payload instead of claiming Opus.
- `WSMSG_MAXSIZE` is 4096 so 60 ms PCM packets plus the v3 header are not rejected by the local lwIP WebSocket send path.
- Status is partially fixed: upstream transport is working, model reply is not yet working.

Reusable trick:
- Do not debug WiFi, DHCP, or LVGL when `xz_ws=1` and `probe_lwip` increases during capture. At that point inspect server-side ASR/codec logs or add Opus/PCM transcode support.
- Treat these as separate gates: WebSocket connected, server hello received, mic frames captured, binary frames sent, server STT returned, TTS audio returned, speaker playback.
- If nobody is physically near the board, generate a local 16 kHz mono WAV with Windows speech synthesis and send its PCM frames through the WebSocket probe to remove ambient noise from the diagnosis.

Update:
- After the platform relay was fixed, the same PC synthetic speech PCM probe returned `stt`, `llm`, `chat`, and `tts start/stop`.
- The board then needed a reset because M55 voice status had gone stale and M33 `tx_pending` increased without fresh ACKs.
- After reset, M55 IPC and WebSocket recovered and board PCM upstream was again proven by `probe_lwip=386/742664`.
- If board capture still produces no STT while nobody is near the microphone, treat it as no valid speech input, not as a relay regression.

## 2026-06-17 - Do Not Claim Opus While Sending PCM

Symptoms:
- A PC-side XiaoZhi smoke test connected to the platform and passed `hello`/`listen start`, but the platform returned `opus_decode_not_configured` after binary frames.
- The test output said `declared_format=opus` while the script actually generated 16 kHz S16LE PCM tone frames.

Root cause:
- The smoke test's `hello.audio_params.format` was hardcoded to `opus`, but `New-PcmFrame` produced raw PCM. This made a good platform rejection look like a board or server Opus failure.

Fix:
- `tools/xiaozhi_ws_smoke_test.ps1` now defaults to `AudioFormat=pcm_s16le`.
- `AudioFormat=opus` requires an explicit length-prefixed Opus packet file; the script does not pretend to encode PCM on the PC.
- CM55 firmware now enables `XIAOZHI_USE_OFFICIAL_OPUS_AUDIO` and fixes the Opus encoder sample-count check to 960 samples for 60 ms at 16 kHz.

Status:
- Board-side official Opus uplink is validated by `m55qa_status` examples such as `xz_last=158/28282 xz_fail=0`.
- The latest probe did not receive binary TTS (`xz_rx=2/0`), so speaker playback remains unverified rather than proven broken.

Reusable trick:
- Keep the XiaoZhi gates separate: declared audio format, actual binary payload format, WebSocket connection, upstream packet counter, STT text, binary TTS, CM55 `tts_fwd`, and M33 `sound0`.
- If `xz_last` is around tens of KB for several seconds of speech, it is likely Opus. If it is hundreds of KB, it is likely raw PCM.

## 2026-06-15 - XiaoZhi LVGL Stuck Thinking And Missing Chinese Glyphs

Symptoms:
- LCD XiaoZhi panel can remain on “正在思考” after an utterance if no TTS/text completion arrives.
- Some Chinese UI text renders as square boxes.

Root cause:
- `xiaozhi_ui_state` recorded the last phase but did not expire `THINKING` or `SPEAKING` if the platform reply or stop event never arrived.
- The generated `rehab_wifi_font` only contains a small fixed symbol set and had `.fallback = NULL`, even though `LV_FONT_SIMSUN_16_CJK` is enabled.

Fix:
- Expire `XIAOZHI_UI_THINKING` after about 20 s into `READY` with “未收到回复，请重试”.
- Expire `XIAOZHI_UI_SPEAKING` after about 30 s into `READY`.
- Declare `lv_font_simsun_16_cjk` and assign it as the fallback for `rehab_wifi_font`.

Reusable trick:
- On this bench COM4 is the M33 shell. M55-only finsh exports are not directly callable there; use `m55qa_status` as the authoritative M55 IPC snapshot.
- Do not grow the custom LVGL font with every possible model reply. Keep dynamic replies off the small LCD and use a CJK fallback for fixed UI text.

Status:
- Built and burned on M55 with WiFi resources. Serial QA confirmed WiFi, XiaoZhi WebSocket, wake readiness, and LVGL flush in the stable state.
- Visual LCD confirmation is still required for the final glyph appearance.

## 2026-06-15 - Speaker QA Tone Is Not Representative Of XiaoZhi Voice

Symptom:
- `audio_playback_tone_cmd` proves `sound0` and I2S writes, but the square-wave tone sounds harsh and does not resemble a XiaoZhi/person voice.

Root cause:
- The first QA command intentionally generated a simple square wave to make driver failures obvious. It is useful for electrical/software bring-up but poor for user-facing audio evaluation.

Fix:
- Added `audio_playback_voice_cmd`, an algorithmic voice-like sample with a 64-point sine table, simple harmonic/formant-like mixing, pitch movement, and attack/release envelope.
- Avoided embedding a large PCM asset in firmware.

Reusable trick:
- Keep two speaker QA levels: a simple tone for low-level driver verification, and a softer voice-like local sample for human listening checks. Neither replaces real platform TTS validation.

Status:
- Command built, burned, and ran successfully through `sound0`; physical listening quality still needs onsite confirmation.

Update:
- Onsite feedback confirmed the algorithmic sample sounds noisy and must not be used as a user-facing response.
- Keep `audio_playback_voice_cmd` only as a speaker QA/debug command.
- Do not wire local generated audio into XiaoZhi wake acknowledgement. For a real “我在” response, use platform/official TTS audio or a separately validated real prompt asset.

## 2026-06-19 - COM4 token reload can succeed while XiaoZhi reconnect still fails

Symptoms:
- `tools/load_xiaozhi_token.ps1` successfully sent `m55qa_xz_token_begin`, a sequence of `m55qa_xz_token_part` chunks, and `m55qa_xz_token_commit` over COM4.
- The visible shell returned ACKs for the config bridge path, but `m55qa_xz_reconnect` still ended in `cmd=1003 result=-255`.
- `m55qa_status` showed the token updated to `token_len=480`, yet `xz_ws` stayed `0` and `xz_errno` remained `-403`.

Environment:
- Active shell: `COM4` KitProg3 USB-UART.
- Loader source: `D:\RT-ThreadStudio\workspace\yiliao_m33\tools\load_xiaozhi_token.ps1`.
- Token source: scoped relay token file beginning with `rehab-relay.v1.`.

Root cause:
- The token write path was fine; the remaining failure sits on the platform acceptance / authorization side, not on WiFi or the shell transport.

Fix:
- Treat the current blocker as cloud/token acceptance, not board-side WiFi bring-up.
- Keep using the chunked loader path because it avoids shell truncation and proves the token reached CM55.

Trick:
- Check both the ACK chain and the status snapshot. A successful `m55qa_xz_token_commit` does not guarantee `xz_ws=1`; always confirm `m55qa_status` after reconnect.

Status:
- Partially fixed: token rewrite works, reconnect still rejected.

## 2026-06-19 - XiaoZhi token must be persisted outside RAM or every power cycle asks for it again

Symptoms:
- Each fresh power-up lost the CM55 XiaoZhi relay token even after `m55qa_xz_token_begin` -> `m55qa_xz_token_part` -> `m55qa_xz_token_commit` had succeeded.
- The board then required the COM4 loader again before `m55qa_xz_reconnect` or normal XiaoZhi startup could work.

Environment:
- Active M55 tree: `D:\RT-ThreadStudio\workspace\wifi`
- Mirror M55 tree: `D:\RT-ThreadStudio\workspace\_m55_ref_repo`
- Token file path now used by the firmware: `/flash/rehab_xiaozhi_token.cfg`

Root cause:
- The relay token previously lived only in `g_xiaozhi.token` RAM and in the temporary shell loader path.
- WiFi had already been persisted through `/flash/rehab_wifi.cfg`, but XiaoZhi token handling had not yet been given the same treatment.

Fix:
- Save the token to `/flash/rehab_xiaozhi_token.cfg` on `set` and `commit`.
- Load the token from the same file during `xiaozhi_voice_relay_init()`.
- Delete the file when the token is cleared.

Trick:
- If a board asks for the token after every reset, check whether the value is only being staged in RAM or over a shell loader. A successful commit is not persistence by itself.

Status:
- Fixed in source; full power-cycle verification is still pending.

## 2026-06-19 - Port 3001 platform front door is live, but unauthenticated requests only see login

Symptoms:
- `http://106.55.62.122:3001/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab` returns HTTP 200 and serves the platform shell.
- The same request from this shell lands on the login page rather than the project workspace.

Environment:
- Front door: `106.55.62.122:3001`
- Project path: `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab`

Root cause:
- The platform exists and is reachable, but the current session is not authenticated for the project page.

Fix:
- Treat `3001` as the active platform entry and login gate, not as evidence that the model-relay-lab workspace is already available in the current shell.

Trick:
- When a platform page works in the browser but not from a shell, check whether you are seeing the front door or the authenticated project surface.

Status:
- Live but not authenticated from this context.

## 2026-06-19 - The platform login page expects a real email/password pair, not the bench account stub

Symptoms:
- The login page at `http://106.55.62.122:3001/login` rendered correctly and accepted form input.
- Submitting `3245056131 / 1234` returned `INVALID_CREDENTIALS`.
- A best-effort `3245056131@qq.com / 1234` retry also stayed on the login page.

Environment:
- Platform front door: `106.55.62.122:3001`
- Target project path: `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab`

Root cause:
- The supplied pair is not a valid login for this platform account system.
- The page is email-based, so a raw numeric identifier is not enough by itself.

Trick:
- When a login page uses email fields, do not assume a numeric chat handle is a usable account.
- Treat `INVALID_CREDENTIALS` as a hard stop and stop guessing after one careful retry.

Status:
- Unauthenticated; relay inspection from the project page is still blocked until the correct account or session is available.

## 2026-06-19 - `model-relay-lab` is the authenticated relay page, not just a static shell

Symptoms:
- The login page accepted the correct email account, and the project list exposed a `医疗康复机械臂` project.
- Opening `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab` showed `Relay Lab`, `API key 可用性测试`, and explicit HTTP/XiaoZhi endpoints.
- The in-page `测试调用` action returned `qwen / qwen-plus`.

Environment:
- Authenticated project: `医疗康复机械臂`
- Relay page: `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab`

Root cause:
- The earlier confusion came from looking only at the login gate or unauthenticated shell.
- The real relay page is only visible after the correct account signs in.

Trick:
- When the login works, go straight to the project-specific relay page and read the endpoint labels there. Do not keep inferring from the front door.

Status:
- Fixed for this session; the relay page is confirmed live and returns a model answer.

## 2026-06-19 - A freshly generated relay token can still fail PC WebSocket connect

Symptoms:
- The authenticated relay page generated a new token and showed the correct project/device scope.
- The CM55 loader accepted the new token and reported `token_len=442`.
- The PC smoke test against the relay WebSocket still failed immediately with `无法连接到远程服务器`.

Environment:
- Token source: authenticated `model-relay-lab` page for `医疗康复机械臂`
- Board loader: `tools/load_xiaozhi_token.ps1`
- Smoke test: `tools/xiaozhi_ws_smoke_test.ps1`

Root cause:
- The token generation page is not enough on its own; the live relay endpoint or client path still needs a successful connect.

Trick:
- When a fresh token still fails at connect time, separate token issuance from transport reachability before touching the board again.

Status:
- Unresolved; board-side reconnect and relay transport still need another targeted pass.

## 2026-06-19 - The real blocker was an old hardcoded `fd6...` project URL on the board side

Symptoms:
- The authenticated `model-relay-lab` page for the current session belongs to `project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c`.
- The M55 source still hardcodes `project_id=fd6a55ed-a63c-44b3-b123-96fb3c154966` in the default XiaoZhi WebSocket URL.
- PC smoke test only works when pointed at the current `e201...` endpoint.

Environment:
- Board sources: `wifi/applications/xiaozhi_voice_relay.h`, `_m55_ref_repo/applications/xiaozhi_voice_relay.h`
- Relay page: `/projects/e201f41c-25a6-46e1-baf8-be6dcb83284c/model-relay-lab`

Root cause:
- The token and page were correct, but the board's default URL was still aimed at the old project id.

Trick:
- When relay auth looks inconsistent, compare the project id in the page-generated token with the hardcoded board URL before changing token logic again.

Status:
- Found; the next fix is to switch the default board endpoint to the current authenticated project path.

## 2026-06-19 - LVGL provisioning QR and XiaoZhi relay URL must share the same project id

Symptoms:
- The board-side XiaoZhi relay default had already been updated to `project_id=e201f41c-25a6-46e1-baf8-be6dcb83284c`.
- The LVGL `扫码配网` QR payload in `rehab_wifi_panel.c` still pointed at the old `fd6a55ed...` project.
- That left the UI provisioning entry and the cloud relay entry on different project scopes.

Root cause:
- The QR helper and the XiaoZhi WebSocket helper were edited at different times, so the UI path drifted away from the live relay project.

Fix:
- Update both the active `wifi` burn project and the `_m55_ref_repo` mirror so the QR payload and the XiaoZhi default endpoint use the same `e201...` project id.

Trick:
- When relay auth, QR provisioning, and WebSocket connect are all in play, compare the project id in each path before touching tokens again.

Status:
- Fixed in source; rebuild/burn still needed for hardware verification.

## 2026-06-19 - `m55qa_xz_reconnect` can fail even when WiFi, token, and platform are good

Symptoms:
- After flashing the corrected `e201...` M55 image and loading the scoped token, `m55qa_status` can show `xz_ws=1 xz_stage=70 xz_errno=0`.
- Calling `m55qa_xz_reconnect` from COM4 can then drop the state to `xz_ws=0 xz_stage=80`, with either `xz_errno=0` or `xz_errno=-1`.
- WiFi remains healthy during the failure: `wlan=1 ready=1`, valid IP/gateway/DNS, and `cloud_tcp=0/1`.
- The same token and endpoint still pass the PC XiaoZhi WebSocket smoke test.

Root cause / current best hypothesis:
- This is inside the CM55 lwIP WebSocket reconnect state machine, not WiFi, token scope, or cloud model availability.
- The intentional local close before reconnect can race with `WS_DISCONNECT` callbacks or leave the `wsock_state_t`/PCB lifecycle in a state that makes the immediate next connect fail.

Fix attempted:
- Added a guard to ignore the next local `ERR_ABRT` disconnect caused by intentional close.
- Added a disconnect completion wait before reconnecting instead of relying only on a fixed delay.

Status:
- Partially fixed / still open. Token reload can reach `xz_ws=1`, but explicit `m55qa_xz_reconnect` remains unstable.

Trick:
- If status shows `xz_token=1`, `token_len=442`, WiFi ready, and PC smoke passes, stop regenerating tokens. The next useful evidence is realtime `[websocket]` logs during the close/connect transition.

Update:
- The stable fix for the user-facing `m55qa_xz_reconnect` path is to avoid reconnecting at all when `websocket_client_is_connected()` is already true.
- Do not send a duplicate `hello` on an already-open XiaoZhi WebSocket; one test showed duplicate hello could be followed by `xz_stage=80 xz_errno=-1`.
- After the no-op change, COM4 validated `m55qa_xz_reconnect` keeps `xz_ws=1 xz_stage=70 xz_errno=0`.

Status:
- Fixed for the already-connected reconnect command path. Real offline reconnect still uses the lower-level connect path and should be tested separately if the socket is genuinely down.

## 2026-06-19 - `/flash` token persistence fails when filesystem storage is unavailable

Symptoms:
- After loading the scoped XiaoZhi token once, `m55qa_status` showed `xz_token=1 token_len=442`.
- After reboot/power transition, the user still saw the board ask for token again.
- COM4 confirmed the failure: `xz_token=0 token_len=0`, while WiFi persisted correctly with `saved=1 auto=1`.
- The same status line showed `storage=0`, so the filesystem-backed `/flash/rehab_xiaozhi_token.cfg` path was not a reliable persistence layer.

Environment:
- Active burn tree: `D:\RT-ThreadStudio\workspace\wifi`
- Git mirror: `D:\RT-ThreadStudio\workspace\_m55_ref_repo`
- Existing WiFi persistence mechanism: FAL partition `wifi_cfg`

Root cause:
- XiaoZhi token persistence had been implemented through stdio on `/flash`, but the board's filesystem mount was not available in the observed runtime.
- WiFi worked because it already used a raw FAL log partition, not because `/flash` was healthy.

Fix:
- Added a dedicated 4 KB FAL partition `xiaozhi_cfg` at `0x1FE000` and reduced the unused `filesystem` partition by 4 KB.
- Changed `xiaozhi_voice_relay` to load/save/clear the token from `xiaozhi_cfg` first, with `/flash/rehab_xiaozhi_token.cfg` only as fallback.

Status:
- Fixed for software reset: after reboot without rerunning the loader, COM4 showed `xz_token=1 token_len=442`.
- Needs one user-observed full power-cycle confirmation on the final FAL build.

Trick:
- If `m55qa_status` shows `saved=1 auto=1` for WiFi but `xz_token=0`, compare the storage backend. Do not assume `/flash` works just because WiFi survives reboot.

## 2026-06-19 - XiaoZhi path is past WiFi/token; remaining failure is relay audio/TTS behavior

Symptoms:
- With WiFi ready and token persisted, `m55qa_status` can reach `xz_ws=1 xz_stage=70 xz_errno=0`.
- Automatic wake/listen sent Opus packets such as `xz_last=22/3938` or `53/9487`.
- The relay returned text/control frames only: `xz_rx=<n>/0`, `tts_fwd=0/0`, so M33 speaker had no cloud TTS binary to play.
- Manual/QA `m55qa_capture_on` is unstable: after protocol alignment and mic restart fixes it can ACK success, but some runs still end with `xz_ws=0 xz_stage=80 xz_errno=-1`.

Root cause / current best hypothesis:
- This is no longer a WiFi scan, WiFi connect, token scope, or token persistence problem.
- The remaining issue is in the XiaoZhi listen protocol/server behavior or in the board-side handling of server text/TTS. The platform has not sent binary audio in observed board runs.
- Manual capture likely differs from the official wake-triggered flow enough for the relay to close or ignore it; the automatic wake path is the more faithful path to continue.

Fix attempted:
- Enabled official Opus audio mode (`XIAOZHI_USE_OFFICIAL_OPUS_AUDIO`).
- Changed manual start to send `listen/detect` before `listen/start` and to use wake-style `auto` mode instead of `manual`.
- Added CM55 capture start/stop stage logs and forced a mic restart before `VOICE_CTRL_START_CAPTURE`.

Status:
- Partially improved. Token/WiFi/WebSocket baseline is stable; cloud binary TTS is still not validated.

Trick:
- Use `xz_rx=text/binary`, `tts_fwd=chunks/bytes`, and `xz_last=chunks/bytes` as the main split. If `xz_last` increases but `xz_rx` binary and `tts_fwd` stay zero, stop debugging the speaker first; the platform did not provide playable audio.

## 2026-06-19 - Rebooted board still kept the token, so token was not the blocker

Symptoms:
- After a fresh power cycle, `m55qa_status` still showed `xz_token=1 token_len=442`, `wlan=1 ready=1`, and `xz_ws=1 xz_stage=70 xz_errno=0`.
- The PC XiaoZhi smoke test against the same token and relay endpoint succeeded and returned `stt` text.
- The CM55 capture path still fell back to `xz_ws=0 xz_stage=80 xz_errno=-1` without any `xz_cur/xz_last` growth.

Root cause:
- The token and relay project are fine. The remaining failure is the board-side audio/listen flow or the relay's handling of that flow.

Trick:
- If rebooted status still shows `xz_token=1`, stop reloading token and move directly to the audio path. The token is no longer the interesting variable.

Status:
- Token ruled out on the current board image.

## 2026-06-19 - Reuse An Already-Connected XiaoZhi Socket

Symptoms:
- The board can report `xz_ws=1` and still sit forever at "等待小智会话" or "小智连接中" after `m55qa_capture_on`.

Root cause / current best hypothesis:
- `voice_service_start_xiaozhi_talk()` was forcing a disconnect/reconnect cycle even when the websocket was already connected.
- That makes the healthy session look like a startup failure and hides the real first-frame boundary.

Fix/status:
- Reuse the existing websocket when it is already connected.
- Only reconnect if the socket is actually down.
- Keep the current PCM relay path on `Protocol-Version: 3`.

Reusable trick:
- When the socket is already online, debug the first `websocket_client_send_binary()` result before changing token, WiFi, or platform settings again.

## 2026-06-19 - Build and QA were being blocked by a fake GCC path, not by WiFi

Symptoms:
- Rebuilds in the active M55 burn tree needed an explicit local GCC path instead of the old placeholder `C:\Users\XXYYZZ`.
- WiFi and token status were already stable, but the board still needed a fresh build before the new XiaoZhi session changes could be tested.

Environment:
- Active burn tree: `D:\RT-ThreadStudio\workspace\wifi`
- Git mirror: `D:\RT-ThreadStudio\workspace\_m55_ref_repo`

Fix:
- Pointed `rtconfig.py` at the real local GNU toolchain install and prepended its `bin` directory to `PATH`.

Trick:
- If the board keeps landing in the same waiting state, check the build toolchain first. A stale compiler path can hide the actual protocol bug behind an old binary.

Status:
- Fixed in source; rebuild still running when this note was written.

## 2026-06-19 - `m33qa_xz_probe` is a debug-only path and can fill the IPC queue

Symptoms:
- On the refreshed M55 image, `m55qa_capture_on` now returns `0`, but the old `m33qa_xz_probe` test path starts failing after a few 1920-byte packets with `ret=-28`.
- COM4 status at the same time still shows `xz_ws=1`, `xz_token=1`, `token_len=442`, and WiFi ready, so the failure is not token or network related.

Root cause:
- The M33 probe path pushes PCM through the same M33->M55 IPC queue used by the real voice bridge, and that queue is finite.
- Using it as a mainline audio path can saturate the queue and hide the actual XiaoZhi session behavior.

Fix / trick:
- Keep `m33qa_xz_probe` as a narrow debug tool only.
- For XiaoZhi mainline QA, prefer `m55qa_capture_on` on the refreshed M55 path and ignore the old probe once the queue fills.

Status:
- Understood on the current image; no code change required for the mainline path yet.

## 2026-06-19 - XiaoZhi kept showing "waiting platform" because hello was self-confirmed too early

Symptoms:
- The board reported `xz_ws=1`, `xz_token=1`, and `token_len=442`, but `m55qa_capture_on` still behaved like the session was not really ready.
- UI and logs kept lingering at "等待小智会话" / "小智连接中" even though WiFi and token were already healthy.

Root cause:
- `voice_service_send_xiaozhi_hello()` was marking `xiaozhi_server_hello_seen` immediately after sending the local hello.
- That blurred the line between "I sent hello" and "the server actually replied hello", so talk start could look ready before the real server handshake arrived.

Fix:
- Stop self-marking the server hello when sending the local hello.
- Let `voice_service_handle_server_text()` own the real `hello` confirmation.
- Make `voice_service_start_xiaozhi_talk()` wait for the actual server hello before entering manual listening.

Reusable trick:
- When XiaoZhi sits in a waiting state with healthy WiFi/token, check whether the client is confusing its own outbound hello with the platform's inbound hello.

Status:
- Fixed in source; needs one fresh flash and a real COM4 QA pass to prove the startup flow now advances correctly.

## 2026-06-19 - Probe selection mattered more than the image when flashing the wifi tree

Symptoms:
- `wifi/program_with_resources.bat` originally used plain `interface/kitprog3.cfg` and then died with `kitprog3: failed to acquire the device`.
- Switching to `interface/cmsis-dap.cfg` caused OpenOCD to attach to the wrong external probe and fail with `CMSIS-DAP command CMD_INFO failed`.

Environment:
- Board-mounted probe: `KitProg3 CMSIS-DAP` with parent serial `17040F11022F2400`.
- External probe also present: `Horco CMSIS-DAP v2` with parent serial `2d2670f3`.

Root cause:
- Automatic probe selection was ambiguous because two CMSIS-DAP probes were visible at once.
- The board image itself was fine; the flashing path was stopping in probe acquisition, not in the hex/resource payload.

Fix:
- Explicitly lock the board-mounted KitProg3 by adding `adapter serial 17040F11022F2400` to the OpenOCD command line while keeping `interface/kitprog3.cfg`.
- Do not let OpenOCD auto-pick between the board probe and the external Horco probe.

Trick:
- When multiple probes are attached, query `DEVPKEY_Device_Parent` and pin the board probe serial in the burn script before debugging anything else.

Status:
- Partially fixed. Flashing and post-flash status checks now work on the board probe, but the session still needs a real cloud reply to complete the XiaoZhi path.

## 2026-06-22 - Stale `m55qa_status` after TTS means check voice service drain progress

Symptoms:
- After a successful QA probe/TTS playback run, `m55qa_probe_pcm_off` could ACK but the following real mic0 `m55qa_capture_on/off` timed out.
- `tx_pending` rose while WiFi/token/WebSocket stayed healthy, so this is not a network/token regression.

Fix / trick:
- `m55qa_status` now prints `voice_svc=loop/drain/last_consume_ret/phase` using existing diagnostic slots.
- M55 drains M33->M55 IPC before and after each TTS chunk publish, so stop/control commands are not starved behind synchronous TTS forwarding.
- M55 publishes a fresh status after auto reconnect success/failure; otherwise COM4 can keep showing the last `xz_ws=0 stage=80` status until another event publishes a new snapshot.

How to read it:
- `loop` should keep increasing when the M55 voice service thread is alive.
- `drain` should increase when M33 control/probe messages are consumed.
- `last_consume_ret=-3` normally means the queue was empty.
- `phase=40/41/42/43` points inside TTS forwarding; if it sticks there with stale seq, inspect M55->M33 audio queue/playback pressure before touching WiFi or token.

Validated:
- After reflashing both sides, real CM55 mic0 control commands no longer stuck behind prior QA/TTS state: `probe_pcm_off`, `capture_on`, and `capture_off` all ACKed with `tx_pending=0`.
- A post-stop status published after auto reconnect showed `xz_ws=1 xz_stage=70 xz_errno=0` with a fresh status age, confirming the stale `xz_ws=0 stage=80` snapshot no longer persists after recovery.

## 2026-06-22 - `capture_on result=-116` can be stale/repeated hello gating

Symptoms:
- `m55qa_status` shows `xz_ws=1`, `xz_stage=70`, `xz_errno=0`, and `srv_hello=1`.
- `m55qa_probe_pcm_on` ACKs, but `m55qa_capture_on` returns ACK `result=-116`.
- `tx_pending=0`, so M33->M55 IPC is not the blocker.

Fix / trick:
- M55 now treats prior server-hello evidence in the same runtime as sufficient if a repeated hello wait times out while the WebSocket is still connected.
- This lets manual/QA listen start proceed on platforms that do not send another hello on demand.
- The cold-start talk hello wait is now 8 seconds instead of 3 seconds, so immediate post-flash QA has time for WebSocket hello before returning `-116`.

## 2026-06-22 - QA PCM consumed but no XiaoZhi uplink means check accepted vs ignored counts

Symptoms:
- `m33qa_xz_probe 3000` sends all 50 packets and `tx_pending=0`.
- `voice_svc drain` increases, but `xz_cur/xz_last` remains `0/0`.

Fix / trick:
- `m55qa_status` now shows M33 QA PCM counters as `probe_lwip=accepted/ignored`.
- M55 shared PCM acceptance now feeds XiaoZhi immediately while `xiaozhi_listening_active`, so accepted QA PCM does not depend on later wake/detect processing.

Validated:
- After the direct-feed fix, a 3000 ms QA run showed `probe_lwip=50/0`, `xz_last=193/34547`, and `xz_fail=0`.
- If `xz_rx` increments only on text and binary stays `0`, the next layer is platform/protocol event handling, not M33->M55 IPC or Opus uplink.

## 2026-06-22 - Human voice QA must feed immediately after capture_on

Symptoms:
- `m55qa_capture_on` can ACK `0`, but if the QA script waits too long before `m33qa_xz_probe full`, M55 may already have left XiaoZhi listening.
- In that case the correct M33 behavior is:
  - `xiaozhi probe abort: M55 not listening ... xz_ws=1 tx_pending=0`
- This is not a WiFi/token/WebSocket failure when `xz_ws=1`, `token_len=442`, and `srv_hello=1`.

Fix / trick:
- For deterministic human-voice QA, send `m33qa_xz_probe full` immediately after `m55qa_capture_on` returns ACK.
- Keep `m55qa_probe_pcm_on` enabled during this test so CM55 mic0 EOU does not prematurely close the QA session.
- Treat `M55 not listening` as a safe abort. Re-run `m55qa_capture_on`; do not continue sending PCM and do not debug WiFi.

Validated:
- Human-like prompt `你好小智，请用一句话介绍一下你自己。` embedded as `166974` bytes of 16 kHz mono S16LE PCM.
- Fast-feed run sent `87` parts / `166974` bytes, with `retries=0` and `tx_pending=0`.
- M55 reported `probe_lwip=87/0`, `xz_last=313/600960`, and `xz_fail=0`.
- M33 received TTS downlink and wrote it to the speaker path:
  - `tts audio rx total=640`
  - `audio_playback Started`
  - `tts audio write chunk=1/2/3`

Reusable QA sequence:
- `m55qa_status`
- `m55qa_probe_pcm_on`
- `m55qa_capture_on`
- immediately `m33qa_xz_probe full`
- `m55qa_capture_off`
- wait 60 seconds
- `m55qa_status`

## 2026-06-22 - Short TTS replies may need an M33 idle flush

Symptoms:
- M33 receives a small number of `MSG_TYPE_TTS_AUDIO` chunks and `audio_playback Started` appears.
- The server/platform may not send a zero-length TTS flush marker after a short reply.
- In that case the last buffered audio can remain pending in M33 playback even though the XiaoZhi uplink and downlink already worked.

Fix / trick:
- M33 now tracks TTS audio activity at file scope and calls `audio_playback_flush()` after 500 ms without another TTS chunk.
- Normal zero-length flush messages still flush immediately and reset the same counters.
- Expected diagnostic line for this fallback is:
  - `[m33] tts audio idle flush chunks=... bytes=... ret=...`

Validation:
- Clean M33 build passed with the idle-flush code included.
- The clean ELF contains `tts audio idle flush`, confirming the board image source is current.
- Board-side QA could not be rerun in this pass because the debugger/board stopped enumerating before flash; do not reinterpret that as WiFi/token/platform regression.

## 2026-06-22 - If only com0com ports enumerate, flashing cannot proceed

Symptoms:
- M55 `program_with_resources.bat` fails before writing any bytes:
  - `Error: unable to find a matching CMSIS-DAP device`
- `Get-CimInstance Win32_SerialPort` only shows com0com virtual ports and no board COM/KitProg interface.

Fix / trick:
- This is a USB/debugger enumeration problem, not a XiaoZhi voice-link problem.
- Do not debug WiFi, token, WebSocket, Opus, or platform events from this state.
- Wait for the board/KitProg interface to reappear, then flash M55 and M33 before running QA.

Status:
- Latest code builds on both M55 and M33, but the requested unattended human-voice QA is pending until the hardware enumerates again.

## 2026-06-22 - Reset QA probe counters before judging each XiaoZhi run

Symptoms:
- A repeated human-voice QA run can show `probe_lwip=accepted/ignored` values that appear contradictory, such as `87/87`.
- M33 may print `xiaozhi probe done parts=87 sent=166974/166974`, while the final M55 status appears to include both accepted and ignored packets.

Root cause:
- `probe_lwip=accepted/ignored` was cumulative across QA sessions.
- A previous successful run could leave `accepted=87`; a later failed or stale-listening run could add ignored packets, making the final status look like one mixed run.

Fix / trick:
- M55 now resets `m33_pcm_probe_accepted_count` and `m33_pcm_probe_ignored_count` when `m55qa_probe_pcm_on` enables M33 PCM probe mode.
- Treat only a clean-count run after `m55qa_probe_pcm_on` as authoritative.

Validated:
- Clean-count human QA after reflashing showed `probe_lwip=87/0`, `xz_last=143/274560`, `xz_fail=0`, and `tx_pending=0`.
- The same run still had no platform STT/TTS (`srv_stt=0`, `srv_tts=0/0/0`, `xz_rx=1/0`), so the remaining issue is above board uplink/IPC.

Boundary:
- If clean-count QA shows `probe_lwip=87/0` and `xz_last` grows, do not investigate WiFi/token/IPC. Inspect XiaoZhi relay/platform behavior after `listen/stop`.

## 2026-06-24 - "请再说一遍" can be a platform fallback even when the server received audio

Symptoms:
- User hears or sees repeated `"请再说一遍"` and suspects the device did not enter the server.
- Public cloud dashboard for `nanopi-m5` may still show real server entry:
  - `audio_format=opus`
  - `asr_called=true`
  - `sent_frames>0`
  - `sent_bytes>0`
- A prior recognized transcript `嗯，你是什么模型？` reached model relay, but model relay returned:
  - `classification.type=none`
  - `operator_facing_reply=请再说一遍。`
  - `provider.configured=false`

Root cause:
- The board and XiaoZhi WebSocket were not the primary failure.
- Cloud ASR/TTS keys existed, but the dedicated model relay key was missing. The relay fallback classified normal voice questions as `none`, causing a fixed retry phrase.

Fix / trick:
- Platform commit `1764e91b` makes model relay safely reuse the server-side XiaoZhi ASR/TTS key when the dedicated model relay key is absent.
- Voice questions from `voice_intent` / `vla_language_from_voice` now fall back to `daily_chat` if they contain meaningful text and no rehab-command words.
- Fallback reply for daily chat is no longer `"请再说一遍。"` when ASR produced text.

Validation:
- Cloud health shows `deployment.build_sha=1764e91b140b`.
- Cloud smoke for prompt `你是什么模型` returned:
  - `classification.type=daily_chat`
  - `provider.configured=true`
  - `external_call_ok=true`
  - a natural model reply.

Boundary:
- Do not debug WiFi/token when `xz_ws=1`, `token_len=442`, `srv_hello=1`, and dashboard shows Opus audio frames or ASR/TTS counters.
- If the new turn still says `"请再说一遍"`, first check `asr_ok/asr_error/asr_text`; only empty ASR text points back to capture/audio quality.
- If ASR text exists but reply is wrong, inspect platform model relay classification and key configuration.

## 2026-06-24 - Opus TTS must be paced at audio frame duration, not 20 ms

Symptoms:
- Platform reports `audio_format=opus`, `opus_packet_count>0`, and `sent_frames>0`, but the user hears no intelligible voice or only noise.
- A pre-fix dashboard showed `tts_send_timeout:frame=61`.

Root cause:
- The cloud was sending each TTS Opus packet after a fixed 20 ms sleep even though the XiaoZhi session declares `frame_duration=60`.
- This can push 60 ms audio packets at roughly 3x real-time speed and overwhelm the M55/M33 speaker path.

Fix / trick:
- Platform commit `1764e91b` paces TTS downlink at `audio_params.frame_duration`, clamped to 10-120 ms.
- Official 60 ms Opus sessions now send TTS packets every 60 ms.

Validation:
- Added and passed `test_rehab_arm_xiaozhi_websocket_paces_official_opus_tts_at_frame_duration`.
- Cloud selected XiaoZhi tests passed after deployment.

## 2026-06-24 - LVGL stop freeze can be caused by synchronous M55 WebSocket send

Symptoms:
- Pressing LVGL stop appears to freeze the XiaoZhi UI.
- WiFi/token/WebSocket status can still be healthy.

Root cause:
- The stop action used M55 `voice_service_stop_xiaozhi_talk()`.
- That path synchronously flushed a tail frame and sent `listen stop`; the WebSocket send path blocks on lwIP `tcpip_callback_with_block`.
- If tcpip is busy, the UI worker waits and the user sees a frozen stop/thinking state.

Fix / trick:
- M55 manual/LVGL stop now calls `voice_service_stop_xiaozhi_listening_async()` and returns immediately.
- `xz_stop` performs the server notification in the background.
- Automatic EOU can still flush tail audio; manual stop favors UI responsiveness over the last partial frame.

Validation:
- `m55qa_capture_off` returns ACK with `tx_pending=0`.
- A later `m55qa_status` showed `xz_listening=0`, `xz_ws=1`, `srv_tts=1/1/0`, `tts_fwd=58/237568`, and `tts_fail=0`.

Boundary:
- If LVGL still freezes after this firmware, first check `lvgl_flush` and shell responsiveness. Do not assume platform or WiFi unless `xz_ws/token/wlan` regress.
