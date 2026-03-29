"""本地启动：python main.py（端口见 .env 中 PORT，默认 38421）"""

import uvicorn

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=s.port, reload=True)
