"""双 Agent LLM：前台（话术）与后台（推演）可共用或拆分 API / 模型 / 温度。"""

from app.llm.resolve import AgentRuntime, get_background_runtime, get_foreground_runtime

__all__ = ["AgentRuntime", "get_foreground_runtime", "get_background_runtime"]
