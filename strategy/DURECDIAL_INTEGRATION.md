# DuRecDial 转换产物接入本项目 — 修改策略

本文说明如何将 `convert.py` 生成的文件接入当前 **tot_rec** 服务（双 Agent + 策略池）。不展开 JSON 字段细节，只列**项目应如何改**。

---

## 1. 三个产物与用途

| 文件 | 用途 |
|------|------|
| `strategies.json` | **后台** `navigator`：参考阶段 / 剧本模板，拼进 LLM 提示 |
| `knowledge_rag.jsonl` | **检索层**：BM25 或向量检索后，把 top-k 证据给后台或前台 |
| `chat_samples.jsonl` | **前台** `stream_chat`：few-shot 话术示例；或仅离线微调（运行时可选不接） |

---

## 2. 阶段 A：只增强后台（已实现）

### 2.1 配置

- `app/config.py`：`durecdial_enable`、`durecdial_strategies_path`
- `.env`：`DURECDIAL_ENABLE`、`DURECDIAL_STRATEGIES_PATH`（见 `.env.example`）

### 2.2 加载与匹配

- `app/knowledge/strategies_store.py`：首次需要时加载 JSON；按「最近对话 + 当前用户句」与条目的 **situation 粗排 → 全文精排** 选一条，低于阈值则不注入。

### 2.3 接入 navigator

- `app/background/navigator.py`：在调用 LLM 前拼接 `【DuRecDial 参考剧本】…` 与对话摘录。

WebSocket 与策略池字段未变。

---

## 3. 阶段 B：接上 RAG（`knowledge_rag.jsonl`）

### 3.1 配置

在 `app/config.py` 增加：

- `durecdial_knowledge_path`：指向 `knowledge_rag.jsonl`
- `rag_top_k`：检索条数

### 3.2 检索模块

新建 `app/knowledge/retriever.py`：

- 启动时读入 `knowledge_rag.jsonl` 到内存
- 使用 **BM25**（依赖少）或后续替换为向量库
- 输入：`history` +当前 `user_text` 拼成 query；输出：top-k 条文本

### 3.3 注入位置

- **优先**：`navigator.py` 中注入检索结果，供策略推演使用
- **可选**：`stream_chat.py` 中同样注入，使前台回复带依据（注意 token 上限）

---

## 4. 阶段 C：前台 few-shot（`chat_samples.jsonl`）✅ 已实现

### 4.1 配置

- `app/config.py`：`few_shot_enable`、`chat_samples_path`、`few_shot_max_samples`
- `.env`：`FEW_SHOT_ENABLE=true`、`CHAT_SAMPLES_PATH`（可选）、`FEW_SHOT_MAX_SAMPLES`（默认 2）

### 4.2 加载

`app/knowledge/chat_samples_store.py`：

- 懒加载 `chat_samples.jsonl`
- 匹配优先级：`strategy_step` 标签关键词（权重 0.6）→ 用户输入字符 Jaccard（权重 0.4）
- 取 top-k 条（超 3 条自动截断），低于最低阈值时不注入
- 日志中输出命中的 `uid`，便于追踪

### 4.3 接入前台

`app/foreground/stream_chat.py`：

- 系统提示之后、历史对话之前插入 few-shot `user/assistant` 对
- 每条文本超 120 字符自动截断（去除 DuRecDial 分词空格），控制 token 消耗
- `few_shot_enable=false` 时完全跳过，保持原有行为

---

## 5. 工程注意

- **路径**：一律由配置指定，便于本地与部署环境切换
- **大文件**：可采用懒加载或后台预加载，避免阻塞首个请求
- **`get_settings()`**：带缓存，改 `.env` 后需**重启服务**
- **开关**：`durecdial_enable=false` 时保持当前线上行为，便于 A/B

---

## 6. 推荐落地顺序

1. **阶段 A**：配置 + `strategies_store` + `navigator` prompt 注入  
2. **阶段 B**：`retriever` + `navigator`（必要时前台）  
3. **阶段 C**：`chat_samples` few-shot 或离线微调后再接运行时

---

## 7. 与现有文档的关系

- 运行时与接口约定见 [`../docs/TECHNICAL.md`](../docs/TECHNICAL.md)
- 数据处理步骤见 [`../data/DuRecDial_STEPS.md`](../data/DuRecDial_STEPS.md)

---

*文档随实现迭代时可在此补充：实际模块名、环境变量名、检索算法选型。*
