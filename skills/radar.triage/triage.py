#!/usr/bin/env python3
"""radar.triage — 对 candidates.md 中未处理的 repo，按 rubrics/triage.md 调本地 LLM 出决策。

用法:
    triage.py <direction> [--since YYYY-MM-DD] [--limit N] [--dry-run]

例:
    triage.py voice-pipeline
    triage.py voice-pipeline --since 2026-05-20
    triage.py voice-pipeline --limit 3 --dry-run

依赖:
    - litellm (pip install litellm)
    - pyyaml, jsonschema
    - gh CLI (已登录)
    - 本地模型: ollama 服务运行 + 已 pull 对应模型
    - 云端模型: 设置对应 API key 环境变量 (见 config.yaml)

配置:
    所有模型/温度/超时/fallback 由根目录 config.yaml 控制。
    切模型 = 改 config.yaml 的 triage.active，不动本文件。

设计原则:
    - 所有 LLM 输出必须含 reasoning（> 100 字），缺字段即丢弃
    - 失败即停，不静默降级
    - 完整 trace 写 runs/{ts}-triage/triage-trace.jsonl
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

# 让 _lib 可 import
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib.config import StageConfig, load_stage_config  # noqa: E402
from _lib.llm import LLMCallError, LLMMetrics, call_llm  # noqa: E402

# litellm 仅在真正调 LLM 时导入；dry-run / 单纯校验输出不需要它


# ============== 路径与常量 ==============

REPO_ROOT = Path(__file__).resolve().parents[2]
README_MAX_CHARS = 3000
FILE_TREE_DEPTH = 2

# triage 输出强 schema
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "repo",
        "decision",
        "question_match",
        "license_detected",
        "reasoning",
        "evidence",
    ],
    "properties": {
        "repo": {"type": "string", "pattern": r"^[^/]+/[^/]+$"},
        "decision": {"enum": ["reject", "maybe", "deepdive"]},
        "question_match": {"type": ["string", "null"]},
        "license_detected": {"type": "string"},
        "reasoning": {"type": "string", "minLength": 100},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "concerns": {"type": "array", "items": {"type": "string"}},
    },
    "additionalProperties": True,
}


# ============== 工具 ==============


def log(msg: str) -> None:
    print(msg, flush=True)


def err(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def run_gh(args: list[str]) -> str | None:
    """跑 gh，失败返回 None。"""
    try:
        out = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if out.returncode != 0:
            return None
        return out.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


# ============== 候选解析 ==============

CANDIDATE_LINE_RE = re.compile(
    r"^- \[ \] ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\b"
)


@dataclass
class Candidate:
    repo: str
    raw_line: str  # 用于后续 mark [x]


def parse_candidates(path: Path, since: dt.date | None) -> list[Candidate]:
    """从 candidates.md 取未处理候选。

    since: 若设置，只取该日期之后追加的（依赖 <!-- scan YYYY-MM-DD-HHMM --> 标记）。
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    cutoff = since
    in_window = since is None  # 无 since 时全要
    in_fence = False

    out: list[Candidate] = []
    for line in lines:
        # 跳过 ``` fenced block 内的示例
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        m_scan = re.match(r"<!-- scan (\d{4}-\d{2}-\d{2})", line)
        if m_scan:
            scan_date = dt.date.fromisoformat(m_scan.group(1))
            in_window = (cutoff is None) or (scan_date >= cutoff)
            continue

        if not in_window:
            continue

        m = CANDIDATE_LINE_RE.match(line)
        if m:
            out.append(Candidate(repo=m.group(1), raw_line=line))

    # 去重保序
    seen: set[str] = set()
    uniq: list[Candidate] = []
    for c in out:
        if c.repo in seen:
            continue
        seen.add(c.repo)
        uniq.append(c)
    return uniq


# ============== Fetch repo 资源 ==============


@dataclass
class RepoSnapshot:
    repo: str
    metadata: dict[str, Any]
    readme: str
    file_tree: str
    license_text: str | None


def fetch_repo(repo: str) -> RepoSnapshot | None:
    """拉取 triage 必需的最小集。任一关键资源失败返回 None。"""
    # 元数据
    raw = run_gh(
        [
            "repo",
            "view",
            repo,
            "--json",
            "name,owner,description,stargazerCount,pushedAt,primaryLanguage,licenseInfo,url",
        ]
    )
    if not raw:
        return None
    meta = json.loads(raw)

    # README（前 N 字）
    readme_raw = run_gh(["api", f"repos/{repo}/readme", "-H", "Accept: application/vnd.github.raw"])
    readme = (readme_raw or "")[:README_MAX_CHARS]

    # 文件树深度 2（用 default branch tree）
    tree_raw = run_gh(["api", f"repos/{repo}/git/trees/HEAD?recursive=1"])
    file_tree = ""
    if tree_raw:
        try:
            tree = json.loads(tree_raw)
            paths = [
                t["path"]
                for t in tree.get("tree", [])
                if t["path"].count("/") < FILE_TREE_DEPTH
            ][:200]
            file_tree = "\n".join(sorted(paths))
        except (json.JSONDecodeError, KeyError):
            file_tree = ""

    # LICENSE（meta 里有 licenseInfo 就够；额外拉文本会浪费 API quota，跳过）
    license_text = None

    return RepoSnapshot(
        repo=repo,
        metadata=meta,
        readme=readme,
        file_tree=file_tree,
        license_text=license_text,
    )


# ============== LLM 调用 ==============


SYSTEM_PROMPT_TEMPLATE = """你是技术雷达的 triage agent。严格按以下 rubric 工作。

==== Rubric (rubrics/triage.md) ====
{rubric}

==== 当前 questions (voice-pipeline/questions.md) ====
{questions}

==== 输出要求 ====
仅输出一个 YAML 文档（不要 ``` 围栏，不要前后多余文字），字段严格匹配 schema:

repo: owner/name
decision: reject | maybe | deepdive
question_match: voice-pipeline/Q3 | null
license_detected: <license key 或 unknown>
reasoning: |
  > 100 字，说明判断依据。
evidence:
  - "具体出处，如 README 提到 X / 存在 tests/ 目录"
concerns:
  - "可选，限制或风险"
"""


USER_PROMPT_TEMPLATE = """== Candidate: {repo} ==

## 元数据
{metadata}

## README (前 {readme_len} 字)
{readme}

## 文件树（深度 {depth}）
{file_tree}
"""


def build_messages(
    rubric: str, questions: str, snap: RepoSnapshot
) -> list[dict[str, str]]:
    meta_pretty = json.dumps(snap.metadata, ensure_ascii=False, indent=2)
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT_TEMPLATE.format(
                rubric=rubric, questions=questions
            ),
        },
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                repo=snap.repo,
                metadata=meta_pretty,
                readme_len=README_MAX_CHARS,
                readme=snap.readme or "(empty)",
                depth=FILE_TREE_DEPTH,
                file_tree=snap.file_tree or "(empty)",
            ),
        },
    ]


# call_llm 来自 skills/_lib/llm.py，返回 (content, LLMMetrics)


# ============== 输出校验 ==============


def parse_and_validate(raw: str) -> dict[str, Any]:
    """从 LLM raw 输出抽 YAML 并校验。失败抛 ValueError。"""
    # 容错：去掉可能的 ``` 围栏
    cleaned = re.sub(r"^```(?:yaml|yml)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```$", "", cleaned)

    try:
        obj = yaml.safe_load(cleaned)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 解析失败: {e}")

    if not isinstance(obj, dict):
        raise ValueError(f"输出不是 dict，是 {type(obj).__name__}")

    validator = Draft202012Validator(OUTPUT_SCHEMA)
    errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise ValueError(f"schema 校验失败: {msg}")

    return obj


# ============== 落盘 ==============


def write_inbox_entry(
    inbox_dir: Path, today: dt.date, decision_obj: dict[str, Any]
) -> Path:
    owner, name = decision_obj["repo"].split("/", 1)
    fname = f"{today.isoformat()}-{owner}-{name}.md"
    path = inbox_dir / fname

    body = [
        "---",
        yaml.safe_dump(
            {
                "repo": decision_obj["repo"],
                "decision": decision_obj["decision"],
                "question_match": decision_obj.get("question_match"),
                "license_detected": decision_obj.get("license_detected"),
                "triaged_at": today.isoformat(),
            },
            allow_unicode=True,
            sort_keys=False,
        ).strip(),
        "---",
        "",
        f"# {decision_obj['repo']} → **{decision_obj['decision']}**",
        "",
        "## Reasoning",
        decision_obj["reasoning"].strip(),
        "",
        "## Evidence",
    ]
    for e in decision_obj.get("evidence", []):
        body.append(f"- {e}")
    if decision_obj.get("concerns"):
        body.append("")
        body.append("## Concerns")
        for c in decision_obj["concerns"]:
            body.append(f"- {c}")

    body.append("")
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def mark_candidate_done(candidates_path: Path, repo: str) -> None:
    text = candidates_path.read_text(encoding="utf-8")
    new = re.sub(
        rf"^- \[ \] ({re.escape(repo)}\b.*)$",
        r"- [x] \1",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new != text:
        candidates_path.write_text(new, encoding="utf-8")


# ============== 主流程 ==============


def main() -> int:
    ap = argparse.ArgumentParser(description="radar.triage")
    ap.add_argument("direction", help="e.g. voice-pipeline")
    ap.add_argument("--since", help="YYYY-MM-DD, 只处理该日期之后追加的候选")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 条（0 = 全部）")
    ap.add_argument(
        "--profile",
        help="覆盖 config.yaml 中 triage.active（用于临时切模型）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只 fetch + 构造 prompt，不调 LLM")
    args = ap.parse_args()

    # 加载阶段配置（dry-run 也加载，便于验证）
    try:
        cfg = load_stage_config("triage", override_profile=args.profile)
    except (FileNotFoundError, KeyError, ValueError, EnvironmentError) as e:
        err(f"配置错误: {e}")
        return 1

    direction_dir = REPO_ROOT / args.direction
    candidates_path = direction_dir / "candidates.md"
    inbox_dir = direction_dir / "inbox"
    questions_path = direction_dir / "questions.md"
    rubric_path = REPO_ROOT / "rubrics" / "triage.md"

    for p in (candidates_path, inbox_dir, questions_path, rubric_path):
        if not p.exists():
            err(f"缺路径: {p}")
            return 1

    if not shutil.which("gh"):
        err("需要 gh CLI")
        return 1

    rubric = rubric_path.read_text(encoding="utf-8")
    questions = questions_path.read_text(encoding="utf-8")

    since: dt.date | None = None
    if args.since:
        since = dt.date.fromisoformat(args.since)

    candidates = parse_candidates(candidates_path, since)
    if args.limit:
        candidates = candidates[: args.limit]

    if not candidates:
        log("没有未处理候选。退出。")
        return 0

    ts = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    run_dir = REPO_ROOT / "runs" / f"{ts}-triage"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rubric-snapshot.md").write_text(rubric, encoding="utf-8")
    trace_path = run_dir / "triage-trace.jsonl"
    summary_path = run_dir / "summary.md"

    log(f"→ rubric: {rubric_path}")
    log(f"→ candidates: {len(candidates)} 条")
    log(f"→ profile: {cfg.profile_name}  ({cfg.provider})")
    log(f"→ model:   {cfg.model}")
    if cfg.api_base:
        log(f"→ api_base: {cfg.api_base}")
    log(f"→ run dir: {run_dir}")
    if args.dry_run:
        log("→ DRY RUN（不调 LLM）")

    counts = {"reject": 0, "maybe": 0, "deepdive": 0, "error": 0}
    metrics_log: list[LLMMetrics] = []  # 用于 summary 聚合
    today = dt.date.today()

    with trace_path.open("w", encoding="utf-8") as trace_f:
        for i, c in enumerate(candidates, 1):
            log(f"\n[{i}/{len(candidates)}] {c.repo}")
            snap = fetch_repo(c.repo)
            if not snap:
                err(f"  ! fetch 失败，跳过")
                counts["error"] += 1
                trace_f.write(json.dumps(
                    {"repo": c.repo, "stage": "fetch", "error": "gh failed"},
                    ensure_ascii=False,
                ) + "\n")
                continue

            messages = build_messages(rubric, questions, snap)

            if args.dry_run:
                trace_f.write(json.dumps(
                    {"repo": c.repo, "stage": "dry-run", "messages": messages},
                    ensure_ascii=False,
                ) + "\n")
                continue

            try:
                raw, metrics = call_llm(messages, cfg)
            except LLMCallError as e:
                err(f"  ! LLM 调用失败 ({e.metrics.latency_s}s): {e}")
                counts["error"] += 1
                metrics_log.append(e.metrics)
                trace_f.write(json.dumps(
                    {"repo": c.repo, "stage": "llm",
                     "metrics": e.metrics.to_dict()},
                    ensure_ascii=False,
                ) + "\n")
                # 设计原则：失败即停
                err("失败即停。修复后重跑。")
                break

            metrics_log.append(metrics)
            log(f"  · llm {metrics.latency_s}s  "
                f"in={metrics.prompt_tokens} out={metrics.completion_tokens}"
                + (f" think={metrics.reasoning_chars}ch" if metrics.reasoning_chars else ""))

            try:
                obj = parse_and_validate(raw)
            except ValueError as e:
                err(f"  ! 输出校验失败: {e}")
                counts["error"] += 1
                trace_f.write(json.dumps(
                    {"repo": c.repo, "stage": "validate", "error": str(e),
                     "metrics": metrics.to_dict(), "raw": raw},
                    ensure_ascii=False,
                ) + "\n")
                continue

            # 强制把 LLM 报的 repo 改回真值（防止它幻觉重命名）
            obj["repo"] = c.repo

            inbox_path = write_inbox_entry(inbox_dir, today, obj)
            mark_candidate_done(candidates_path, c.repo)
            counts[obj["decision"]] += 1
            log(f"  → {obj['decision']}  ({inbox_path.name})")

            trace_f.write(json.dumps(
                {
                    "repo": c.repo,
                    "stage": "done",
                    "decision": obj["decision"],
                    "metrics": metrics.to_dict(),
                    "raw": raw,
                    "parsed": obj,
                },
                ensure_ascii=False,
            ) + "\n")

    # ============== Summary: 决策分布 + LLM 用量聚合 ==============
    ok = [m for m in metrics_log if m.error is None]
    lat = [m.latency_s for m in ok]
    pt = [m.prompt_tokens or 0 for m in ok]
    ct = [m.completion_tokens or 0 for m in ok]
    tt = [m.total_tokens or 0 for m in ok]

    def stat(xs: list[float]) -> str:
        if not xs:
            return "n/a"
        return f"sum={sum(xs):.1f} avg={sum(xs)/len(xs):.1f} min={min(xs):.1f} max={max(xs):.1f}"

    summary = [
        f"# triage summary — {ts}",
        "",
        f"- direction: {args.direction}",
        f"- profile: {cfg.profile_name} ({cfg.provider})",
        f"- model: {cfg.model}",
        f"- rubric snapshot: rubric-snapshot.md",
        f"- 候选总数: {len(candidates)}",
        "",
        "## 决策分布",
        f"- reject:   {counts['reject']}",
        f"- maybe:    {counts['maybe']}",
        f"- deepdive: {counts['deepdive']}",
        f"- error:    {counts['error']}",
        "",
        f"## LLM 用量（成功 {len(ok)} 次）",
        f"- 时延 (秒):       {stat(lat)}",
        f"- prompt_tokens:   {stat(pt)}",
        f"- completion_tokens: {stat(ct)}",
        f"- total_tokens:    {stat(tt)}",
    ]
    summary_path.write_text("\n".join(summary), encoding="utf-8")

    log("\n✓ done")
    log(f"  reject={counts['reject']} maybe={counts['maybe']} "
        f"deepdive={counts['deepdive']} error={counts['error']}")
    if ok:
        log(f"  llm: 共 {len(ok)} 次, "
            f"总耗时 {sum(lat):.1f}s, 总 token {sum(tt)} "
            f"(in={sum(pt)} out={sum(ct)})")
    log(f"  trace: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
