# voice-pipeline questions

Phase 1 仅追 Q3。其他 question 留空，等 Phase 2 解锁。

---

## Q3: barge-in 中断状态机

**问题**: 在 TTS 播放过程中用户开口，如何低延迟地取消当前播放、清空 playback queue、并把 ASR 部分转写 forward 给 LLM，且整个过程是可恢复、状态机清晰的？

**关键词**: cancellation, interrupt, barge-in, playback queue, state machine, streaming asr

**需要的参考实现类型**:
- 中断状态机源代码（不要框架，要 < 5 文件的核心实现）
- playback queue 的 flush / cancel 逻辑
- 部分转写 (partial transcript) 与最终转写 (final transcript) 的合流策略

**已知不要什么**:
- 整套 enterprise voice infra
- 仅 demo / hello world 级别
- 仅 JS / browser-only（我们是 python 后端）

---

## Q1, Q2, Q4+
Phase 1 不接，留空。
