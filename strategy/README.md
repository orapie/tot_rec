# 阶段性策略文档

本目录存放 **tot_rec** 的**分阶段实施规划**（数据接入、RAG、微调路线等），与「产品/系统架构」「代码级技术说明」区分如下：

| 文档 | 位置 | 说明 |
|------|------|------|
| 概念架构（双轨、Redis、LangGraph 设想） | [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) | 偏产品设计与技术选型 |
| 实现与运维（目录、配置、接口、并发） | [`docs/TECHNICAL.md`](../docs/TECHNICAL.md) | 与当前代码一致 |
| DuRecDial 接入阶段规划 | [`DURECDIAL_INTEGRATION.md`](DURECDIAL_INTEGRATION.md) | 阶段 A/B/C 与模块落点 |
| 数据处理步骤（DuRecDial 原始 txt） | [`../data/DuRecDial_STEPS.md`](../data/DuRecDial_STEPS.md) | `data/raw` → `processed` |

后续同类规划文档可继续放在 **`strategy/`**，并在上表补一行索引。
