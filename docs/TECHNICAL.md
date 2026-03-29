# tot_rec 技术文档

本文档描述仓库内**已实现**的代码结构、运行时行为、配置项与接口约定。高层产品设计见仓库根目录 [`ARCHITECTURE.md`](../ARCHITECTURE.md)。

---

## 1. 项目定位

**tot_rec** 是一个基于 **FastAPI** 的异步对话服务原型，实现「**前台话术 Agent** + **后台导航 Agent** + **动态策略池**」：

| 组件 | 职责 | 实现位置 |
|------|------|----------|
| 前台 Agent | 流式生成对用户的回复；人设 + **严格执行当前策略指令** | `app/foreground/stream_chat.py` |
| 后台 Agent | 根据对话与最新用户输入，**异步**更新「下一条」导航策略（不写用户可见话术） | `app/background/navigator.py` |
| 策略池 | 按 `session_id` 存储当前导航指令；前台每轮**先读**再生成 | `app/state/strategy_store.py` |
| LLM 路由 | 前后台可共用或拆分 **API Key / Base URL / 模型 / 温度** | `app/llm/resolve.py` |

> **如何理解「两个 Agent」**：即使只配置一套 `OPENAI_*`（同一厂商、同一模型名），代码路径仍是**两条**——两次独立的 `chat.completions` 调用、两套 System 提示（销售话术 vs 导航器）。若配置了 `FOREGROUND_*` / `BACKGROUND_*`，则可使用不同模型或端点。

---

## 2. 运行时与并发模型

```
用户 WebSocket 消息
    │
    ├─► 从策略池读取 strategy（上一轮后台写入）
    ├─► asyncio.create_task(后台 navigator) ──► 完成后写策略池，并可向客户端推送 strategy_updated
    └─► 前台 stream_assistant_reply（流式）──► token 帧
```

- **不阻塞**：前台不等待后台 navigator 完成；本轮前台使用的是**进入本轮前**策略池中的指令。
- **滞后一回合**：用户第一条消息时，策略多为默认值；从第二轮起，策略通常反映上一轮后台的推演结果（与产品设计一致时可接受）。
- **异常**：前台流式或后台任务出错时，通过 WebSocket 下发 `type: error`，并尽量发送 `assistant_done`，避免连接被粗暴断开（见 `app/main.py`）。

---

## 3. 目录结构

```
tot_rec/
├── main.py                 # 入口：uvicorn 启动 app.main:app
├── requirements.txt
├── .env.example
├── ARCHITECTURE.md         # 概念架构（Mermaid）
├── docs/
│   └── TECHNICAL.md        # 本文件
├── app/
│   ├── main.py             # FastAPI 路由、WebSocket /health /ready
│   ├── config.py           # pydantic-settings，从 .env 加载
│   ├── auth.py             # APP_API_KEY（HTTP / WebSocket）
│   ├── llm/
│   │   ├── clients.py      # OpenAI 兼容 AsyncOpenAI 构造
│   │   └── resolve.py      # get_foreground_runtime / get_background_runtime
│   ├── foreground/
│   │   └── stream_chat.py  # 前台流式生成
│   ├── background/
│   │   └── navigator.py    # 后台写策略
│   └── state/
│       └── strategy_store.py  # 内存或 Redis
└── scripts/
    └── ws_chat.py          # 终端 WebSocket 调试客户端
```

---

## 4. 依赖栈

| 依赖 | 用途 |
|------|------|
| fastapi / uvicorn | HTTP + WebSocket ASGI |
| pydantic-settings | 配置与 `.env` |
| openai | OpenAI 兼容异步客户端（Kimi / vLLM 等） |
| redis | 可选策略持久化 |
| httpx | 间接依赖（openai） |
| websockets | 仅 `scripts/ws_chat.py` 客户端 |

Python 建议 **3.11+**（当前开发常用 3.12）。

---

## 5. 配置说明（环境变量）

配置集中在 `app/config.py`，通过 **`.env`** 或环境变量注入（`get_settings()` 带 `lru_cache`，修改 `.env` 后需**重启进程**）。

### 5.1 服务

| 变量 | 说明 |
|------|------|
| `PORT` | HTTP 监听端口，默认 `38421` |
| `APP_API_KEY` | 访问本服务的密钥；**留空**时不校验（仅建议本机调试） |
| `REDIS_URL` | 若设置则策略池用 Redis；否则进程内字典（单机、多 worker 不共享） |

### 5.2 默认 LLM（前后台未单独覆盖时共用）

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | 厂商 API Key（Kimi / OpenAI / 兼容网关） |
| `OPENAI_BASE_URL` | 如 `https://api.moonshot.cn/v1` |
| `OPENAI_MODEL` | 模型名 |
| `OPENAI_TEMPERATURE` | 采样温度；**部分 Kimi 模型仅允许 `1`** |

### 5.3 前台 / 后台独立覆盖（可选）

任一字段非空或非默认时，对应 Agent **不再**仅用 `OPENAI_*` 的该维度：

| 前缀 | 含义 |
|------|------|
| `FOREGROUND_OPENAI_API_KEY` 等 | 仅前台 |
| `BACKGROUND_OPENAI_API_KEY` 等 | 仅后台 |
| `BACKGROUND_MAX_TOKENS` | 后台 navigator 单次补全上限，默认 `512` |

温度字段 `FOREGROUND_OPENAI_TEMPERATURE` / `BACKGROUND_OPENAI_TEMPERATURE` 为 **可选**：未设置则继承 `OPENAI_TEMPERATURE`。

---

## 6. HTTP 接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/` | 无 | 返回服务说明与常用 URL |
| GET | `/health` | 无 | 存活探针 |
| GET | `/ready` | 若配置了 `APP_API_KEY` 则需 `X-API-Key` 或 `Authorization: Bearer` | 就绪探针 |
| GET | `/docs` | 无 | Swagger UI |

---

## 7. WebSocket：`/ws/chat`

### 7.1 连接与鉴权

- URL：`ws://<host>:<port>/ws/chat`
- 若启用 `APP_API_KEY`：查询参数 `?api_key=` 或请求头 `X-API-Key` / `Authorization: Bearer`

### 7.2 客户端 → 服务端

文本帧，JSON：

```json
{"type": "user_message", "text": "用户输入"}
```

### 7.3 服务端 → 客户端（消息类型）

| `type` | 含义 |
|--------|------|
| `session` | 含 `session_id`，会话级策略键 |
| `assistant_start` | 本轮前台回复开始 |
| `token` | 流式片段，字段 `text` |
| `assistant_done` | 本轮前台回复结束 |
| `strategy_updated` | 后台写入新策略，`instruction`、`version` |
| `error` | 错误说明 `message` |

---

## 8. 策略池（Redis / 内存）

- **键**：Redis 模式下为 `strategy:{session_id}`（JSON）；内存模式为进程内 `dict`。
- **字段**：`instruction`（导航正文）、`version`（单调递增）、`updated_at`。
- **默认指令**：当某会话尚无记录时，使用模块内默认短句（见 `strategy_store.py`）。

---

## 9. 安全与运维注意

- **勿将 `.env` 提交到版本库**；`.env.example` 仅含占位符。
- 公网部署务必设置强 `APP_API_KEY`，并配合 HTTPS / WSS 与反向代理。
- **多实例**：无 Redis 时各进程策略池不互通；生产建议配置 `REDIS_URL`。
- **Kimi 限制**：若 API 返回 `temperature` 仅允许 `1`，需将 `OPENAI_TEMPERATURE`（或前后台覆盖）设为 `1`。

---

## 10. 本地运行

```bash
cd tot_rec
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 编辑填入 Key 等
python main.py
```

**须使用虚拟环境内的解释器**，否则会出现 `ModuleNotFoundError: uvicorn`。

终端 WebSocket 客户端：

```bash
python scripts/ws_chat.py
```

---

## 11. 扩展与演进（未在代码中强制）

- **LangGraph / ToT**：将 `navigator.py` 中单次补全替换为状态机或多节点图，输出仍写入策略池即可。
- **观测**：可在前后台入口增加结构化日志（模型名、`session_id`），或增加只读 `GET /debug/agents` 返回解析后的模型配置（注意勿泄露 Key）。
- **前台专用小模型**：仅设置 `FOREGROUND_OPENAI_MODEL` 为更小、更快模型；后台用 `BACKGROUND_OPENAI_MODEL` 指向更强模型。

---

## 12. 文档关系

| 文件 | 内容 |
|------|------|
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | 产品级双轨、Redis、LangGraph 设想、部署拓扑 |
| `docs/TECHNICAL.md` | 本文件：与代码一致的实现细节与运维 |

---

*文档版本随代码迭代；若接口或配置变更，请同步更新本节与 `.env.example`。*
