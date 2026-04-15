"""DuRecDial knowledge_rag.jsonl 内存检索（阶段 B）。"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_KNOWLEDGE_REL = "data/processed_data/knowledge_rag.jsonl"
_MAX_EVIDENCE_CHARS = 220


class _Index:
    def __init__(self, docs: list[str], tokens_per_doc: list[list[str]], dfs: Counter[str]) -> None:
        self.docs = docs
        self.tokens_per_doc = tokens_per_doc
        self.dfs = dfs
        self.doc_lens = [len(x) for x in tokens_per_doc]
        self.avgdl = sum(self.doc_lens) / len(self.doc_lens) if self.doc_lens else 0.0
        self.n_docs = len(docs)


_index_cache: _Index | None = None


def _resolve_knowledge_path(s: Settings) -> Path | None:
    if not s.durecdial_enable:
        return None
    raw = (s.durecdial_knowledge_path or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else _PROJECT_ROOT / p
    return _PROJECT_ROOT / _DEFAULT_KNOWLEDGE_REL


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    # 英文按词切分；中文按字切分，避免依赖额外分词库。
    return re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", text.lower())


def _compact_text(s: str, limit: int = _MAX_EVIDENCE_CHARS) -> str:
    t = " ".join(s.split())
    if len(t) <= limit:
        return t
    return f"{t[:limit]}..."


def _extract_doc_text(row: dict[str, Any]) -> str:
    # 优先常见字段，保证检索主体更稳定；其余字段作为兜底补充。
    preferred = [
        "text",
        "content",
        "knowledge",
        "passage",
        "evidence",
        "response",
        "goal",
        "topic",
    ]
    parts: list[str] = []
    for key in preferred:
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())

    if not parts:
        for v in row.values():
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, str) and x.strip():
                        parts.append(x.strip())
            elif isinstance(v, dict):
                for x in v.values():
                    if isinstance(x, str) and x.strip():
                        parts.append(x.strip())
    return " ".join(parts)


def _load_index() -> _Index:
    s = get_settings()
    path = _resolve_knowledge_path(s)
    if path is None or not path.is_file():
        if s.durecdial_enable and path is not None:
            logger.warning("DuRecDial knowledge file missing: %s", path)
        return _Index([], [], Counter())

    docs: list[str] = []
    tokens_per_doc: list[list[str]] = []
    dfs: Counter[str] = Counter()

    try:
        with path.open(encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skip invalid JSONL line %d in %s", line_no, path)
                    continue
                if not isinstance(row, dict):
                    continue
                text = _extract_doc_text(row).strip()
                if not text:
                    continue
                tokens = _tokenize(text)
                if not tokens:
                    continue
                docs.append(text)
                tokens_per_doc.append(tokens)
                for token in set(tokens):
                    dfs[token] += 1
    except OSError as e:
        logger.warning("Failed to read DuRecDial knowledge file: %s", e)
        return _Index([], [], Counter())

    logger.info("Loaded DuRecDial knowledge: %d entries from %s", len(docs), path)
    return _Index(docs, tokens_per_doc, dfs)


def _ensure_index() -> _Index:
    global _index_cache
    if _index_cache is None:
        _index_cache = _load_index()
    return _index_cache


def _build_query(history: list[dict[str, str]], user_text: str, max_turns: int = 12) -> str:
    parts: list[str] = []
    for m in history[-max_turns:]:
        parts.append(m.get("content", ""))
    parts.append(user_text)
    return " ".join(parts)


def _bm25_scores(index: _Index, query_tokens: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    if not query_tokens or index.n_docs == 0:
        return [0.0] * index.n_docs

    query_tf = Counter(query_tokens)
    scores: list[float] = [0.0] * index.n_docs
    n_docs = index.n_docs
    avgdl = index.avgdl or 1.0

    for i, doc_tokens in enumerate(index.tokens_per_doc):
        tf = Counter(doc_tokens)
        dl = index.doc_lens[i] or 1
        score = 0.0
        for term, qf in query_tf.items():
            if term not in tf:
                continue
            df = index.dfs.get(term, 0)
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            denom = tf[term] + k1 * (1 - b + b * dl / avgdl)
            score += idf * (tf[term] * (k1 + 1)) / denom * qf
        scores[i] = score
    return scores


def retrieve_knowledge_texts(history: list[dict[str, str]], user_text: str, top_k: int | None = None) -> list[str]:
    s = get_settings()
    if not s.durecdial_enable:
        return []

    index = _ensure_index()
    if not index.docs:
        return []

    k = int(top_k if top_k is not None else s.rag_top_k)
    k = max(1, min(k, 20))

    query = _build_query(history, user_text)
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    scores = _bm25_scores(index, q_tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    out: list[str] = []
    for idx, score in ranked[:k]:
        if score <= 0:
            continue
        out.append(_compact_text(index.docs[idx]))
    return out


def build_knowledge_for_navigator(history: list[dict[str, str]], user_text: str) -> str:
    rows = retrieve_knowledge_texts(history, user_text)
    if not rows:
        return ""
    lines = ["【DuRecDial 检索证据】"]
    for i, text in enumerate(rows, 1):
        lines.append(f"{i}. {text}")
    return "\n".join(lines)


def warmup_retriever() -> None:
    """服务启动时调用，预热索引，减少首轮请求延迟。"""
    _ensure_index()


def reload_retriever_cache_for_tests() -> None:
    global _index_cache
    _index_cache = None
