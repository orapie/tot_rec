#!/usr/bin/env python3
"""
终端 WebSocket 对话客户端。请先启动服务：python main.py

用法（在项目根目录）:
  python scripts/ws_chat.py
  python scripts/ws_chat.py --host 127.0.0.1

读取项目根目录 .env 中的 PORT、APP_API_KEY（可选）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _settings() -> tuple[str, int, str]:
    import os

    _load_env()
    host = os.environ.get("WS_CHAT_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "38421"))
    key = (os.environ.get("APP_API_KEY") or "").strip()
    return host, port, key


_print_lock = asyncio.Lock()
_waiting_user_input = False


async def _println(line: str = "") -> None:
    async with _print_lock:
        print(line, flush=True)


def _print_user_prompt() -> None:
    print("你: ", end="", flush=True)


def _handle_incoming_json(msg: dict) -> None:
    t = msg.get("type")
    if t == "session":
        print(f"[session] id={msg.get('session_id')}", flush=True)
    elif t == "assistant_start":
        print("\n助手: ", end="", flush=True)
    elif t == "token":
        piece = msg.get("text") or ""
        print(piece, end="", flush=True)
    elif t == "assistant_done":
        print(flush=True)
    elif t == "strategy_updated":
        # 后台策略更新只用于服务端下一轮控制，不在终端回显。
        return
    elif t == "error":
        print(f"\n[错误] {msg.get('message')}", flush=True)
    else:
        print(f"\n[{t}] {msg}", flush=True)


async def _recv_loop(ws) -> None:
    from websockets.exceptions import ConnectionClosed

    global _waiting_user_input
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _println(f"[raw] {raw}")
                continue
            async with _print_lock:
                _handle_incoming_json(msg)
                # 当接收消息覆盖了输入行时，补回输入提示，保证“你:”始终先出现。
                t = msg.get("type")
                if _waiting_user_input and t in {"assistant_done", "error"}:
                    _print_user_prompt()
    except ConnectionClosed as e:
        await _println(f"\n[连接已关闭] {getattr(e, 'reason', None) or e}")


async def _send_loop(ws) -> None:
    from websockets.exceptions import ConnectionClosed

    global _waiting_user_input
    await _println('输入消息后回车发送；输入 "quit" 或 Ctrl+D 退出。\n')
    loop = asyncio.get_running_loop()
    while True:
        try:
            async with _print_lock:
                _waiting_user_input = True
                _print_user_prompt()
            line = await loop.run_in_executor(None, lambda: input().strip())
        except (EOFError, KeyboardInterrupt):
            _waiting_user_input = False
            await _println()
            break
        _waiting_user_input = False
        if not line:
            continue
        if line.lower() in ("quit", "exit", "q"):
            break
        try:
            await ws.send(json.dumps({"type": "user_message", "text": line}, ensure_ascii=False))
        except ConnectionClosed as e:
            await _println(f"\n[无法发送：连接已断开] {getattr(e, 'reason', None) or e}")
            break


async def main(host: str, port: int, api_key: str) -> None:
    import websockets  # noqa: PLC0415

    q = f"?api_key={api_key}" if api_key else ""
    uri = f"ws://{host}:{port}/ws/chat{q}"
    print(f"连接 {uri} ...", flush=True)
    async with websockets.connect(
        uri,
        ping_interval=20,
        ping_timeout=120,
        close_timeout=10,
    ) as ws:
        # 先读完服务端发来的 session，避免与 input 提示交错在同一行
        try:
            first = await asyncio.wait_for(ws.recv(), timeout=30.0)
        except TimeoutError:
            print("[错误] 未收到 session，请确认服务已启动且端口正确。", flush=True)
            return
        try:
            msg = json.loads(first)
            _handle_incoming_json(msg)
        except json.JSONDecodeError:
            print(f"[首包] {first}", flush=True)

        recv_task = asyncio.create_task(_recv_loop(ws))
        try:
            await _send_loop(ws)
        finally:
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="tot_rec 终端 WebSocket 客户端")
    parser.add_argument("--host", default=None, help="默认 127.0.0.1 或环境变量 WS_CHAT_HOST")
    args = parser.parse_args()
    h, p, k = _settings()
    if args.host:
        h = args.host
    try:
        asyncio.run(main(h, p, k))
    except ConnectionRefusedError:
        print("无法连接：请先在本机启动服务 (python main.py)，并检查 PORT 与 .env 是否一致。", file=sys.stderr)
        sys.exit(1)
