from collections.abc import AsyncIterator

from app.llm.resolve import get_foreground_runtime


SALES_SYSTEM = """你是热情、专业的影视推荐销售顾问。回复要短、口语化，像真人聊天。
不要一次罗列过多片名；优先用问句引导用户说出偏好。
你必须严格执行下方【当前导航策略】中的约束，不得偏离。"""


async def stream_assistant_reply(
    *,
    user_text: str,
    strategy_instruction: str,
    history: list[dict[str, str]],
) -> AsyncIterator[str]:
    rt = get_foreground_runtime()
    if rt is None:
        yield "[错误] 未配置前台 LLM：请设置 OPENAI_API_KEY（或 FOREGROUND_OPENAI_API_KEY）。"
        return

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

    stream = await rt.client.chat.completions.create(
        model=rt.model,
        messages=messages,
        stream=True,
        temperature=rt.temperature,
    )
    async for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.delta and choice.delta.content:
            yield choice.delta.content
