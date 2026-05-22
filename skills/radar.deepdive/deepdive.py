#!/usr/bin/env python3
"""radar.deepdive — 对指定 repo 调远端强模型生成结构化 entry。

用法:
    deepdive.py owner/repo [owner/repo ...] [--profile NAME] [--dry-run]
    deepdive.py --from-inbox <direction>   # 读 inbox 中 decision=deepdive 的条目

例:
    deepdive.py cyijun/hachimi
    deepdive.py --from-inbox voice-pipeline --limit 2
    deepdive.py owner/repo --profile siliconflow-qwen3-omni-30b-thinking

依赖:
    - litellm + .env (MOONSHOT_API_KEY 或所选 profile 对应 key)
    - gh CLI (已登录)
    - pyyaml, jsonschema

配置:
    根目录 config.yaml 的 deepdive 段决定模型 / 温度 / 超时 / fallback / 周配额。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib.config import StageConfig, load_stage_config  # noqa: E402
from _lib.llm import LLMCallError, LLMMetrics, call_llm  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[2]
README_MAX_CHARS = 8000
FILE_TREE_DEPTH = 3
FILE_TREE_MAX_PATHS = 400

LICENSE_WHITELIST = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause",
                     "mpl-2.0", "unlicense", "isc"}

# Entry frontmatter schema（强制最小集）
FRONTMATTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "repo", "domain", "question_match", "status",
        "decision", "discovered", "last_reviewed", "license", "signals",
    ],
    "properties": {
        "repo": {"type": "string", "pattern": r"^[^/]+/[^/]+$"},
        "domain": {"type": "string"},
        "question_match": {"type": "string"},
        "status": {"type": "string"},
        "decision": {"type": "string"},
        "discovered": {"type": "string"},
        "last_reviewed": {"type": "string"},
        "license": {"type": "object"},
        "signals": {"type": "object"},
    },
    "additionalProperties": True,
}

REQUIRED_SECTIONS = [
    "一句话定位",
    "它解决了哪个具体问题",
    "关键文件",
    "它做对了什么",
    "它不适合我的地方",
    "License 与合规",
    "下一步",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def err(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def run_gh(args: list[str], timeout: int = 30) -> str | None:
    try:
        out = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, timeout=timeout, check=False,
        )
        return out.stdout if out.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


# ============== 拉取 repo 资源 ==============


@dataclass
class RepoBundle:
    repo: str
    metadata: dict[str, Any]
    readme: str
    file_tree: str
    license_key: str
    license_text: str | None
    manifest_name: str | None      # pyproject.toml / package.json / go.mod / Cargo.toml
    manifest_content: str | None
    entry_files: list[tuple[str, str]]   # (path, content) 1-2 个


MANIFEST_FILES = ["pyproject.toml", "package.json", "go.mod", "Cargo.toml"]
ENTRY_HINTS = [
    "src/main.py", "main.py", "app.py", "src/index.ts", "src/index.js",
    "index.ts", "index.js", "cmd/main.go", "src/lib.rs", "src/main.rs",
]


def fetch_file(repo: str, path: str) -> str | None:
    raw = run_gh(["api", f"repos/{repo}/contents/{path}",
                  "-H", "Accept: application/vnd.github.raw"])
    return raw


def fetch_bundle(repo: str, entry_override: str | None = None) -> RepoBundle | None:
    meta_raw = run_gh([
        "repo", "view", repo, "--json",
        "name,owner,description,stargazerCount,pushedAt,primaryLanguage,licenseInfo,url",
    ])
    if not meta_raw:
        return None
    meta = json.loads(meta_raw)
    license_key = ((meta.get("licenseInfo") or {}).get("key") or "unknown").lower()

    readme_raw = run_gh(["api", f"repos/{repo}/readme",
                         "-H", "Accept: application/vnd.github.raw"])
    readme = (readme_raw or "")[:README_MAX_CHARS]

    # 文件树深度 3
    tree_raw = run_gh(["api", f"repos/{repo}/git/trees/HEAD?recursive=1"])
    file_tree = ""
    all_paths: list[str] = []
    if tree_raw:
        try:
            tree = json.loads(tree_raw)
            all_paths = [t["path"] for t in tree.get("tree", [])]
            shallow = [p for p in all_paths if p.count("/") < FILE_TREE_DEPTH]
            file_tree = "\n".join(sorted(shallow)[:FILE_TREE_MAX_PATHS])
        except (json.JSONDecodeError, KeyError):
            pass

    # 入口 manifest
    manifest_name = None
    manifest_content = None
    for cand in MANIFEST_FILES:
        if cand in all_paths:
            c = fetch_file(repo, cand)
            if c:
                manifest_name = cand
                manifest_content = c[:3000]
                break

    # 入口文件 1-2 个
    entry_files: list[tuple[str, str]] = []
    candidates: list[str] = []
    if entry_override:
        candidates = [entry_override]
    else:
        for h in ENTRY_HINTS:
            if h in all_paths:
                candidates.append(h)
            if len(candidates) >= 2:
                break
    for p in candidates[:2]:
        c = fetch_file(repo, p)
        if c:
            entry_files.append((p, c[:4000]))

    # LICENSE 文本（若 licenseInfo.key 为 unknown 才费力拉）
    license_text = None
    if license_key == "unknown":
        license_text = fetch_file(repo, "LICENSE") or fetch_file(repo, "LICENSE.md")
        if license_text:
            license_text = license_text[:2000]

    return RepoBundle(
        repo=repo, metadata=meta, readme=readme, file_tree=file_tree,
        license_key=license_key, license_text=license_text,
        manifest_name=manifest_name, manifest_content=manifest_content,
        entry_files=entry_files,
    )


# ============== Prompt 组装 ==============


SYSTEM_PROMPT_TEMPLATE = """你是技术雷达的 deepdive agent。按以下 rubric 与 entry 模板，对一个 repo 生成结构化 entry。

==== Rubric (rubrics/deepdive.md) ====
{rubric}

==== Questions ====
{questions}

==== Entry 模板 (附录 D) ====
{template}

==== 输出格式 ====
直接输出完整 markdown entry（开头是 YAML frontmatter `---`，无 ``` 围栏，无多余前后文字）。
严格遵循模板章节顺序与名称。每个章节都要写实质内容。
license 不在白名单 ({whitelist}) 时，"我打算抄走什么" 章节改为 "可借鉴的设计"。

==== 输出长度约束 ====
整个 entry（含 frontmatter）控制在 1500 字以内。每章节简短具体：
- "一句话定位"：1 行
- "它做对了什么"：2-4 条 bullet
- "它不适合我的地方"：2-3 条 bullet
- "下一步"：严格 1 条
不要展开论述，不要客套，不要重复 README。
"""


USER_PROMPT_TEMPLATE = """== Target: {repo} ==

## GitHub 元数据
{metadata}

## License (gh API): {license_key}
{license_text_block}

## README (前 {readme_len} 字)
{readme}

## 文件树（深度 {depth}, 截断 {max_paths} 条）
{file_tree}

## Manifest ({manifest_name})
{manifest_content}

## 入口文件采样
{entry_files_block}
"""


def build_messages(rubric: str, questions: str, template: str,
                   bundle: RepoBundle) -> list[dict[str, str]]:
    license_block = (bundle.license_text or "(licenseInfo 已识别为 "
                                            f"{bundle.license_key}，不再拉文本)")
    entry_block = "\n\n".join(
        f"### {p}\n```\n{c}\n```" for p, c in bundle.entry_files
    ) or "(无可用入口文件)"
    manifest_block = bundle.manifest_content or "(无)"

    sys_msg = SYSTEM_PROMPT_TEMPLATE.format(
        rubric=rubric, questions=questions, template=template,
        whitelist=", ".join(sorted(LICENSE_WHITELIST)),
    )
    usr_msg = USER_PROMPT_TEMPLATE.format(
        repo=bundle.repo,
        metadata=json.dumps(bundle.metadata, ensure_ascii=False, indent=2),
        license_key=bundle.license_key,
        license_text_block=license_block,
        readme_len=README_MAX_CHARS,
        readme=bundle.readme or "(empty)",
        depth=FILE_TREE_DEPTH,
        max_paths=FILE_TREE_MAX_PATHS,
        file_tree=bundle.file_tree or "(empty)",
        manifest_name=bundle.manifest_name or "n/a",
        manifest_content=manifest_block,
        entry_files_block=entry_block,
    )
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": usr_msg},
    ]


# ============== 输出校验 ==============


FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def parse_and_validate(raw: str, repo: str, license_key: str) -> tuple[dict[str, Any], str]:
    """返回 (frontmatter_dict, body_md)。失败抛 ValueError。"""
    cleaned = re.sub(r"^```(?:markdown|md)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```$", "", cleaned)

    m = FRONTMATTER_RE.match(cleaned)
    if not m:
        raise ValueError("没有有效的 YAML frontmatter (--- ... ---)")

    # 用 BaseLoader 把所有 scalar 当 string，避免 YYYY-MM-DD 被实例化为 date 等隐式转换
    try:
        fm = yaml.load(m.group(1), Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise ValueError(f"frontmatter YAML 解析失败: {e}")
    if not isinstance(fm, dict):
        raise ValueError("frontmatter 不是 dict")

    body = m.group(2)

    # 修正 repo 防幻觉重命名
    fm["repo"] = repo

    # schema 校验
    errors = sorted(Draft202012Validator(FRONTMATTER_SCHEMA).iter_errors(fm),
                    key=lambda e: e.path)
    if errors:
        msg = "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])
        raise ValueError(f"frontmatter schema 失败: {msg}")

    if not fm.get("question_match"):
        raise ValueError("question_match 必填（rubric 强校验）")

    # 必含章节检查
    missing = [s for s in REQUIRED_SECTIONS if f"## {s}" not in body]
    if missing:
        raise ValueError(f"缺章节: {missing}")

    # 下一步只允许 1 条
    nextstep_m = re.search(r"##\s*下一步[^\n]*\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    if nextstep_m:
        bullets = [ln for ln in nextstep_m.group(1).splitlines()
                   if ln.strip().startswith(("- ", "* ", "1.", "2.", "3."))]
        if len(bullets) > 1:
            raise ValueError(f"下一步章节有 {len(bullets)} 条，rubric 限制 1 条")

    # license 不在白名单时不允许 "我打算抄走什么"
    if license_key not in LICENSE_WHITELIST and "## 我打算抄走什么" in body:
        raise ValueError(
            f"license={license_key} 不在白名单，不允许 '我打算抄走什么' 章节"
        )

    return fm, body


def write_entry(entries_dir: Path, repo: str, fm: dict[str, Any], body: str,
                metrics: LLMMetrics) -> Path:
    owner, name = repo.split("/", 1)
    path = entries_dir / f"{owner}-{name}.md"
    fm_str = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    content = f"---\n{fm_str}\n---\n{body.lstrip()}\n"
    path.write_text(content, encoding="utf-8")
    return path


# ============== inbox 反读 ==============


def repos_from_inbox(inbox_dir: Path) -> list[str]:
    """读 inbox/*.md 中 decision=deepdive 的 repo。"""
    out: list[str] = []
    for f in sorted(inbox_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(fm, dict) and fm.get("decision") == "deepdive":
            r = fm.get("repo")
            if isinstance(r, str) and "/" in r:
                out.append(r)
    return out


# ============== 主流程 ==============


def main() -> int:
    ap = argparse.ArgumentParser(description="radar.deepdive")
    ap.add_argument("repos", nargs="*", help="owner/repo（一个或多个）")
    ap.add_argument("--from-inbox", metavar="DIRECTION",
                    help="读取 inbox decision=deepdive 的条目")
    ap.add_argument("--direction", default="voice-pipeline",
                    help="entry 写入哪个 direction (默认 voice-pipeline)")
    ap.add_argument("--entry", help="强制指定入口文件路径")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--profile", help="覆盖 config.yaml 的 deepdive.active")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # 解析 repos 来源
    repos: list[str] = list(args.repos)
    if args.from_inbox:
        inbox = REPO_ROOT / args.from_inbox / "inbox"
        if not inbox.exists():
            err(f"缺 inbox: {inbox}")
            return 1
        repos.extend(repos_from_inbox(inbox))
    repos = list(dict.fromkeys(repos))   # 保序去重
    if args.limit:
        repos = repos[: args.limit]
    if not repos:
        err("没有 repos 可处理。给参数 owner/repo 或 --from-inbox。")
        return 2

    # 配置
    try:
        cfg = load_stage_config("deepdive", override_profile=args.profile)
    except (FileNotFoundError, KeyError, ValueError, EnvironmentError) as e:
        err(f"配置错误: {e}")
        return 1

    if cfg.max_runs_per_week and len(repos) > cfg.max_runs_per_week:
        err(f"请求 {len(repos)} 条，超过周配额 {cfg.max_runs_per_week}。"
            "用 --limit 截断或调 config.yaml。")
        return 1

    if not shutil.which("gh"):
        err("需要 gh CLI")
        return 1

    direction_dir = REPO_ROOT / args.direction
    entries_dir = direction_dir / "entries"
    questions_path = direction_dir / "questions.md"
    rubric_path = REPO_ROOT / "rubrics" / "deepdive.md"
    template_path = entries_dir / "_TEMPLATE.md"

    for p in (entries_dir, questions_path, rubric_path, template_path):
        if not p.exists():
            err(f"缺路径: {p}")
            return 1

    rubric = rubric_path.read_text(encoding="utf-8")
    questions = questions_path.read_text(encoding="utf-8")
    template = template_path.read_text(encoding="utf-8")

    ts = dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    run_dir = REPO_ROOT / "runs" / f"{ts}-deepdive"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "rubric-snapshot.md").write_text(rubric, encoding="utf-8")
    trace_path = run_dir / "deepdive-trace.jsonl"
    summary_path = run_dir / "summary.md"

    log(f"→ rubric: {rubric_path}")
    log(f"→ repos: {len(repos)} 条")
    log(f"→ profile: {cfg.profile_name}  ({cfg.provider})")
    log(f"→ model:   {cfg.model}")
    if cfg.api_base:
        log(f"→ api_base: {cfg.api_base}")
    log(f"→ run dir: {run_dir}")
    if args.dry_run:
        log("→ DRY RUN（不调 LLM）")

    counts = {"written": 0, "validate_failed": 0, "fetch_failed": 0, "llm_failed": 0}
    metrics_log: list[LLMMetrics] = []

    with trace_path.open("w", encoding="utf-8") as trace_f:
        for i, repo in enumerate(repos, 1):
            log(f"\n[{i}/{len(repos)}] {repo}")
            bundle = fetch_bundle(repo, entry_override=args.entry)
            if not bundle:
                err("  ! fetch 失败")
                counts["fetch_failed"] += 1
                trace_f.write(json.dumps(
                    {"repo": repo, "stage": "fetch", "error": "gh failed"},
                    ensure_ascii=False,
                ) + "\n")
                continue

            messages = build_messages(rubric, questions, template, bundle)
            if args.dry_run:
                trace_f.write(json.dumps(
                    {"repo": repo, "stage": "dry-run", "messages": messages},
                    ensure_ascii=False,
                ) + "\n")
                continue

            try:
                # 注意: thinking 模型 (kimi-k2.6) 的 reasoning_content 会吃 max_tokens，
                # 用 fallback 切到 Kimi 时需要 >= 12000 才能给最终 entry 留出预算。
                max_tokens = 12000 if "kimi" in cfg.model.lower() else 4000
                raw, metrics = call_llm(messages, cfg, max_tokens=max_tokens)
            except LLMCallError as e:
                err(f"  ! LLM 失败 ({e.metrics.latency_s}s): {e}")
                counts["llm_failed"] += 1
                metrics_log.append(e.metrics)
                trace_f.write(json.dumps(
                    {"repo": repo, "stage": "llm", "metrics": e.metrics.to_dict()},
                    ensure_ascii=False,
                ) + "\n")
                err("失败即停。")
                break

            metrics_log.append(metrics)
            log(f"  · llm {metrics.latency_s}s  "
                f"in={metrics.prompt_tokens} out={metrics.completion_tokens}"
                + (f" think={metrics.reasoning_chars}ch" if metrics.reasoning_chars else ""))

            try:
                fm, body = parse_and_validate(raw, repo, bundle.license_key)
            except ValueError as e:
                err(f"  ! 校验失败: {e}")
                counts["validate_failed"] += 1
                trace_f.write(json.dumps(
                    {"repo": repo, "stage": "validate", "error": str(e),
                     "metrics": metrics.to_dict(), "raw": raw},
                    ensure_ascii=False,
                ) + "\n")
                continue

            entry_path = write_entry(entries_dir, repo, fm, body, metrics)
            counts["written"] += 1
            log(f"  ✓ entry: {entry_path.relative_to(REPO_ROOT)}")

            trace_f.write(json.dumps(
                {"repo": repo, "stage": "done",
                 "metrics": metrics.to_dict(),
                 "frontmatter": fm, "raw": raw},
                ensure_ascii=False,
            ) + "\n")

    # Summary
    ok = [m for m in metrics_log if m.error is None]
    lat = [m.latency_s for m in ok]
    pt = [m.prompt_tokens or 0 for m in ok]
    ct = [m.completion_tokens or 0 for m in ok]
    tt = [m.total_tokens or 0 for m in ok]

    def stat(xs: list[float]) -> str:
        if not xs:
            return "n/a"
        return f"sum={sum(xs):.1f} avg={sum(xs)/len(xs):.1f} min={min(xs):.1f} max={max(xs):.1f}"

    summary_path.write_text("\n".join([
        f"# deepdive summary — {ts}",
        "",
        f"- direction: {args.direction}",
        f"- profile: {cfg.profile_name} ({cfg.provider})",
        f"- model: {cfg.model}",
        f"- rubric snapshot: rubric-snapshot.md",
        f"- repos: {len(repos)}",
        "",
        "## 结果",
        f"- written:          {counts['written']}",
        f"- validate_failed:  {counts['validate_failed']}",
        f"- fetch_failed:     {counts['fetch_failed']}",
        f"- llm_failed:       {counts['llm_failed']}",
        "",
        f"## LLM 用量（成功 {len(ok)} 次）",
        f"- 时延 (秒):       {stat(lat)}",
        f"- prompt_tokens:   {stat(pt)}",
        f"- completion_tokens: {stat(ct)}",
        f"- total_tokens:    {stat(tt)}",
    ]), encoding="utf-8")

    log("\n✓ done")
    log(f"  written={counts['written']} validate_failed={counts['validate_failed']} "
        f"fetch_failed={counts['fetch_failed']} llm_failed={counts['llm_failed']}")
    if ok:
        log(f"  llm: 共 {len(ok)} 次, 总耗时 {sum(lat):.1f}s, "
            f"总 token {sum(tt)} (in={sum(pt)} out={sum(ct)})")
    log(f"  trace: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
