from fastapi import HTTPException, WebSocket, status

from app.config import get_settings


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return None


def verify_http_api_key(x_api_key: str | None, authorization: str | None) -> None:
    settings = get_settings()
    expected = (settings.app_api_key or "").strip()
    if not expected:
        return
    got = x_api_key or _extract_bearer(authorization)
    if got != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


async def verify_ws_api_key(websocket: WebSocket) -> bool:
    """校验通过返回 True；失败时已 close，返回 False。
    APP_API_KEY 为空时不校验（仅建议本机开发；公网务必配置密钥）。"""
    settings = get_settings()
    expected = (settings.app_api_key or "").strip()
    if not expected:
        return True

    q = websocket.query_params.get("api_key")
    header = websocket.headers.get("x-api-key") or _extract_bearer(
        websocket.headers.get("authorization")
    )
    if (q or header) == expected:
        return True
    await websocket.close(code=4401)
    return False
