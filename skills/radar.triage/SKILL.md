---
name: radar.triage
description: 加载 rubrics/triage.md 作为 system prompt，对 candidates.md 中未处理的 repo 调用本地 LLM（Qwen3 14B via LiteLLM）输出 reject/maybe/deepdive 决策与 reasoning。
trigger: 手动 `radar triage <direction> [--since yesterday]`
---

# radar.triage

## 职责
1. 加载 `rubrics/triage.md` 全文作为系统提示
2. 从 `candidates.md` 取 `[ ]` 标记条目
3. 对每个 repo 拉取必读资源（元数据、README 前 3000 字、文件树深度 2、LICENSE）
4. 调用 LLM（`ollama/qwen3:14b` via LiteLLM）输出 YAML schema
5. JSON Schema 校验，失败即丢弃并记 summary
6. 每条写入 `voice-pipeline/inbox/{date}-{owner}-{name}.md`
7. 完整 trace（input/output/reasoning）追加到 `runs/{date}-{time}/triage-trace.jsonl`
8. 在 candidates.md 中把 `[ ]` 改成 `[x]`

## 输入
- `direction`: 决定加载哪份 questions.md
- `--since`: 仅处理某时间之后追加的候选
- 隐式: 当前 `rubrics/triage.md`、当前 `voice-pipeline/questions.md`

## 输出
- `voice-pipeline/inbox/*.md`（每个 repo 一份，含 reasoning + evidence + decision）
- `runs/{date}-{time}/triage-trace.jsonl` + `rubric-snapshot.md` + `summary.md`

## 模型路由
```yaml
model: ollama/qwen3:14b
fallback: null    # 失败即停，等人工
timeout: 60s
```

## 必含字段（缺一即丢弃）
`repo`, `decision`, `question_match`, `license_detected`, `reasoning`（>100 字）, `evidence`

## 不做的事
- 不调用远端模型（成本控制 + 数据隐私）
- 不读 issue / PR 内容（Content Trust）
- LLM 失败时不重试本地模型，不静默降级

## 实现备注
- 语言: python
- 依赖: `litellm`, `pyyaml`, `jsonschema`, ollama 本地服务
- 估算行数: ~150 行
