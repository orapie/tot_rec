from openai import AsyncOpenAI


def make_async_client(*, api_key: str, base_url: str | None) -> AsyncOpenAI:
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)
