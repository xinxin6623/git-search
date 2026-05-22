---
type: repo
repo: owner/name
domain: voice-pipeline
question_match: voice-pipeline/Q3
status: active
decision: deepdive  # 来自 triage，可被人工改为 harvest/adopt/watch
discovered: 2026-05-20
last_reviewed: 2026-05-20

license:
  detected: MIT
  in_whitelist: true
  harvest_allowed: true

signals:
  stars: 0
  last_commit_age_days: 0
  active_contributors: 0
---

## 一句话定位
[本质上解决什么问题]

## 它解决了哪个具体问题
voice-pipeline/Q3: barge-in 中断状态机

## 关键文件
- `src/pipeline/interrupt.py:42-180` — 中断状态机核心
- `src/audio/buffer.py:60-95` — playback queue 清理

## 它做对了什么
- [设计点 1] | evidence: src/pipeline/interrupt.py:67
- [设计点 2] | evidence: README L88-95

## 它不适合我的地方
- [限制 1]
- [限制 2]

## 我打算抄走什么
- `src/audio/buffer.py:60-95` 的 queue flush 实现

## License 与合规
- MIT，可自由 harvest
- 需保留 copyright header

## 下一步（只允许 1 条）
- [ ] 复制 buffer.py:60-95 进 openclaw-voice-bot 试用

---
## 已用于
（此区域由人工在使用后追加，不由 LLM 生成）
