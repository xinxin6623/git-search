#!/usr/bin/env bash
# radar.scan — 按 rubrics/scan.md 中的 query 集搜 GitHub 仓库
# 用法: scan.sh <direction>
# 例:   scan.sh voice-pipeline
#
# 依赖: gh (已登录), jq
# 不做的事: 不调 LLM；不评判；仅去重 + 负面词过滤后追加 candidates.md

set -euo pipefail

# ============== 路径解析 ==============
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIRECTION="${1:-}"

if [[ -z "$DIRECTION" ]]; then
  echo "用法: scan.sh <direction>" >&2
  echo "  例: scan.sh voice-pipeline" >&2
  exit 2
fi

RUBRIC_FILE="$REPO_ROOT/rubrics/scan.md"
CANDIDATES_FILE="$REPO_ROOT/$DIRECTION/candidates.md"
TIMESTAMP="$(date +%Y-%m-%d-%H%M)"
RUN_DIR="$REPO_ROOT/runs/$TIMESTAMP-scan"
RESULTS_JSON="$RUN_DIR/scan-results.json"
RUBRIC_SNAPSHOT="$RUN_DIR/rubric-snapshot.md"
SUMMARY="$RUN_DIR/summary.md"

# ============== 前置检查 ==============
[[ -f "$RUBRIC_FILE" ]]     || { echo "缺 rubric: $RUBRIC_FILE" >&2; exit 1; }
[[ -f "$CANDIDATES_FILE" ]] || { echo "缺 candidates.md: $CANDIDATES_FILE" >&2; exit 1; }
command -v gh >/dev/null    || { echo "需要 gh CLI" >&2; exit 1; }
command -v jq >/dev/null    || { echo "需要 jq" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "gh 未登录，运行: gh auth login" >&2; exit 1; }

mkdir -p "$RUN_DIR"
cp "$RUBRIC_FILE" "$RUBRIC_SNAPSHOT"

# ============== 从 rubric 解析 query 与负面词 ==============
# Query 集: ### Query 集 章节下，反引号包裹的行
# 负面词:   ### 负面词过滤 章节下，- 开头的逗号分隔列表

parse_section() {
  # $1 = 章节标题（不含 ###）; stdout: 该章节到下一个 ### 之间的内容
  awk -v title="$1" '
    /^### / { in_sec = ($0 ~ title) ? 1 : 0; next }
    in_sec { print }
  ' "$RUBRIC_FILE"
}

QUERIES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && QUERIES+=("$line")
done < <(
  parse_section "Query 集" \
    | grep -oE '`[^`]+`' \
    | sed 's/^`//; s/`$//'
)

NEG_TERMS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && NEG_TERMS+=("$line")
done < <(
  parse_section "负面词过滤" \
    | grep -E '^- ' \
    | sed 's/^- //' \
    | tr ',' '\n' \
    | sed 's/^ *//; s/ *$//' \
    | grep -v '^$'
)

if [[ ${#QUERIES[@]} -eq 0 ]]; then
  echo "未从 $RUBRIC_FILE 解析出 query（检查 '### Query 集' 章节格式）" >&2
  exit 1
fi

echo "→ rubric: $RUBRIC_FILE"
echo "→ queries: ${#QUERIES[@]} 条"
echo "→ neg terms: ${#NEG_TERMS[@]} 个"
echo "→ run dir: $RUN_DIR"

# ============== 已有 repo 集合（用于去重） ==============
EXISTING="$(grep -oE '[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+' "$CANDIDATES_FILE" | sort -u || true)"

# ============== 执行搜索 ==============
echo "[]" > "$RESULTS_JSON"
PER_QUERY_LIMIT=15

for q in "${QUERIES[@]}"; do
  echo "  query: $q"
  if hits="$(gh search repos "$q" --limit "$PER_QUERY_LIMIT" \
       --json fullName,stargazersCount,pushedAt,description,license 2>/dev/null)"; then
    # 给每条加 query 字段，合并入 RESULTS_JSON
    jq --argjson new "$hits" --arg q "$q" '
      . + ($new | map(. + {query: $q}))
    ' "$RESULTS_JSON" > "$RESULTS_JSON.tmp" && mv "$RESULTS_JSON.tmp" "$RESULTS_JSON"
  else
    echo "    ! 查询失败，跳过" >&2
  fi
done

TOTAL_RAW="$(jq 'length' "$RESULTS_JSON")"

# ============== 过滤：负面词 + 已存在去重 ==============
# 负面词正则（不区分大小写）
NEG_REGEX=""
if [[ ${#NEG_TERMS[@]} -gt 0 ]]; then
  NEG_REGEX="$(printf '%s|' "${NEG_TERMS[@]}" | sed 's/|$//')"
fi

# 追加到 candidates.md 的新行
APPENDED=0
SKIP_NEG=0
SKIP_DUP=0
TODAY="$(date +%Y-%m-%d)"

{
  echo ""
  echo "<!-- scan $TIMESTAMP -->"

  jq -r '.[] | [.fullName, .stargazersCount, .pushedAt, (.description // ""), (.license.key // "unknown")] | @tsv' "$RESULTS_JSON" \
    | sort -u \
    | while IFS=$'\t' read -r full stars pushed desc license_key; do
        # 去重
        if echo "$EXISTING" | grep -qx "$full"; then
          SKIP_DUP=$((SKIP_DUP+1))
          continue
        fi
        # 负面词
        if [[ -n "$NEG_REGEX" ]]; then
          haystack="$(printf '%s %s' "$full" "$desc" | tr '[:upper:]' '[:lower:]')"
          if echo "$haystack" | grep -qE "$NEG_REGEX"; then
            SKIP_NEG=$((SKIP_NEG+1))
            continue
          fi
        fi

        # 提交天数: pushedAt → 距今天数
        if [[ -n "$pushed" && "$pushed" != "null" ]]; then
          # macOS date
          pushed_epoch="$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$pushed" +%s 2>/dev/null || echo "")"
          if [[ -n "$pushed_epoch" ]]; then
            now_epoch="$(date +%s)"
            days=$(( (now_epoch - pushed_epoch) / 86400 ))
          else
            days="?"
          fi
        else
          days="?"
        fi

        # 短描述: 截断到 80 字符
        short_desc="$(printf '%s' "$desc" | tr '\n\r' '  ' | cut -c1-80)"

        printf -- '- [ ] %s · ★%s · 提交%sd · "%s"\n' \
          "$full" "$stars" "$days" "$short_desc"
        APPENDED=$((APPENDED+1))
        # 注意: while 在子 shell，APPENDED 在外面不可见，下面用 wc 重新算
      done
} >> "$CANDIDATES_FILE"

# 重新精确算追加数（子 shell 变量问题）
APPENDED="$(grep -c "^- \[ \] " "$CANDIDATES_FILE" | head -1)"
TOTAL_NEW="$(awk '/<!-- scan '"$TIMESTAMP"' -->/{flag=1; next} flag && /^- \[ \] /{c++} END{print c+0}' "$CANDIDATES_FILE")"

# ============== Summary ==============
{
  echo "# scan summary — $TIMESTAMP"
  echo ""
  echo "- direction: $DIRECTION"
  echo "- rubric snapshot: rubric-snapshot.md"
  echo "- queries 数: ${#QUERIES[@]}"
  echo "- 原始命中（合并所有 query）: $TOTAL_RAW"
  echo "- 追加到 candidates.md: $TOTAL_NEW"
  echo ""
  echo "## queries"
  for q in "${QUERIES[@]}"; do echo "- \`$q\`"; done
  echo ""
  echo "## 负面词"
  for n in "${NEG_TERMS[@]}"; do echo "- $n"; done
} > "$SUMMARY"

echo ""
echo "✓ done"
echo "  原始命中: $TOTAL_RAW"
echo "  追加 candidates: $TOTAL_NEW"
echo "  trace: $RUN_DIR"
