from openai import AsyncOpenAI

from app.config import get_settings
from app.foreground.stream_chat import build_client
from app.state.strategy_store import StrategyStore


NAV_SYSTEM = """你是对话导航器，不负责写给用户看的句子。
根据最近对话与最新用户输入，产出**一条**给前台销售机器人用的简短策略指令（中文，不超过80字）。
只输出策略正文，不要引号、不要前缀如「策略：」。"""


async def run_navigation_update(
    *,
    session_id: str,
    user_text: str,
    history: list[dict[str, str]],
    store: StrategyStore,
) -> dict:
    """后台异步：写入 Redis/内存中的下一条导航策略。"""
    s = get_settings()
    if not s.openai_api_key:
        return await store.set_instruction(session_id, "保持自然追问，澄清类型、年代或观影场景。")

    client: AsyncOpenAI = build_client()
    compact = []
    for m in history[-12:]:
        compact.append(f'{m["role"]}: {m["content"]}')
    compact.append(f"user: {user_text}")
    blob = "\n".join(compact)

    resp = await client.chat.completions.create(
        model=s.openai_model,
        messages=[
            {"role": "system", "content": NAV_SYSTEM},
            {"role": "user", "content": f"对话摘录：\n{blob}\n\n请输出下一条导航策略。"},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    text = (resp.choices[0].message.content or "").strip()
    return await store.set_instruction(session_id, text)
