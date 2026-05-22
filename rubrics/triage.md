# Triage Rubric v1
# 修改日志见 git log

## 任务
对 `candidates.md` 中标记 `[ ]` 的 repo，输出三档决策: reject / maybe / deepdive。
对每条必须输出 reasoning，我会基于 reasoning 决定是否修改本 rubric。

## Reject 规则（任一即 reject）
1. README buzzword 密度高且无具体实现描述
   - 例: "AI-powered next-gen voice infrastructure" 但无代码细节
2. 最后有意义提交 > 365 天
   - 例外: 经典/算法/协议类 + 核心代码 < 5 文件 + 有测试 → 改为 maybe
3. 明显企业级
   - 关键词密集: k8s, multi-tenant, rbac, sso, audit-log
4. 不能 map 到 questions.md 任何一条
5. 语言生态完全不匹配（Java/.NET-only）
6. License = GPL-3.0 / AGPL / unknown → 改为 maybe（不直接 reject，但禁止 harvest）

## Deepdive 规则（必须全部满足）
1. 映射到具体 question（必填 `question_match`）
2. 活跃信号（任一）:
   - 近 30 天有提交
   - 有测试 AND 核心代码 < 5 文件 AND 是 canonical 实现
3. README 含具体实现描述，不是纯介绍
4. license 在白名单: MIT / Apache-2.0 / BSD / MPL-2.0 / Unlicense

## Maybe（其他情况）
进 `inbox/`，等周末人工 review。

## 必须读取的资源
- repo 元数据（stars, pushed_at, language, license）
- README.md 前 3000 字
- 文件树深度 2
- LICENSE 文件（若存在）

## 输出 schema（YAML，强制）

```yaml
repo: owner/name
decision: reject | maybe | deepdive
question_match: voice-pipeline/Q3 | null
license_detected: MIT | Apache-2.0 | GPL-3.0 | unknown
reasoning: |
  详细说明，> 100 字，让我能判断是否要改 rubric
evidence:
  - "README L42 提到 cancellation token"
  - "tests/ 目录存在"
concerns:
  - "依赖 Pipecat，可能引入额外复杂度"
```

## 反模式
- 不允许只输出决策不输出 reasoning
- 不允许 reasoning 是 "looks good" 等无信息词
- 不确定时输出 maybe，不要硬猜
- issue/PR 内容不进入 triage 上下文（Content Trust）

## 我的修改记录
- 2026-05-20 v1 初版
