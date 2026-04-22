# 数据格式规范

本文说明 **tot_rec** 当前各阶段所需的清洗数据格式，以及如何将任意原始数据转换为系统可用格式。

---

## 目录结构

```text
data/
├── raw/                    # 原始数据（不改动，保留可追溯）
│   └── *.txt / *.json ...
├── processed_data/
│   ├── strategies.json     # 阶段 A：后台导航参考（必须）
│   ├── knowledge_rag.jsonl # 阶段 B：RAG 检索知识库（可选）
│   └── chat_samples.jsonl  # 阶段 C：前台 few-shot 话术（可选）
└── DuRecDial_STEPS.md
```

---

## 一、阶段 A —— strategies.json（后台导航）

### 用途

系统启动后加载到内存，每轮对话中后台 Agent 用「当前上下文」与每条样本做字符相似度匹配，命中后把参考剧本注入 LLM prompt，提升策略质量。

### 文件格式

根类型为 **JSON 数组**，每个元素为一个 JSON 对象：

```json
[
  {
    "situation": "场景描述文字",
    "steps": [
      "阶段一描述",
      "阶段二描述",
      "阶段三描述"
    ],
    "uid": "strategy_xxxxxxxxxxxxxxxx"
  }
]
```

### 字段说明

| 字段 | 类型 | 必须 | 含义 |
|------|------|------|------|
| `situation` | string | **必须** | 对话发生的场景、时间、背景。系统匹配时主要用此字段做粗排。 |
| `steps` | string[] | **必须** | 有序阶段列表，描述本次对话应经历的话题路径与目标。 |
| `uid` | string | 推荐 | 稳定唯一标识，由 `scripts/assign_uids.py` 自动生成，用于追踪命中。可留空，留空则无法在终端显示命中记录。 |

### 匹配规则（代码层）

1. 用最近 12 轮对话内容 + 当前用户输入拼成 `context`
2. 先按 `situation` 字段做字符 Jaccard 粗排，取 top-64 候选
3. 再对候选做 `situation + steps 全文` 精排，取得分最高项
4. 得分 < `0.02` 时不注入（视为无匹配）

### 最小可用样本

```json
[
  {
    "situation": "用户想看一部悬疑电影",
    "steps": [
      "确认喜欢的悬疑子类型（犯罪/心理/烧脑）",
      "用评论作为推荐理由给出1-2部具体片名",
      "确认用户是否接受推荐"
    ]
  }
]
```

---

## 二、阶段 B —— knowledge_rag.jsonl（RAG 检索）

### 用途

将任意知识文本拆成细粒度条目，通过 BM25 或向量检索取 top-k 注入后台（或前台）prompt，提供事实依据。

> 阶段 B 功能当前已部分接入（`app/knowledge/retriever.py`），可按需开启。

### 文件格式

**JSONL（每行一条 JSON 对象）**：

```jsonl
{"text": "知识文本内容", "metadata": {"category": "分类标签", "source": "来源标识"}, "uid": "knowledge_xxxxxxxxxxxxxxxx"}
{"text": "另一条知识", "metadata": {"category": "人物", "source": "百科"}, "uid": "knowledge_xxxxxxxxxxxxxxxx"}
```

### 字段说明

| 字段 | 类型 | 必须 | 含义 |
|------|------|------|------|
| `text` | string | **必须** | 可被检索与注入的知识文本，一般不超过 300 字。过长应拆分。 |
| `metadata` | object | 可选 | 任意附加信息，`category`/`source` 仅为惯例，字段名可自定义。 |
| `uid` | string | 推荐 | 条目唯一标识，由 `scripts/assign_uids.py` 自动生成。 |

### 原始数据转换示例

**输入**（百科段落）：

```
《新边缘人》是1990年香港电影，由张国荣主演，讲述...
```

**输出**：

```jsonl
{"text": "《新边缘人》是1990年香港电影，由张国荣主演，讲述...", "metadata": {"category": "电影", "source": "百科"}}
```

---

## 三、阶段 C —— chat_samples.jsonl（前台 few-shot）

### 用途

向前台 Agent 提供真实对话示例，按策略阶段或关键词取 1-3 条注入 prompt，引导模型"照着说"。

> 阶段 C 为可选接入，当前尚未接入运行时（适合后续微调或 prompt 增强）。

### 文件格式

**JSONL（每行一条 JSON 对象）**：

```jsonl
{"strategy_step": "电影推荐", "user_input": "用户输入文字", "bot_response": "机器人回复文字", "uid": "chat_xxxxxxxxxxxxxxxx"}
```

### 字段说明

| 字段 | 类型 | 必须 | 含义 |
|------|------|------|------|
| `strategy_step` | string | 推荐 | 当前轮次对应的策略阶段标签，用于按阶段筛选样本。可自定义值，如 `"电影推荐"`、`"确认偏好"` 等。 |
| `user_input` | string | **必须** | 该轮用户输入。 |
| `bot_response` | string | **必须** | 对应的优质机器人回复，将作为 few-shot 示例。 |
| `uid` | string | 推荐 | 由 `scripts/assign_uids.py` 自动生成。 |

---

## 四、数据清洗通用步骤

任何原始数据转换为上述格式时，建议按以下顺序操作：

### Step 1：放置原始文件

```text
data/raw/your_dataset.txt  （或 .json / .csv 等）
```

### Step 2：编写转换脚本

参考 `convert.py`（已处理 DuRecDial）。核心思路：

- 遍历原始数据每一条记录
- 提取 `situation`（场景背景）→ 写入 `strategies.json`
- 提取知识性文本片段 → 写入 `knowledge_rag.jsonl`
- 提取高质量对话对 → 写入 `chat_samples.jsonl`
- 写出到 `data/processed_data/`

### Step 3：分配 UID

```bash
python scripts/assign_uids.py --inplace
```

或先预览再覆盖：

```bash
python scripts/assign_uids.py          # 生成 *.uid.* 预览文件
python scripts/assign_uids.py --inplace  # 确认后原地写回
```

### Step 4：质检

```bash
# 查看条目数
python -c "
import json
data = json.load(open('data/processed_data/strategies.json'))
print('strategies:', len(data))
has_uid = sum(1 for r in data if r.get('uid'))
print('有uid:', has_uid)
no_situation = sum(1 for r in data if not r.get('situation'))
print('缺situation:', no_situation)
"
```

---

## 五、不同类型原始数据的处理建议

| 原始数据类型 | 目标文件 | 关键提取点 |
|-------------|----------|------------|
| 对话类数据集（有目标链路） | `strategies.json` | 场景 → `situation`；话题阶段 → `steps` |
| 百科 / 评论 / 简介 | `knowledge_rag.jsonl` | 每段独立文本 → `text`，控制长度 ≤ 300 字 |
| 已有优质对话记录 | `chat_samples.jsonl` | 用户句 → `user_input`；回复 → `bot_response` |
| 结构完全不同 | 自建 store 模块 | 见 `app/knowledge/strategies_store.py` 作为参考新建 |

---

## 六、字段约束一览

| 文件 | 必须字段 | 推荐字段 | 系统使用方式 |
|------|----------|----------|-------------|
| `strategies.json` | `situation`、`steps` | `uid` | 字符 Jaccard 匹配后注入后台 prompt |
| `knowledge_rag.jsonl` | `text` | `metadata`、`uid` | BM25/向量检索后注入 |
| `chat_samples.jsonl` | `user_input`、`bot_response` | `strategy_step`、`uid` | 前台 few-shot 示例 |

---

## 相关文档

- `data/DuRecDial_STEPS.md`：DuRecDial 专项处理步骤
- `strategy/DURECDIAL_INTEGRATION.md`：分阶段接入策略
- `docs/TECHNICAL.md`：系统运行时与配置
