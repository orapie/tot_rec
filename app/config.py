from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_api_key: str = ""
    # 默认 LLM：未单独配置前台/后台时，两者共用以下变量（仍是一套 API Key）
    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Kimi 等部分模型仅允许 temperature=1；OpenAI 可改为 0.7 等
    openai_temperature: float = 1.0

    # 前台 Agent（话术丝滑、严格执行策略）：留空则继承上面的 OPENAI_*
    foreground_openai_api_key: str = ""
    foreground_openai_base_url: str = ""
    foreground_openai_model: str = ""
    foreground_openai_temperature: Optional[float] = None

    # 后台 Agent（推演 / ToT / 导航）：留空则继承 OPENAI_*；可换更强模型而不影响前台
    background_openai_api_key: str = ""
    background_openai_base_url: str = ""
    background_openai_model: str = ""
    background_openai_temperature: Optional[float] = None
    background_max_tokens: int = 512

    # DuRecDial 阶段 A：convert.py 产出的 strategies.json 注入后台 navigator
    durecdial_enable: bool = False
    durecdial_strategies_path: str = ""  # 留空则使用 data/processed_data/strategies.json（相对项目根）
    # DuRecDial 阶段 B：knowledge_rag.jsonl 检索注入（RAG）
    durecdial_knowledge_path: str = ""  # 留空则使用 data/processed_data/knowledge_rag.jsonl（相对项目根）
    rag_top_k: int = 3

    # DuRecDial 阶段 C：chat_samples.jsonl 前台 few-shot 注入
    few_shot_enable: bool = False
    chat_samples_path: str = ""   # 留空则使用 data/processed_data/chat_samples.jsonl（相对项目根）
    few_shot_max_samples: int = 2  # 注入条数上限（建议 1-3，过多会超 token）

    redis_url: str | None = None
    # HTTP 监听端口（可用环境变量 PORT 覆盖）；默认高位端口，减少与其它服务冲突
    port: int = 38421


@lru_cache
def get_settings() -> Settings:
    return Settings()
