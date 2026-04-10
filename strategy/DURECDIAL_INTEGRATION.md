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

## 2. 阶段 A：只增强后台（改动最小，建议先做）

### 2.1 配置

在 `app/config.py` 增加可选项，例如：

- `durecdial_strategies_path`：指向 `data/processed_data/strategies.json`
- `durecdial_enable`：布尔开关，关闭时行为与现在完全一致

路径建议走环境变量 / `.env`，避免写死。

### 2.2 加载与匹配

新建模块（示例路径）`app/knowledge/strategies_store.py`：

- 进程内加载 `strategies.json`（启动时或首次使用时）
- 提供接口：根据当前对话上下文（或关键词）返回一段「参考阶段」文本（可先简单关键词 / 与 `situation` 重叠匹配）

### 2.3 接入 navigator

在 `app/background/navigator.py` 中，调用 LLM **之前**将「参考阶段」写入 prompt（如 `【DuRecDial 参考阶段】...`）。

- **不修改** WebSocket 协议
- **不修改** 策略池字段：仍只写入 `instruction`

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

## 4. 阶段 C：前台 few-shot（`chat_samples.jsonl`）

### 4.1 加载

新建 `app/knowledge/chat_samples_store.py`：

- 加载 `chat_samples.jsonl`
- 按 `strategy_step` 或关键词取 1～3 条示例

### 4.2 接入前台

在 `app/foreground/stream_chat.py` 的 `messages` 中，在系统提示之后插入少量 `user` / `assistant` 对话对作为 few-shot，控制总长度。

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
