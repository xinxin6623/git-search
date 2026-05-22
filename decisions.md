# decisions.md — 人工 override 累计记录

每次 Review inbox 时，对不同意 LLM 决策的条目记录在此。
积累足够 override → 月度 review 时提炼进 `rubrics/*.md`。

## 格式
```
### YYYY-MM-DD · owner/repo
- **LLM 决策**: reject | maybe | deepdive
- **我的决策**: reject | maybe | deepdive
- **理由**: 一段话，说清楚为什么 LLM 错了
- **是否已改 rubric**: yes（指向 commit）/ no（待月度提炼）
```

---

<!-- override 记录从此处往下追加 -->
