---
type: repo
repo: cyijun/hachimi
domain: voice-pipeline
question_match: voice-pipeline/Q3
status: active
decision: deepdive
discovered: '2026-05-20'
last_reviewed: '2026-05-20'
license:
  detected: MIT
  in_whitelist: 'true'
  harvest_allowed: 'true'
signals:
  stars: '4'
  last_commit_age_days: '119'
  active_contributors: '1'
---
## 一句话定位
一个基于多进程队列和事件信号实现低延迟用户中断（barge-in）的Python语音助手核心框架。

## 它解决了哪个具体问题
voice-pipeline/Q3: barge-in 中断状态机

## 关键文件
- `main.py:1-80` — 多进程与全局事件/队列的架构定义
- `src/voice_listener.py:1-250` — 唤醒词检测与中断事件触发逻辑
- `src/tts.py:1-150` — TTS播放进程，监听中断事件以停止播放

## 它做对了什么
- **使用全局 `multiprocessing.Event` 作为中断信号**，解耦进程间状态同步。evidence: `main.py:33-34` 创建 `interrupt_event`，并在所有进程间传递。
- **在唤醒词检测中直接设置中断事件**，实现低延迟触发。evidence: `src/voice_listener.py:230-250` 检测到唤醒词后调用 `interrupt_event.set()`。
- **TTS播放进程轮询检查中断事件**，及时停止音频流。evidence: `src/tts.py:130-150` 在播放循环中检查 `if interrupt_event.is_set(): break`。
- **队列作为进程间缓冲**，允许STT和LLM进程自然消费完中断前的数据，避免复杂的状态回滚。evidence: `main.py:18-28` 定义了 `audio_queue`, `text_queue`, `tts_queue`。

## 它不适合我的地方
- **中断逻辑过于简单**，没有显式的状态机来管理“中断中”、“恢复”等状态，仅依赖一个二进制事件。
- **缺乏部分转写（partial transcript）的转发机制**，中断时STT进程可能正在处理音频，其部分结果未被收集和传递。
- **深度依赖特定云API（SiliconFlow）**，其STT/TTS的流式控制逻辑封装在云端，难以借鉴其客户端侧的取消逻辑。

## 我打算抄走什么
- `main.py:18-34` 中基于 `multiprocessing.Queue` 和 `Event` 的进程间通信骨架，特别是将 `interrupt_event` 作为核心控制信号传递给所有子进程的模式。
- `src/tts.py:130-150` 中在音频播放循环内轮询检查 `interrupt_event` 并立即 `break` 的清理模式。

## License 与合规
- 检测为 MIT 许可证，在白名单内，允许吸收代码片段。
- 使用时需保留原版权声明。

## 下一步（只允许 1 条）
- [ ] 将 `main.py` 中的进程间通信骨架（Queue + Event）移植到 openclaw-voice-bot 作为基础架构原型。
