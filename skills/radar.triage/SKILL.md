---
name: radar.triage
description: 加载 rubrics/triage.md 作为 system prompt，对 candidates.md 中未处理的 repo 调用 LLM 输出 reject/maybe/deepdive 决策与 reasoning。模型由根目录 config.yaml 控制。
trigger: 手动 `python3 skills/radar.triage/triage.py <direction> [--since YYYY-MM-DD] [--limit N] [--profile NAME] [--dry-run]`
---

# radar.triage

## 职责
1. 加载 `rubrics/triage.md` 全文作为系统提示
2. 加载 `<direction>/questions.md` 作为可匹配 question 集
3. 从 `candidates.md` 取 `[ ]` 标记条目（跳过 fenced code 中的示例）
4. 对每个 repo 用 `gh` 拉元数据 / README(前 3000 字) / 文件树（深度 2）
5. 调用 LLM（按 `config.yaml` 的 `triage.active` profile）输出 YAML
6. JSON Schema 校验，缺字段或 reasoning 短于 100 字 → 丢弃
7. 写入 `<direction>/inbox/{date}-{owner}-{name}.md`
8. 完整 trace 追加到 `runs/{ts}-triage/triage-trace.jsonl`
9. 把 candidates.md 对应行 `[ ]` 改成 `[x]`

## 配置（统一在 `config.yaml`）

切模型 = 改 `triage.active` 字段。可选 profile（开箱即用）:
- `siliconflow-qwen3-omni-30b-thinking` (默认，需 `SILICONFLOW_API_KEY`)
- `siliconflow-qwen3-14b`
- `siliconflow-deepseek-v32`
- `local-qwen3-14b` (需 `ollama pull qwen3:14b` ~9GB)
- `local-qwen3-4b` (1-2GB，验证管线足够)
- `cloud-deepseek-chat` (需 `DEEPSEEK_API_KEY`)
- `cloud-gpt-4o-mini` (需 `OPENAI_API_KEY`)

加 profile / 接 LiteLLM Proxy：直接在 `config.yaml` 里加块即可，无需改代码。

CLI 临时覆盖：`--profile siliconflow-qwen3-14b`

## Setup

```bash
# Python 依赖
pip3 install --break-system-packages litellm pyyaml jsonschema

# 默认 profile：硅基流动 API key
# https://cloud.siliconflow.cn/account/ak
export SILICONFLOW_API_KEY=sk-...

# 或本地 ollama（备用）
# ollama pull qwen3:14b
# ollama pull qwen3:4b

# 或其他云端
# export DEEPSEEK_API_KEY=sk-...
# export OPENAI_API_KEY=...
```

## 输入
- `direction`: e.g. `voice-pipeline`
- `--since YYYY-MM-DD`: 仅处理该日期之后 scan 追加的候选
- `--limit N`: 最多处理 N 条
- `--profile NAME`: 临时覆盖 config.yaml 的 active
- `--dry-run`: 只 fetch + 构造 prompt，不调 LLM（不需要 litellm）

## 输出
- `<direction>/inbox/{date}-{owner}-{name}.md`
- `runs/{ts}-triage/`：rubric 快照 + triage-trace.jsonl + summary.md

## 必含字段（schema 强制，缺一即丢弃）
`repo`, `decision`, `question_match`, `license_detected`, `reasoning`（>100 字）, `evidence`

## 失败模式
- LLM 调用失败 → 立刻停止整次 triage（设计原则：失败即停）
- 单条输出 schema 不符 → 该条记 error，继续下一条
- fetch（gh）失败 → 该条记 error，继续下一条

## 不做的事
- 不读 issue / PR 内容（Content Trust）
- Phase 1 不自动重试，不静默 fallback

## 实现备注
- 文件: `triage.py` (~330 行)
- 配置加载: `skills/_lib/config.py`
- 依赖: `litellm`, `pyyaml`, `jsonschema`, `gh` CLI
