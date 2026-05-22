"""读取根目录 config.yaml，提供阶段级模型设置。

用法:
    from skills._lib.config import load_stage_config
    cfg = load_stage_config("triage")
    # cfg.model, cfg.api_base, cfg.api_key, cfg.temperature, cfg.timeout, cfg.fallback

启动时会自动加载根目录 .env 文件（若存在），从而把 *_API_KEY 注入进程环境。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config.yaml"
ENV_PATH = REPO_ROOT / ".env"

# 在 import 时尝试加载 .env（不存在/装不上 dotenv 都静默）
try:
    from dotenv import load_dotenv  # type: ignore
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
except ImportError:
    pass


@dataclass
class StageConfig:
    stage: str               # "triage" | "deepdive"
    profile_name: str        # e.g. "local-qwen3-14b"
    provider: str            # ollama / openai / anthropic / deepseek
    model: str               # 传给 litellm.completion(model=...)
    api_base: str | None
    api_key: str | None      # 从 env 解析后的实际值（None = 不需要）
    temperature: float
    timeout_seconds: int
    fallback_profile: str | None
    max_runs_per_week: int | None  # 仅 deepdive 有


def _resolve_profile(
    stage_name: str,
    profile_name: str,
    profiles: dict[str, Any],
    base: dict[str, Any],
) -> dict[str, Any]:
    if profile_name not in profiles:
        raise KeyError(
            f"config.yaml: stage={stage_name} 引用了不存在的 profile '{profile_name}'。"
            f" 可用: {list(profiles.keys())}"
        )
    return profiles[profile_name]


def load_stage_config(stage: str, override_profile: str | None = None) -> StageConfig:
    """加载 stage 的运行时配置。

    Args:
        stage: "triage" 或 "deepdive"
        override_profile: 若指定，使用此 profile 而非 active
    """
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"缺 config.yaml: {CONFIG_PATH}")

    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if stage not in raw:
        raise KeyError(f"config.yaml 没有 {stage} 段")

    section = raw[stage]
    profiles = section.get("profiles", {})
    active = override_profile or section.get("active")
    if not active:
        raise ValueError(f"config.yaml: {stage}.active 未设置")

    prof = _resolve_profile(stage, active, profiles, section)

    api_key_env = prof.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None
    if api_key_env and not api_key:
        raise EnvironmentError(
            f"profile '{active}' 需要环境变量 {api_key_env} (provider={prof['provider']})"
        )

    fallback = section.get("fallback")

    return StageConfig(
        stage=stage,
        profile_name=active,
        provider=prof["provider"],
        model=prof["model"],
        api_base=prof.get("api_base"),
        api_key=api_key,
        temperature=section.get("temperature", 0.2),
        timeout_seconds=section.get("timeout_seconds", 60),
        fallback_profile=fallback,
        max_runs_per_week=section.get("max_runs_per_week"),
    )
