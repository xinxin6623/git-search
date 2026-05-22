# Scan Rubric v1
# 修改日志见 git log

## 当前 question（从 questions.md 派生）
- voice-pipeline/Q3: barge-in 中断状态机
  - 关键词: cancellation, interrupt, barge-in, playback queue, state machine

## 搜索策略
执行 `gh search repos`，每个 query 取 top 15。

### Query 集
- `"voice barge-in interrupt python"`
- `"tts playback queue cancel streaming"`
- `"voice agent interrupt state machine"`
- `"streaming asr partial transcript llm"`

### 负面词过滤（命中即丢）
- call-center, ivr, sip, webrtc-sfu
- enterprise, multi-tenant, rbac
- kubernetes-operator

### Source budget（Phase 1）
- gh search: 100%
- 手动种子: 0
- HN / arXiv: 不接入

## 输出格式
追加到 `voice-pipeline/candidates.md`，每条:

```
- [ ] owner/name · ★stars · 提交Nd · "短描述"
```

去重: 对比 candidates.md 历史，已存在的 repo 跳过。

## 我的修改记录
- 2026-05-20 v1 初版
