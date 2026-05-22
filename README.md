# 个人技术雷达系统 (ai-radar)

按 [radar-system-v2.1.md](./radar-system-v2.1.md) 实施。Phase 1 仅跑 `voice-pipeline/Q3`。

> **核心架构**: Rubric-as-Interface — 系统的"判断逻辑"全部外化为 [rubrics/](./rubrics/) 下的 markdown 文件。每次 LLM 调用加载最新 rubric。人工的核心维护动作 = 编辑 rubric。

## 目录结构

```
.
├─ rubrics/                    # 【核心】人工调参界面
│   ├─ scan.md
│   ├─ triage.md
│   └─ deepdive.md
├─ skills/                     # 自动化执行层（代码稳定）
│   ├─ radar.scan/SKILL.md
│   ├─ radar.triage/SKILL.md
│   └─ radar.deepdive/SKILL.md
├─ voice-pipeline/             # 知识库主体（Phase 1 唯一方向）
│   ├─ README.md
│   ├─ questions.md            # Phase 1 仅 Q3
│   ├─ candidates.md           # scan 输出
│   ├─ inbox/                  # triage 输出
│   ├─ entries/                # deepdive 输出 + 人工 polish
│   │   └─ _TEMPLATE.md
│   └─ refs.md                 # 使用追踪
├─ runs/                       # 每次执行的完整 trace（gitignore，本地保留）
├─ decisions.md                # 人工 override 累计记录
└─ radar-system-v2.1.md        # 设计文档
```

> **部署路径**: 设计文档使用 `~/.ai-radar/` 作为部署根目录。本仓库为版本管控副本，部署时可 `ln -s` 或 rsync 到 `~/.ai-radar/`。

## 模型配置

所有 LLM 调用走根目录 [`config.yaml`](./config.yaml)，按阶段（triage / deepdive）独立路由。切模型只改配置，不动代码：

```yaml
triage:
  active: siliconflow-qwen3-omni-30b-thinking   # ← 改这里
  profiles:
    siliconflow-qwen3-omni-30b-thinking: ...    # 默认（OpenAI 兼容协议）
    siliconflow-qwen3-14b: ...
    siliconflow-deepseek-v32: ...
    local-qwen3-14b: ...                        # ollama 本地备用
    cloud-deepseek-chat: ...
    cloud-gpt-4o-mini: ...
    ...
```

支持 SiliconFlow（硅基流动）/ 本地 ollama / 云端（OpenAI / Anthropic / DeepSeek / 自建 LiteLLM Proxy）。完整字段见 `config.yaml` 注释。

## 五步管线

```
[1. SCAN]      rubrics/scan.md + gh CLI  →  candidates.md
[2. TRIAGE]    rubrics/triage.md + Qwen3 14B (local) → inbox/*.md
[3. REVIEW]    人工浏览 inbox + 改 rubric → decisions.md
[4. DEEPDIVE]  rubrics/deepdive.md + 远端 LLM → entries/*.md
[5. POLISH]    人工改写 entry，使用时追加 refs.md
```

## 工作流（典型一周）

### 周日晚 60 分钟

1. **(15 min) 改 rubric** ← 最重要的动作
   - 翻 `decisions.md`，找出反复 override 的模式
   - 改 `rubrics/*.md` 对应章节
   - `git commit -m "rubric: <change>"`
2. **(5 min) 触发 scan** — `radar scan voice-pipeline`
3. **(5 min) 触发 triage** — `radar triage voice-pipeline --since yesterday`
4. **(20 min) Review inbox** — override 记 `decisions.md`
5. **(10 min) 触发 deepdive**（本周限 ≤ 3 条）— `radar deepdive owner/repo`
6. **(5 min) Polish entries**

### 写代码时
- `/radar voice interrupt` 查 entry
- 用了某 entry → 在该 entry 末尾追加"已用于"，同步追加到 `refs.md`

### 月度（60 min）
- `git log rubrics/` 看演化曲线
- 把高频 override 模式提炼进 rubric

## Phase 1 成功标准（必须全部满足）

| 标准 | 衡量方式 |
| --- | --- |
| 知识库被实际使用 | `refs.md` ≥ 1 条 |
| Rubric 在演化 | `git log rubrics/` ≥ 3 次有意义修改 |

第二条比第一条更重要。

## 失败信号（触发即停止扩张）
- 4 周内 rubric 修改次数 = 0
- 4 周内 entries = 0
- 4 周内 refs.md = 空
- inbox 累计未 review > 30 条

## 设计文档
完整设计见 [radar-system-v2.1.md](./radar-system-v2.1.md)。
