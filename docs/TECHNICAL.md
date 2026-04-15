# tot_rec 技术文档

本文档描述仓库内**当前已实现**的代码结构、运行时行为、配置项与接口约定。高层说明见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

## 1. 项目定位

**tot_rec** 是一个基于 **FastAPI** 的异步对话服务，核心是「前台流式回复 + 后台并行导航 + 会话策略池」：

| 组件 | 职责 | 实现位置 |
|------|------|----------|
| 前台 Agent | 流式生成用户可见回复；严格执行当前策略指令 | `app/foreground/stream_chat.py` |
| 后台 Agent | 根据当前轮对话推演下一条策略；不直接生成用户可见文本 | `app/background/navigator.py` |
| 策略池 | 以 `session_id` 存储策略，供前台每轮读取 | `app/state/strategy_store.py` |
| DuRecDial 知识层 | 阶段 A：剧本参考；阶段 B：RAG 证据检索 | `app/knowledge/strategies_store.py`、`app/knowledge/retriever.py` |
| LLM 路由 | 前后台独立解析模型、base_url、温度 | `app/llm/resolve.py` |

---

## 2. 运行时并发模型

```
用户 WebSocket 消息
    │
    ├─► 读取策略池（上一轮后台写入）
    ├─► asyncio.create_task(后台 navigator)
    │       └─► 生成并写入新策略（strategy_updated 事件可推送）
    └─► 前台 stream_assistant_reply（流式 token）
```

- 前台与后台并行，前台不等待后台完成。
- 本轮前台使用的是“本轮开始前”的策略；新策略通常下一轮生效。
- 后台 prompt 在 `DURECDIAL_ENABLE=true` 时会注入：
  - `【DuRecDial 参考剧本】`（`strategies.json`）
  - `【DuRecDial 检索证据】`（`knowledge_rag.jsonl` BM25 top-k）

---

## 3. 目录结构（当前实现）

```
tot_rec/
├── main.py
├── start.sh                 # 激活 .venv 并启动 main.py
├── start_ws_chat.sh         # 激活 .venv 并启动 scripts/ws_chat.py
├── requirements.txt
├── .env.example
├── docs/
│   ├── ARCHITECTURE.md
│   └── TECHNICAL.md
├── app/
│   ├── main.py
│   ├── config.py
│   ├── auth.py
│   ├── llm/
│   │   ├── clients.py
│   │   └── resolve.py
│   ├── foreground/
│   │   └── stream_chat.py
│   ├── background/
│   │   └── navigator.py
│   ├── knowledge/
│   │   ├── strategies_store.py
│   │   └── retriever.py
│   └── state/
│       └── strategy_store.py
└── scripts/
    └── ws_chat.py
```

---

## 4. 依赖栈

| 依赖 | 用途 |
|------|------|
| `fastapi`, `uvicorn` | HTTP + WebSocket 服务 |
| `pydantic-settings` | 配置加载（`.env`） |
| `openai` | OpenAI 兼容异步客户端 |
| `redis` | 可选策略存储 |
| `websockets` | 终端 WebSocket 客户端 |
| `python-dotenv` | 客户端读取 `.env` |

Python 建议 `3.11+`。

---

## 5. 配置说明（环境变量）

配置集中在 `app/config.py`。`get_settings()` 含 `lru_cache`，修改 `.env` 后需重启服务。

### 5.1 服务

| 变量 | 说明 |
|------|------|
| `PORT` | HTTP 监听端口，默认 `38421` |
| `APP_API_KEY` | 服务鉴权密钥；留空则不校验 |
| `REDIS_URL` | 设置后策略池使用 Redis；否则用进程内内存 |

### 5.2 LLM

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | 默认前后台共用 |
| `OPENAI_TEMPERATURE` | 默认温度 |
| `FOREGROUND_OPENAI_*` | 前台覆盖 |
| `BACKGROUND_OPENAI_*` | 后台覆盖 |
| `BACKGROUND_MAX_TOKENS` | 后台补全上限 |

### 5.3 DuRecDial（阶段 A+B）

| 变量 | 说明 |
|------|------|
| `DURECDIAL_ENABLE` | 总开关；`false` 时不加载参考剧本与检索证据 |
| `DURECDIAL_STRATEGIES_PATH` | `strategies.json` 路径（阶段 A） |
| `DURECDIAL_KNOWLEDGE_PATH` | `knowledge_rag.jsonl` 路径（阶段 B） |
| `RAG_TOP_K` | 每轮检索注入条数，默认 `3` |

---

## 6. HTTP 接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/` | 无 | 服务信息 |
| GET | `/health` | 无 | 存活探针 |
| GET | `/ready` | 受 `APP_API_KEY` 控制 | 就绪探针 |
| GET | `/docs` | 无 | Swagger |

---

## 7. WebSocket：`/ws/chat`

### 7.1 客户端 -> 服务端

```json
{"type":"user_message","text":"用户输入"}
```

### 7.2 服务端 -> 客户端

| `type` | 字段 | 含义 |
|--------|------|------|
| `session` | `session_id` | 会话建立 |
| `assistant_start` | - | 前台回复开始 |
| `token` | `text` | 流式 token |
| `assistant_done` | - | 前台回复结束 |
| `strategy_updated` | `instruction`, `version` | 后台写入新策略 |
| `error` | `message` | 错误信息 |

> 说明：当前 `scripts/ws_chat.py` 默认**不显示** `strategy_updated` 内容，只保留用户可见对话输出。

---

## 8. 策略池（Redis / 内存）

- Redis 键：`strategy:{session_id}`
- 字段：`instruction`、`version`、`updated_at`
- 无记录时返回默认策略文案（`DEFAULT_INSTRUCTION`）
- Redis 模式默认 TTL：7 天

---

## 9. DuRecDial 阶段 A+B 实现说明

### 阶段 A：参考剧本注入

- 模块：`app/knowledge/strategies_store.py`
- 行为：加载 `strategies.json`，按上下文做粗排+精排，命中后生成 `【DuRecDial 参考剧本】` 注入后台 prompt。

### 阶段 B：RAG 检索注入

- 模块：`app/knowledge/retriever.py`
- 行为：
  - 读取 `knowledge_rag.jsonl` 到内存
  - 轻量分词（英文词 + 中文单字）
  - BM25 计算 top-k
  - 格式化为 `【DuRecDial 检索证据】` 注入后台 prompt
- 预热：`app/main.py` 启动事件调用 `warmup_retriever()`，降低首轮读取延迟。

---

## 10. 本地运行

```bash
cd tot_rec
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./start.sh
```

另开终端：

```bash
./start_ws_chat.sh
```

---

## 11. 运维注意

- `.env` 包含密钥，不应提交到仓库。
- 公网部署建议启用 `APP_API_KEY` + HTTPS/WSS。
- 多实例部署建议配置 `REDIS_URL`，避免策略状态分裂。
- 切换 `.env` 变量后需重启服务。

---

## 12. 文档关系

| 文件 | 内容 |
|------|------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 逻辑架构、数据流、演进方向 |
| [`TECHNICAL.md`](TECHNICAL.md) | 当前实现细节、配置与接口约定 |
