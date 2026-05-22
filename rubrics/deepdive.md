# Deepdive Rubric v1
# 修改日志见 git log

## 任务
对通过 triage 的一个 repo，生成结构化 entry（markdown + frontmatter）。

## 必须读取的资源（最小集）
- README.md 全文（若 > 8000 字，取前 8000）
- 文件树深度 3
- 入口文件 1-2 个（根据 README 自动猜测或人工指定）
- LICENSE 文件
- `pyproject.toml` / `package.json` / `go.mod` / `Cargo.toml`（任一存在的）

## 输出 schema
见 `voice-pipeline/entries/_TEMPLATE.md`（附录 D）。所有字段不可省略。

## 关键要求
1. **关键文件必须给出 lines 范围**，不只是路径
2. 每个"它做对了"必须有 evidence（具体到 文件:行号 或 commit hash）
3. "我打算抄什么"必须具体到函数级，不允许写"整个 pipeline"
4. 若 license 不在白名单，strictly 标注且**不写"可吸收片段"**，只写"可借鉴设计"
5. 必须填 `question_match`，无对应 question 时报错退出

## 必须包含的章节（顺序固定）
1. 一句话定位
2. 它解决了哪个具体问题（引用 questions.md 中的 question）
3. 关键文件（含 lines）
4. 它做对了什么（每条带 evidence）
5. 它不适合我的地方
6. 我打算抄走什么（若 license 允许）/ 可借鉴的设计（若 license 受限）
7. License 与合规备注
8. 下一步（只允许 1 条，30 分钟内可执行）

## 反模式
- 不允许复述 README
- 不允许泛泛说"架构清晰"，要给出具体设计点
- 不允许假设我会用，要给出"什么情况不该用"
- 不允许"下一步"超过 1 条

## 我的修改记录
- 2026-05-20 v1 初版
