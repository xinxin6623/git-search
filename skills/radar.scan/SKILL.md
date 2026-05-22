---
name: radar.scan
description: 按 rubrics/scan.md 中的 query 集调用 gh CLI 搜索仓库，追加候选到 voice-pipeline/candidates.md。无 LLM 调用。
trigger: 手动 `radar scan <direction>` 或 cron 每日
---

# radar.scan

## 职责
1. 加载 `rubrics/scan.md`（作为系统提示一部分，但本 Skill 不调用 LLM）
2. 解析 query 集，逐个执行 `gh search repos <query> --json fullName,stargazersCount,pushedAt,description,license --limit 15`
3. 应用负面词过滤
4. 与 `voice-pipeline/candidates.md` 去重
5. 追加新候选，标记 `[ ]`
6. 完整原始输出写入 `runs/{date}-{time}/scan-results.json`
7. 快照本次执行的 `rubrics/scan.md` 到 `runs/{date}-{time}/rubric-snapshot.md`

## 输入
- `direction`: e.g. `voice-pipeline`（决定加载哪条 question）
- 隐式输入: 当前 `rubrics/scan.md`

## 输出
- 追加: `voice-pipeline/candidates.md`
- 新建: `runs/{date}-{time}/scan-results.json` + `rubric-snapshot.md`

## 失败处理
- gh 未登录 → 提示并停止
- query 单条失败 → 跳过该 query，记入 summary，不影响其他
- 全部失败 → 写 summary.md 并非零退出

## 不做的事
- 不调用 LLM
- 不评判，不丢弃（除负面词命中）
- 不接 HN / arXiv（Phase 1 source budget = gh 100%）

## 实现备注
- 语言: bash 或 python 皆可，Phase 1 优先 bash
- 依赖: `gh` CLI、`jq`
- 估算行数: ~80 行
