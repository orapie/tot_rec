# tot_rec

异步双 Agent 对话服务：**前台**负责流式话术（严格执行导航策略），**后台**并行更新「下一条」策略指令；二者通过**策略池**（内存或 Redis）共享状态。适用于推荐、导购、ToT 导航等需要「快响应 + 慢思考」拆分的场景。

---

## 特性

- **FastAPI + WebSocket**：流式 token 下发，长连接对话  
- **OpenAI 兼容 API**：支持 Kimi（Moonshot）、OpenAI、自建 vLLM 等  
- **双 LLM 配置**：可共用一套 `OPENAI_*`，或用 `FOREGROUND_*` / `BACKGROUND_*` 拆模型与端点  
- **可选 Redis**：多实例时共享策略；不设则单机内存  
- **API Key 保护服务**：`APP_API_KEY`（可选，本机调试可留空）

---

## 快速开始

```bash
git clone <你的仓库地址>
cd tot_rec

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env：至少填写 OPENAI_API_KEY、OPENAI_BASE_URL、OPENAI_MODEL（Kimi 注意 temperature=1）

python main.py
```

默认监听 **`http://0.0.0.0:38421`**（可用环境变量 `PORT` 修改）。

- 浏览器：<http://127.0.0.1:38421/docs>  
- 健康检查：<http://127.0.0.1:38421/health>  

**终端 WebSocket 客户端**（需服务已启动）：

```bash
python scripts/ws_chat.py
```

连接地址与鉴权见 `.env` 中的 `PORT`、`APP_API_KEY`。

> 请始终用**虚拟环境里的 Python** 运行，否则可能报 `No module named 'uvicorn'`。

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | 目录结构、配置表、HTTP/WebSocket 协议、并发与策略池 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 产品级架构、技术栈选型、演进设想（LangGraph / Redis 等） |
| [strategy/](strategy/README.md) | 阶段性策略与数据接入规划（如 DuRecDial） |

---

## 环境变量摘要

详见 `.env.example` 与 [docs/TECHNICAL.md](docs/TECHNICAL.md)。

- **服务**：`PORT`、`APP_API_KEY`、`REDIS_URL`  
- **默认 LLM**：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OPENAI_TEMPERATURE`  
- **可选拆分**：`FOREGROUND_OPENAI_*`、`BACKGROUND_OPENAI_*`、`BACKGROUND_MAX_TOKENS`  

---

## 技术栈

Python 3.11+ · FastAPI · Uvicorn · pydantic-settings · OpenAI Python SDK（兼容接口）· 可选 Redis

---

## 许可

若未单独声明许可证，以仓库内 `LICENSE` 为准（如有）。
