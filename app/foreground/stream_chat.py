from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.config import get_settings


SALES_SYSTEM = """你是热情、专业的影视推荐销售顾问。回复要短、口语化，像真人聊天。
不要一次罗列过多片名；优先用问句引导用户说出偏好。"""


def build_client() -> AsyncOpenAI:
    s = get_settings()
    kwargs: dict = {"api_key": s.openai_api_key}
    if s.openai_base_url:
        kwargs["base_url"] = s.openai_base_url
    return AsyncOpenAI(**kwargs)


async def stream_assistant_reply(
    *,
    user_text: str,
    strategy_instruction: str,
    history: list[dict[str, str]],
) -> AsyncIterator[str]:
    s = get_settings()
    if not s.openai_api_key:
        yield "[错误] 未配置 OPENAI_API_KEY，请在 .env 中填写。"
        return

    client = build_client()
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SALES_SYSTEM},
        {
            "role": "system",
            "content": f"【当前导航策略】{strategy_instruction}\n请严格按此策略组织本轮话术。",
        },
    ]
    for m in history[-20:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})

    stream = await client.chat.completions.create(
        model=s.openai_model,
        messages=messages,
        stream=True,
        temperature=0.7,
    )
    async for chunk in stream:
        choice = chunk.choices[0]
        if choice.delta and choice.delta.content:
            yield choice.delta.content
