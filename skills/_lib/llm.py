"""LLM 调用的共享包装：返回内容 + 时延 + token 用量。

设计：
    - 通过 LiteLLM 的 OpenAI 兼容协议调用任何 provider
    - 一律返回 (content_str, LLMMetrics)，避免上层各自抠 usage 字段
    - thinking 模型的 reasoning_content 只记长度，不进 content（content 已是最终答复）
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from .config import StageConfig


@dataclass
class LLMMetrics:
    latency_s: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    finish_reason: str | None
    model: str
    profile_name: str
    reasoning_chars: int | None = None   # thinking 模型的 reasoning_content 长度
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def call_llm(messages: list[dict[str, str]], cfg: StageConfig,
             max_tokens: int | None = None) -> tuple[str, LLMMetrics]:
    """调一次 LLM，返回 (content, metrics)。

    抛出的异常由调用方处理；本函数即便失败也会把 metrics 半填好（含 error）。
    """
    try:
        import litellm
    except ImportError:
        raise RuntimeError(
            "缺 litellm，运行: pip3 install --break-system-packages litellm"
        )

    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "messages": messages,
        "timeout": cfg.timeout_seconds,
        "temperature": cfg.temperature,
    }
    if cfg.api_base:
        kwargs["api_base"] = cfg.api_base
    if cfg.api_key:
        kwargs["api_key"] = cfg.api_key
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    t0 = time.monotonic()
    try:
        resp = litellm.completion(**kwargs)
    except Exception as e:
        elapsed = time.monotonic() - t0
        raise LLMCallError(
            metrics=LLMMetrics(
                latency_s=round(elapsed, 3),
                prompt_tokens=None,
                completion_tokens=None,
                total_tokens=None,
                finish_reason=None,
                model=cfg.model,
                profile_name=cfg.profile_name,
                error=f"{type(e).__name__}: {e}",
            )
        ) from e

    elapsed = time.monotonic() - t0
    choice = resp["choices"][0]
    msg = choice["message"]
    usage = resp.get("usage") or {}
    reasoning = msg.get("reasoning_content")

    metrics = LLMMetrics(
        latency_s=round(elapsed, 3),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        finish_reason=choice.get("finish_reason"),
        model=cfg.model,
        profile_name=cfg.profile_name,
        reasoning_chars=len(reasoning) if isinstance(reasoning, str) else None,
    )
    return (msg.get("content") or ""), metrics


class LLMCallError(Exception):
    """LLM 调用失败，但仍带回了部分 metrics（延迟、error 字符串）。"""

    def __init__(self, metrics: LLMMetrics):
        super().__init__(metrics.error or "LLM call failed")
        self.metrics = metrics
