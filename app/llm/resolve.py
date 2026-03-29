from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI

from app.config import Settings, get_settings
from app.llm.clients import make_async_client


@dataclass(frozen=True)
class AgentRuntime:
    """单次请求所需的 OpenAI 兼容客户端与采样参数。"""

    client: AsyncOpenAI
    model: str
    temperature: float


def _strip_or(s: str | None, fallback: str | None) -> str | None:
    if s is None:
        return fallback
    t = s.strip()
    return t if t else fallback


def _resolve_agent(s: Settings, role: Literal["foreground", "background"]) -> AgentRuntime | None:
    if role == "foreground":
        key = _strip_or(s.foreground_openai_api_key, None) or s.openai_api_key
        base = _strip_or(s.foreground_openai_base_url, None)
        if not base:
            base = s.openai_base_url
        model = _strip_or(s.foreground_openai_model, None) or s.openai_model
        temp = (
            s.foreground_openai_temperature
            if s.foreground_openai_temperature is not None
            else s.openai_temperature
        )
    else:
        key = _strip_or(s.background_openai_api_key, None) or s.openai_api_key
        base = _strip_or(s.background_openai_base_url, None)
        if not base:
            base = s.openai_base_url
        model = _strip_or(s.background_openai_model, None) or s.openai_model
        temp = (
            s.background_openai_temperature
            if s.background_openai_temperature is not None
            else s.openai_temperature
        )

    if not key or not key.strip():
        return None
    return AgentRuntime(
        client=make_async_client(api_key=key.strip(), base_url=base),
        model=model,
        temperature=temp,
    )


def get_foreground_runtime() -> AgentRuntime | None:
    return _resolve_agent(get_settings(), "foreground")


def get_background_runtime() -> AgentRuntime | None:
    return _resolve_agent(get_settings(), "background")
