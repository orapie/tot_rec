import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import Depends, FastAPI, Header, Request, WebSocket, WebSocketDisconnect

from app.auth import verify_http_api_key, verify_ws_api_key
from app.background.navigator import run_navigation_update
from app.foreground.stream_chat import stream_assistant_reply
from app.knowledge.retriever import warmup_retriever
from app.state.strategy_store import StrategyStore, get_strategy_store

logger = logging.getLogger(__name__)

app = FastAPI(title="tot_rec", version="0.1.0")


@app.on_event("startup")
async def _startup() -> None:
    warmup_retriever()


@app.get("/")
async def root(request: Request) -> dict[str, str]:
    u = request.url
    base = f"{u.scheme}://{u.netloc}"
    ws_scheme = "wss" if u.scheme == "https" else "ws"
    ws_base = f"{ws_scheme}://{u.netloc}"
    return {
        "service": "tot_rec",
        "health": f"{base}/health",
        "ready": f"{base}/ready (若配置了 APP_API_KEY 需带头 X-API-Key)",
        "docs": f"{base}/docs",
        "websocket_chat": f"{ws_base}/ws/chat",
        "usage": "浏览器打开 docs 可测 HTTP；聊天需 WebSocket 客户端连接 websocket_chat（可带 ?api_key=）",
    }


def http_auth(
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    authorization: str | None = Header(None),
) -> None:
    verify_http_api_key(x_api_key, authorization)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready(_: None = Depends(http_auth)) -> dict[str, str]:
    return {"status": "ready"}


@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    if not await verify_ws_api_key(websocket):
        return

    await websocket.accept()
    session_id = str(uuid.uuid4())
    history: list[dict[str, str]] = []
    store: StrategyStore = await get_strategy_store()

    await websocket.send_json(
        {
            "type": "session",
            "session_id": session_id,
        }
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload: dict[str, Any] = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            if payload.get("type") != "user_message":
                await websocket.send_json({"type": "error", "message": "unknown type"})
                continue

            user_text = (payload.get("text") or "").strip()
            if not user_text:
                await websocket.send_json({"type": "error", "message": "empty text"})
                continue

            # 本轮用于前台的策略（上一轮后台写入）
            strategy = await store.get(session_id)
            history_before = list(history)

            async def background() -> None:
                try:
                    row = await run_navigation_update(
                        session_id=session_id,
                        user_text=user_text,
                        history=history_before,
                        store=store,
                    )
                    await websocket.send_json(
                        {
                            "type": "strategy_updated",
                            "instruction": row["instruction"],
                            "version": row["version"],
                        }
                    )
                except Exception as e:  # noqa: BLE001
                    await websocket.send_json(
                        {"type": "error", "message": f"navigator failed: {e!s}"}
                    )

            asyncio.create_task(background())

            await websocket.send_json({"type": "assistant_start"})
            full: list[str] = []
            try:
                async for token in stream_assistant_reply(
                    user_text=user_text,
                    strategy_instruction=strategy["instruction"],
                    history=history_before,
                ):
                    full.append(token)
                    await websocket.send_json({"type": "token", "text": token})
            except Exception as e:  # noqa: BLE001
                logger.exception("stream_assistant_reply failed")
                try:
                    await websocket.send_json(
                        {"type": "error", "message": f"前台生成失败: {e!s}"}
                    )
                except Exception:
                    pass
            finally:
                try:
                    await websocket.send_json({"type": "assistant_done"})
                except Exception:
                    pass

            assistant_body = "".join(full)
            history.append({"role": "user", "content": user_text})
            if assistant_body:
                history.append({"role": "assistant", "content": assistant_body})

    except WebSocketDisconnect:
        return
