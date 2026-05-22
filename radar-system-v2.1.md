# 个人技术雷达系统 设计方案 v2.1(全自动化 + 人工调参版)

| 项目 | 说明 |
| --- | --- |
| 版本 | v2.1(对 v2.0 过度收缩的修正) |
| 日期 | 2026-05-20 |
| 状态 | 待审核 |
| 与前版关系 | 全管线自动化 = v1.2;人工调参界面 = v2.0 简洁;两者合体 |
| Phase 1 预计实施 | 3 周,总投入 15–20 小时 |

---

## 摘要

本版本修正 v2.0 的核心误读。v2.0 把"减少机制复杂度"错误地解读为"砍掉自动化与 LLM",这违背了系统初衷。

**正确架构:**

> **自动化全开 + LLM 全管线 + 人工掌控"判断层" + 人工高频修改 rubric**

核心架构创新:**Rubric-as-Interface**(评判标准即接口)

- 系统的"判断逻辑"不写在代码里,不藏在 prompt 里
- 全部外化为可读可改的 markdown rubric 文件
- 每次 LLM 调用加载最新 rubric 作为系统提示一部分
- 人工的核心维护动作 = 编辑 rubric markdown
- 系统智能度随 rubric 演化而提升,与代码改动解耦

**关键产出物的优先级反转:**

| 优先级 | v1.2 | v2.0 | v2.1 |
| --- | --- | --- | --- |
| 第一资产 | entries + eval | entries | **rubrics**(演化的判断标准) |
| 第二资产 | rubrics | (无 rubric) | entries(rubric 的产物) |
| 第三资产 | trace | refs | runs/(可审计的执行 trace) |

---

## 一、对 v2.0 的修正

| v2.0 错误 | v2.1 修正 |
| --- | --- |
| 砍掉 LLM,改用人工过候选 | LLM 全管线接入(scan/triage/deepdive 三步都用) |
| Phase 1 不接 Agent Kernel | Phase 1 即接入,但只 load 必要 Skill |
| 收集脚本只调 gh CLI | scan 用 gh CLI 取候选,triage 立刻接 LLM 评判 |
| "人工 review 输出"为主 | "人工编辑 rubric"为主,review 输出是触发 rubric 修改的信号 |
| 知识库只是 markdown 笔记 | 知识库 = LLM 按 rubric 生成的结构化 entry,人工可改写 |

**保留 v2.0 的正确判断:**

- 三阶段渐进,不一次建完
- Phase 1 仍只跑 voice-pipeline/Q3 一个问题
- 仍不引入 gold set / L1-L4 used 分级 / Pattern 两级制 等过早的评估机制
- 仍保持"无损降级回 markdown 笔记"的退场策略

---

## 二、核心架构:Rubric-as-Interface

### 2.1 三层分离

```
┌─────────────────────────────────────────────┐
│  Layer 3: 人工调参层 (Markdown,频繁编辑)      │
│  ~/.ai-radar/rubrics/                       │
│  ├─ scan.md      搜索策略 / 关键词 / 负面词    │
│  ├─ triage.md    粗筛标准 / reject 规则      │
│  └─ deepdive.md  深度分析模板 / 输出 schema   │
└─────────────────────────────────────────────┘
                    ↓ 加载
┌─────────────────────────────────────────────┐
│  Layer 2: 自动化执行层 (Skill 代码,稳定)       │
│  ~/.ai-radar/skills/                        │
│  ├─ radar.scan/                             │
│  ├─ radar.triage/                           │
│  └─ radar.deepdive/                         │
└─────────────────────────────────────────────┘
                    ↓ 产出
┌─────────────────────────────────────────────┐
│  Layer 1: 知识资产层 (Markdown,LLM 写 + 人改) │
│  ~/.ai-radar/voice-pipeline/                │
│  ├─ candidates.md  scan 输出                 │
│  ├─ inbox/         triage 输出,带 reasoning  │
│  ├─ entries/       deepdive 输出,人改后入库   │
│  └─ refs.md        使用追踪                  │
└─────────────────────────────────────────────┘

跨层反馈:
~/.ai-radar/decisions.md   人工 override 记录 → 反哺 rubric 修改
~/.ai-radar/runs/{date}/   每次执行的完整 trace,可重现
```

### 2.2 关键设计原则

1. **Rubric 是系统的"权重"**:类比神经网络的权重,只是它是人类可读的 markdown
2. **Skill 代码极少改动**:Skill 只负责"加载 rubric + 调 LLM + 校验输出 + 写入文件"
3. **每次 LLM 调用都展示完整 reasoning**:人工才能判断 rubric 该怎么改
4. **rubric 用 git track**:演化历史就是系统"学习曲线"
5. **decisions.md 是 rubric 修改的依据**:积累足够 override → 触发 rubric 调整

---

## 三、自动化管线(Phase 1 即全部启用)

### 3.1 五步完整管线

```
[1. SCAN]                    [人工触发,或 cron 每日]
  rubrics/scan.md  +  gh CLI  →  voice-pipeline/candidates.md
                                  ↓
[2. TRIAGE]                  [自动接力,Qwen3 14B 本地]
  rubrics/triage.md  +  LLM   →  voice-pipeline/inbox/*.md
                                  (含 reasoning + 决策)
                                  ↓
[3. HUMAN REVIEW]            [周日 30 分钟]
  人工浏览 inbox/             →  override 决策记 decisions.md
                                  →  顺手改 rubric 若有发现
                                  ↓
[4. DEEPDIVE]                [人工触发,远端 LLM via LiteLLM]
  rubrics/deepdive.md  +  LLM  →  voice-pipeline/entries/*.md
                                  (结构化 entry + evidence)
                                  ↓
[5. HUMAN POLISH]            [写代码时随手]
  人工改写 entry              →  entries/*.md 最终入库
  使用时追加"已用于"           →  refs.md
```

### 3.2 每步必须的属性

| 步骤 | 输入 | LLM | 输出位置 | 必须包含 |
| --- | --- | --- | --- | --- |
| scan | rubrics/scan.md + question | 无 | candidates.md | repo 列表 + 基础信号 |
| triage | rubrics/triage.md + candidate | Qwen3 14B 本地 | inbox/*.md | 决策 + reasoning + evidence |
| deepdive | rubrics/deepdive.md + repo | 远端强模型 | entries/*.md | 结构化字段 + key files + license |

**所有 LLM 输出必须包含 reasoning 字段。** 没有 reasoning,人工就无法判断 rubric 该不该改。

### 3.3 模型路由(基于已有 LiteLLM)

```yaml
triage:
  model: ollama/qwen3:14b           # 本地,Mac mini M4
  reason: 量大、便宜、人工兜底
  fallback: null                     # 失败即停,等人工

deepdive:
  model: claude-sonnet-4.6 / deepseek-v3
  reason: 结构化输出质量更重要
  fallback: ollama/qwen3:14b         # 远端不可用时降级
  max_runs_per_week: 5               # 成本控制
```

---

## 四、人工在 Phase 1 的核心角色

### 4.1 五个动作(按重要性排序)

| 动作 | 频率 | 时长 | 产出 |
| --- | --- | --- | --- |
| **编辑 rubric** | 每周 | 15 分钟 | rubrics/*.md 的 git diff |
| Review inbox 决策 | 每周 | 20 分钟 | decisions.md 追加 |
| Review/改写 entries | 每条 deepdive 后 | 10 分钟 | entries/*.md 修订 |
| 写代码时使用 entry | 随机 | 0(自然发生) | refs.md 追加 |
| 月度 rubric 大调整 | 每月 | 1 小时 | rubric 整段重写 |

**重点:第一动作是改 rubric,不是改 entry。改 entry 是治标,改 rubric 是治本。**

### 4.2 人工 review 时的判断框架

每条 inbox 决策,人工只问三个问题:

1. **LLM 的决策对吗?** 不对 → 标 override,记 decisions.md
2. **不对的话,是 rubric 漏写了规则吗?** 是 → 顺手改 rubric
3. **是 rubric 写错了吗?** 是 → 改 rubric

如果人工 override 但**没有** rubric 可改,记 decisions.md 等积累 → 月度 review 时提炼。

### 4.3 一次典型的 rubric 修改

假设本周发现 LLM 把一个"老但稳定且经典"的算法 demo repo 给 reject 了:

**编辑前 `rubrics/triage.md`(节选):**
```markdown
## Reject 规则
- 最后一次有意义提交 > 180 天 → reject
```

**编辑后:**
```markdown
## Reject 规则
- 最后一次有意义提交 > 180 天 → 默认 maybe(不再直接 reject)
  - 例外:若同时满足以下,允许 deepdive
    - 文件树小(核心 < 5 文件)
    - 有测试
    - 是算法/协议/数据结构的经典实现
    - README 无营销性词汇
```

下次跑 triage,LLM 行为立刻改变。这就是 Rubric-as-Interface 的价值。

---

## 五、目录结构(完整)

```
~/.ai-radar/
│
├─ rubrics/                       # 【核心】人工调参界面
│   ├─ scan.md                    # 搜索关键词、负面词、source budget
│   ├─ triage.md                  # 三档决策规则、reject 标准、活跃度策略
│   └─ deepdive.md                # entry 输出 schema、强制字段
│
├─ skills/                        # 自动化执行层(代码稳定)
│   ├─ radar.scan/SKILL.md
│   ├─ radar.triage/SKILL.md
│   └─ radar.deepdive/SKILL.md
│
├─ voice-pipeline/                # 知识库主体(Phase 1 唯一方向)
│   ├─ README.md                  # 方向定义
│   ├─ questions.md               # 当前问题(Phase 1 仅 Q3)
│   ├─ candidates.md              # scan 累计输出
│   ├─ inbox/                     # triage 输出,人工 review 后或入 entries 或丢弃
│   │   └─ {date}-{repo}.md
│   ├─ entries/                   # deepdive 输出,最终知识库
│   │   └─ owner-name.md
│   └─ refs.md                    # 使用追踪
│
├─ runs/                          # 每次执行的完整 trace(可审计、可重现)
│   └─ 2026-05-20-1430/
│       ├─ scan-results.json      # gh CLI 原始输出
│       ├─ triage-trace.jsonl     # 每条 triage 的 input/output/reasoning
│       ├─ rubric-snapshot.md     # 本次执行时的 rubric 版本快照
│       └─ summary.md
│
└─ decisions.md                   # 人工 override 累计记录,reasoning 池
```

---

## 六、Phase 1 工作流(典型一周)

### 周日晚 60 分钟 review

1. **(15 min)改 rubric** ← 这是本周最重要的动作
   - 翻上周 decisions.md
   - 找出反复 override 的模式
   - 改 rubric 对应章节
   - `git commit -m "rubric: relax stale-but-canonical exception"`

2. **(5 min)触发 scan**
   ```bash
   radar scan voice-pipeline
   ```
   → 追加新 candidates 到 candidates.md

3. **(5 min)触发 triage**
   ```bash
   radar triage voice-pipeline --since yesterday
   ```
   → 输出到 inbox/

4. **(20 min)Review inbox**
   - 浏览每条 LLM 决策 + reasoning
   - 不同意的标记 override,reasoning 写 decisions.md
   - 同意 deepdive 的,触发下一步

5. **(10 min)触发 deepdive(本周限 ≤ 3 条)**
   ```bash
   radar deepdive owner/repo1 owner/repo2
   ```
   → 输出到 entries/

6. **(5 min)Polish entries**
   - 改写 LLM 没抓住的部分
   - 删掉过分包装的形容词

### 写代码时(任意时刻)

- Claude Code 内 `/radar voice interrupt`
  - Slash command 跑 SQLite FTS(若已上)或 grep entries/
  - 返回相关 entry 路径列表
- 我用了哪个 → 在该 entry 末尾追加:
  ```markdown
  ## 已用于
  - 2026-06-03: openclaw-voice-bot, 改写了 interrupt.py 状态机
  ```
  并同步追加一行到 refs.md

### 月度(60 分钟)

- 跑 `git log rubrics/` 看 rubric 演化曲线
- 翻 decisions.md,把高频 override 模式提炼进 rubric 大章节
- 删过时 entries(60 天无引用 + 主观判断已过时)

---

## 七、Rubric 文件初稿

完整初稿见**附录 A、B、C**。这里只列关键结构:

### 7.1 `rubrics/scan.md` 结构

```markdown
# Scan Rubric v1

## 当前 question
- voice-pipeline/Q3: barge-in 中断状态机

## 搜索查询(每周可调)
- "voice barge-in interrupt python"
- "tts playback queue cancel streaming"
- "voice agent interrupt state machine"

## 负面过滤
- enterprise / call-center / k8s / multi-tenant

## Source budget
- gh search repos: 100%
- 手动种子: 留空 (Phase 1 阶段)
- HN / arXiv: 暂不接入

## 输出格式
追加到 candidates.md,每条:
- repo / stars / 最近提交天数 / 短描述
```

### 7.2 `rubrics/triage.md` 结构

```markdown
# Triage Rubric v1

## 任务
对每个 candidate,输出 reject / maybe / deepdive 决策。

## Reject 规则(任一即 reject)
1. README buzzword 密度高且无具体实现
2. 最后有意义提交 > 365 天,且非经典/算法/协议类
3. 明显企业级场景(K8s / RBAC / multi-tenant 关键词密集)
4. 不能 map 到 questions.md 任何一条
5. 语言生态完全不匹配(Java/.NET-only,除非问题特别需要)

## Deepdive 规则(必须全部满足)
1. 映射到具体 question(必填 question_match 字段)
2. 活跃信号:近 30 天有提交 OR(有测试 AND 核心代码 < 5 文件)
3. README 含具体实现描述
4. license 在白名单(MIT/Apache/BSD/MPL),GPL/AGPL/unknown 降为 maybe

## 输出 schema(强制)
```yaml
repo: owner/name
decision: reject | maybe | deepdive
question_match: voice-pipeline/Q3 | null
reasoning: |
  详细说明为什么这样判
evidence:
  - "README 提到 cancellation token"
  - "src/.../interrupt.py 存在"
license_detected: MIT | Apache-2.0 | ... | unknown
concerns:
  - "依赖 Pipecat,可能过重"
```

## 我的修改记录
- 2026-05-20 v1 初版
- (后续 rubric 修改会追加在这里,git log 留更详细历史)
```

### 7.3 `rubrics/deepdive.md` 结构

```markdown
# Deepdive Rubric v1

## 任务
对一个通过 triage 的 repo,生成结构化 entry。

## 必须读取的资源
- README.md (前 4000 字)
- 文件树(深度 3)
- 入口文件 1-2 个(自动猜测或人工指定)
- LICENSE 文件
- pyproject.toml / package.json / go.mod 等

## 必须输出的字段
见 entry 模板(附录 D),所有字段不可省略。

## 关键要求
- 关键文件必须给出 lines 范围,不只是路径
- 每个"它做对了"必须有 evidence(文件 + 行号 或 commit)
- "我打算抄什么"必须具体到函数级
- 若 license 与白名单不符,strictly 标注且不写"可吸收片段"

## 反模式(禁止)
- 不要复述 README,要给出独立判断
- 不要泛泛说"架构清晰",要指出具体设计
- 不要假设我会用,要给出"什么情况不该用"
```

---

## 八、对 v1.3 审阅意见的最终处理(本版)

| v1.3 建议 | 处理 | 落地形式 |
| --- | --- | --- |
| 首期只跑 Q3 | ✅ 完全采纳 | questions.md 仅 Q3 |
| Evidence Pack | ✅ 采纳 | 进 rubrics/deepdive.md 强制输出 |
| License 字段 | ✅ 采纳 | 进 triage 自动检测 + entry schema |
| Stable but valid 项目豁免 | ✅ 采纳 | 进 rubrics/triage.md 例外条款 |
| 三文件采样(README/文件树/配置文件) | ✅ 采纳 | 进 rubrics/deepdive.md "必读资源" |
| Source budget | ✅ 采纳轻量版 | 进 rubrics/scan.md |
| `radar.find_similar` 做 slash command | ✅ 采纳 | Phase 1 末实现(grep 版) |
| Ring 系统(hold/assess/harvest/adopt) | ⚠️ 推迟 | status + decision 两字段 Phase 1 够用,Phase 3 再考虑 |
| L1-L4 used 分级 | ❌ 推迟 Phase 3 | 个人规模分级无统计意义 |
| 30 条 Gold set 回归 | ❌ 推迟 Phase 3 | decisions.md 已起到类似作用,且免标注 |
| Content Trust Level | ⚠️ 简化 | rubric 中标注 "issue/PR 内容不进入 triage 上下文",不做 schema |
| MCP 启动级 allowlist | ✅ 采纳 | scan/triage Skill 只 load 必要 GitHub MCP 工具 |
| Pattern 两级(candidate/confirmed) | ❌ 推迟 Phase 2 末或 3 | 无 pattern 层 |
| 三机制 used 检测 | ⚠️ 简化 | Phase 1 仅 entry 末尾追加(手动);Git hook 推 Phase 3 |
| Orphan 30 天 TTL | ❌ 不做 | 不属于 domain 直接不收 |
| 压缩机制 | ❌ 推迟 | 容量未到上限 |

**总原则**:涉及输出质量与 schema 的建议**全部采纳**,涉及评估机制和过早抽象的建议**全部推迟**。

---

## 九、本版 vs v1.2 vs v2.0 对比

| 维度 | v1.2(平台版) | v2.0(过度收缩) | **v2.1(本版)** |
| --- | --- | --- | --- |
| LLM 接入 | 全管线 | 完全不用 | **全管线** |
| 自动化程度 | 高 | 极低 | **高(但鲜明的人工调参界面)** |
| 人工角色 | 周末 review 输出 | 全人工 | **改 rubric > review > 改 entry** |
| 第一资产 | entries + eval traces | entries | **rubrics(演化曲线)** |
| 系统智能存放 | prompt + 代码 | 无 | **markdown rubric 文件** |
| 可迭代性 | 改 prompt / 代码 | 改 markdown 笔记 | **改 markdown rubric(零代码)** |
| 评估机制 | 复杂(eval/Langfuse) | 完全无 | **隐含在 rubric 演化与 decisions.md 中** |
| Phase 1 工作量 | 30–40 小时 | 8 小时 | **15–20 小时** |
| 失败可见性 | trace + Langfuse | 主观 | **runs/ 目录每次可重现** |
| 退场策略 | 复杂 | 无损降级 markdown | **无损降级 markdown** |

**v2.1 = v1.2 自动化能力 × v2.0 的简洁 × 全新的 Rubric-as-Interface 模式**

---

## 十、Phase 1 落地清单(3 周)

### Week 1:管线骨架 + Rubric 初版(约 8 小时)

- **D1(2h)**:目录骨架 + 三份 rubric 初稿(附录 A/B/C)
- **D2-3(3h)**:写 `radar.scan` Skill(基于 gh CLI)
- **D4-5(2h)**:写 `radar.triage` Skill(接 LiteLLM → Qwen3 14B,加载 rubrics/triage.md)
- **D7 周日(1h)**:首次跑通 scan → triage,人工 review inbox

### Week 2:Deepdive + 首批 entries(约 6 小时)

- **D8-9(3h)**:写 `radar.deepdive` Skill(接 LiteLLM → 远端模型,加载 rubrics/deepdive.md)
- **D10-13(分散 2h)**:跑 3-5 条 deepdive,人工 polish entries,**修 rubric 至少 2 次**
- **D14 周日(1h)**:首次完整 weekly review,写第一份 decisions.md

### Week 3:触达 + 闭环(约 4 小时)

- **D15-17(2h)**:写最简 `/radar` slash command(grep entries/,无需 SQLite)
- **代码实战(0h 增量)**:在 openclaw-voice-bot 写 barge-in 时使用 entry
- **D21 周日(1h)**:Phase 1 自检,看 rubric git log

### Phase 1 总成本

- 时间:15–20 小时
- 代码:约 300 行(三个 Skill)
- LLM token 月成本估算:< $10(triage 本地;deepdive ≤ 5/周)
- Rubric 文件:3 份,Phase 1 结束时各经历 ≥ 3 次修改

---

## 十一、Phase 1 成功标准(双标准,必须全部满足)

| 标准 | 衡量方式 | 为什么这个标准 |
| --- | --- | --- |
| **知识库被实际使用** | refs.md 至少 1 条引用记录 | 证明系统对开发有价值 |
| **Rubric 在演化** | `git log rubrics/` 显示 ≥ 3 次有意义修改 | 证明系统正在被"训练"而非摆设 |

**第二条比第一条更重要。** 若只满足第一条:可能是运气好。若只满足第二条:虽然没用上,但调参机制证明跑通,Phase 2 加方向后大概率能产生引用。两个都不满足:无条件终止,重评。

---

## 十二、失败信号与退场

### 任一信号触发即停止扩张

- 4 周内 rubric 修改次数 = 0(系统没被训练,只是在跑)
- 4 周内 entries 数 = 0(自动化没产出)
- 4 周内 refs.md = 空(没用上)
- inbox 累计未 review > 30 条(执行力崩溃)

### 失败可见性保证

`runs/` 目录每次执行包含完整 trace(rubric 快照 + LLM input/output + 决策)。任何质疑都可以:

```bash
cat ~/.ai-radar/runs/2026-05-20-1430/triage-trace.jsonl
```

看到当时 rubric 是什么、LLM 想了什么、决策为什么这样。这是 v2.0 没有但 v2.1 必须提供的工程保证。

---

## 十三、决策点(本版)

| # | 决策 | 默认 |
| --- | --- | --- |
| D1 | 自动化范围 | 全管线(scan + triage + deepdive) |
| D2 | Triage 模型 | ollama/qwen3:14b 本地 |
| D3 | Deepdive 模型 | claude-sonnet-4.6(via LiteLLM),周限 5 次 |
| D4 | Rubric 形式 | 三份 markdown 文件,git track |
| D5 | 人工干预点 | inbox review + entries polish + rubric edit(三处全要) |
| D6 | 首期方向 | voice-pipeline/Q3 单一问题 |
| D7 | DB | Phase 1 纯 markdown + JSONL,Phase 2 加 SQLite FTS |
| D8 | 雷达目录 | `~/.ai-radar/`,独立于 Vault |

---

## 十四、风险与缓解

| 风险 | 缓解 |
| --- | --- |
| Rubric 改太频繁导致 triage 行为不稳定 | runs/ 目录锁定执行时 rubric 快照,可重现历史决策 |
| 人工 override 后忘了改 rubric | 周日 review 强制项:翻 decisions.md → 提炼 → 改 rubric |
| LLM 输出 schema 漂移 | 每次输出过 JSON Schema validation,失败即丢弃 |
| Token 成本失控 | triage 本地(零成本),deepdive 周限 5 次(~$2/周) |
| 三周后人工懒了不改 rubric | 月度自检 git log,< 3 次修改即降级 Phase 1 → 重评 |
| 上级觉得"还是太复杂" | 见§十五 |

---

## 十五、对上级可能质疑的预答

**质疑 1:为什么不照 v1.3 修改清单完整实施?**

v1.3 的 10 条修改若全做,Phase 1 工作量 40+ 小时,且 6 条无法在 Phase 1 数据量下验证。本版采纳全部"输出质量/schema"类建议,推迟"评估/抽象"类建议到 Phase 3。这不是拒绝,是排程。

**质疑 2:Rubric-as-Interface 是不是发明新概念?**

不是。这就是把 prompt 工程外化为可版本化的 markdown 文件,本质等价于将 system prompt 与代码解耦。区别在于把"判断标准"从隐式 prompt 变为显式资产。Anthropic 的 Skill 机制、Cursor 的 .cursorrules、Claude Code 的 CLAUDE.md 都是同方向实践。

**质疑 3:为什么不上 Langfuse/Gold set?**

Phase 1 数据量(月 < 20 条 deepdive)下,这些机制信号小于噪声。但本版保证了**可观测性的轻量版**:runs/ 目录每次执行的完整 trace 都在,任意时刻可以一次性导入 Langfuse 而无迁移痛点。决策不可逆性:零。

**质疑 4:与现有 v2 Agent Kernel 架构怎么咬合?**

完美咬合。三个 radar Skill 就是 Agent Kernel 上的标准 Skill,通过 LiteLLM 路由模型,trace 直接进 Langfuse(若 Phase 3 启用)。Rubric 文件可以直接放在 Vault 内 git 同步。雷达 = Agent Kernel 的一个垂直应用。

---

## 附录 A:`rubrics/scan.md` 完整初稿

```markdown
# Scan Rubric v1
# 修改日志见 git log

## 当前 question(从 questions.md 派生)
- voice-pipeline/Q3: barge-in 中断状态机
  - 关键词:cancellation, interrupt, barge-in, playback queue, state machine

## 搜索策略
执行 gh search repos,每个 query 取 top 15。

### Query 集
- "voice barge-in interrupt python"
- "tts playback queue cancel streaming"
- "voice agent interrupt state machine"
- "streaming asr partial transcript llm"

### 负面词过滤(命中即丢)
- call-center, ivr, sip, webrtc-sfu
- enterprise, multi-tenant, rbac
- kubernetes-operator

### Source budget(Phase 1)
- gh search: 100%
- 手动种子: 0
- HN / arXiv: 不接入

## 输出格式
追加到 voice-pipeline/candidates.md,每条:
- `[ ] owner/name · ★stars · 提交Nd · "短描述"`

去重:对比 candidates.md 历史,已存在的 repo 跳过。
```

## 附录 B:`rubrics/triage.md` 完整初稿

```markdown
# Triage Rubric v1
# 修改日志见 git log

## 任务
对 candidates.md 中标记 [ ] 的 repo,输出三档决策:reject / maybe / deepdive。
对每条必须输出 reasoning,我会基于 reasoning 决定是否修改本 rubric。

## Reject 规则(任一即 reject)
1. README buzzword 密度高且无具体实现描述
   - 例:"AI-powered next-gen voice infrastructure" 但无代码细节
2. 最后有意义提交 > 365 天
   - 例外:经典/算法/协议类 + 核心代码 < 5 文件 + 有测试 → 改为 maybe
3. 明显企业级
   - 关键词密集:k8s, multi-tenant, rbac, sso, audit-log
4. 不能 map 到 questions.md 任何一条
5. 语言生态完全不匹配(Java/.NET-only)
6. License = GPL-3.0 / AGPL / unknown → 改为 maybe(不直接 reject,但禁止 harvest)

## Deepdive 规则(必须全部满足)
1. 映射到具体 question(必填 question_match)
2. 活跃信号(任一):
   - 近 30 天有提交
   - 有测试 AND 核心代码 < 5 文件 AND 是 canonical 实现
3. README 含具体实现描述,不是纯介绍
4. license 在白名单:MIT / Apache-2.0 / BSD / MPL-2.0 / Unlicense

## Maybe(其他情况)
进 inbox/,等周末人工 review。

## 必须读取的资源
- repo 元数据(stars, pushed_at, language, license)
- README.md 前 3000 字
- 文件树深度 2
- LICENSE 文件(若存在)

## 输出 schema(YAML,强制)
```yaml
repo: owner/name
decision: reject | maybe | deepdive
question_match: voice-pipeline/Q3 | null
license_detected: MIT | Apache-2.0 | GPL-3.0 | unknown
reasoning: |
  详细说明,> 100 字,让我能判断是否要改 rubric
evidence:
  - "README L42 提到 cancellation token"
  - "tests/ 目录存在"
concerns:
  - "依赖 Pipecat,可能引入额外复杂度"
```

## 反模式
- 不允许只输出决策不输出 reasoning
- 不允许 reasoning 是 "looks good" 等无信息词
- 不确定时输出 maybe,不要硬猜

## 我的修改记录
- 2026-05-20 v1 初版
- (后续修改追加于此)
```

## 附录 C:`rubrics/deepdive.md` 完整初稿

```markdown
# Deepdive Rubric v1
# 修改日志见 git log

## 任务
对通过 triage 的一个 repo,生成结构化 entry(markdown + frontmatter)。

## 必须读取的资源(最小集)
- README.md 全文(若 > 8000 字,取前 8000)
- 文件树深度 3
- 入口文件 1-2 个(根据 README 自动猜测或人工指定)
- LICENSE 文件
- pyproject.toml / package.json / go.mod / Cargo.toml(任一存在的)

## 输出 schema
见附录 D Entry 模板。所有字段不可省略。

## 关键要求
1. **关键文件必须给出 lines 范围**,不只是路径
2. 每个"它做对了"必须有 evidence(具体到文件:行号或 commit hash)
3. "我打算抄什么"必须具体到函数级,不允许写"整个 pipeline"
4. 若 license 不在白名单,strictly 标注且**不写"可吸收片段"**,只写"可借鉴设计"
5. 必须填 question_match,无对应 question 时报错退出

## 必须包含的章节(顺序固定)
- 一句话定位
- 它解决了哪个具体问题(引用 questions.md 中的 question)
- 关键文件(含 lines)
- 它做对了什么(每条带 evidence)
- 它不适合我的地方
- 我打算抄走什么(若 license 允许)/ 可借鉴的设计(若 license 受限)
- License 与合规备注
- 下一步(只允许 1 条,30 分钟内可执行)

## 反模式
- 不允许复述 README
- 不允许泛泛说"架构清晰",要给出具体设计点
- 不允许假设我会用,要给出"什么情况不该用"
- 不允许"下一步"超过 1 条

## 我的修改记录
- 2026-05-20 v1 初版
```

## 附录 D:Entry 模板(deepdive 输出格式)

```markdown
---
type: repo
repo: owner/name
domain: voice-pipeline
question_match: voice-pipeline/Q3
status: active
decision: deepdive  # 来自 triage,可被人工改为 harvest/adopt/watch
discovered: 2026-05-20
last_reviewed: 2026-05-20

license:
  detected: MIT
  in_whitelist: true
  harvest_allowed: true

signals:
  stars: 3200
  last_commit_age_days: 3
  active_contributors: 6
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
- MIT,可自由 harvest
- 需保留 copyright header

## 下一步(只允许 1 条)
- [ ] 复制 buffer.py:60-95 进 openclaw-voice-bot 试用

---
## 已用于
(此区域由人工在使用后追加,不由 LLM 生成)
```

---

## 十六、最终一句话

> **v2.1 = 自动化把脏活全干了,人工把心思全花在调 rubric 上。Phase 1 跑完时,真正长期值钱的不是那 5 个 entries,而是经过 3 次以上修改的三份 rubric——这才是个人技术雷达的"权重"。**

---

*文档结束。v2.1 / 2026-05-20。下一版本仅在 Phase 1 结束并产出 rubric 演化数据后生成。*
