---
name: radar.deepdive
description: 加载 rubrics/deepdive.md 作为 system prompt，对指定 repo 调用远端强模型（claude-sonnet-4.6 / deepseek-v3）生成结构化 entry。
trigger: 手动 `radar deepdive owner/repo1 [owner/repo2 ...]`
---

# radar.deepdive

## 职责
1. 加载 `rubrics/deepdive.md` + entry 模板（`voice-pipeline/entries/_TEMPLATE.md`）作为系统提示
2. 拉取必读资源:
   - README 全文（≤ 8000 字）
   - 文件树深度 3
   - 入口文件 1-2 个（自动猜测或 `--entry path` 指定）
   - LICENSE
   - `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml` 任一
3. 调用 LLM，生成符合 entry 模板的 markdown
4. 写入 `voice-pipeline/entries/{owner}-{name}.md`
5. 完整 trace 写入 `runs/{date}-{time}/deepdive-trace.jsonl`

## 输入
- 一个或多个 `owner/repo`
- 可选 `--entry <path>` 强制指定入口文件
- 隐式: 当前 `rubrics/deepdive.md`

## 输出
- `voice-pipeline/entries/{owner}-{name}.md`
- `runs/{date}-{time}/deepdive-trace.jsonl` + `rubric-snapshot.md` + `summary.md`

## 模型路由
```yaml
model: claude-sonnet-4.6   # via LiteLLM
fallback: ollama/qwen3:14b # 远端不可用时本地降级（标注 quality=degraded）
max_runs_per_week: 5       # 由调用方维护配额计数
timeout: 180s
```

## 强校验
- 缺 `question_match` → 退出，不写文件
- license 不在白名单 → entry 自动去掉"我打算抄走什么"章节，只保留"可借鉴的设计"
- "下一步" 章节 > 1 条 → 退出
- 关键文件未给 lines → 退出

## 不做的事
- 不复述 README
- 不为没有 question_match 的 repo 强行写 entry
- 不读 issue / PR 评论

## 实现备注
- 语言: python
- 依赖: `litellm`, `pyyaml`, `jsonschema`, `gh` CLI（拉文件树）
- 估算行数: ~200 行
