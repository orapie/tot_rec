"""DuRecDial chat_samples.jsonl 懒加载与前台 few-shot 块生成（阶段 C）。

匹配优先级：
  1. strategy_step 标签匹配（与当前策略指令中关键词对比）
  2. user_input 字符 Jaccard 相似度匹配
取 top-k 条（由 few_shot_max_samples 控制），作为 user/assistant 对注入前台 prompt。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SAMPLES_REL = "data/processed_data/chat_samples.jsonl"
_MAX_TEXT_LEN = 120  # 单条 user_input/bot_response 超此长度时截断，控制 token 消耗

_samples: list[dict[str, Any]] | None = None


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _resolve_path(s: Settings) -> Path | None:
    if not s.few_shot_enable:
        return None
    raw = (s.chat_samples_path or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else _PROJECT_ROOT / p
    return _PROJECT_ROOT / _DEFAULT_SAMPLES_REL


def _ensure_loaded() -> list[dict[str, Any]]:
    global _samples
    if _samples is not None:
        return _samples

    s = get_settings()
    path = _resolve_path(s)
    if path is None or not path.is_file():
        if s.few_shot_enable and path is not None:
            logger.warning("chat_samples file missing: %s", path)
        _samples = []
        return _samples

    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    logger.debug("skip malformed line %d in %s", lineno, path)
                    continue
                if isinstance(obj, dict) and obj.get("user_input") and obj.get("bot_response"):
                    rows.append(obj)
        logger.info("Loaded chat_samples: %d entries from %s", len(rows), path)
    except OSError as e:
        logger.warning("Failed to read chat_samples: %s", e)

    _samples = rows
    return _samples


def _truncate(text: str, max_len: int = _MAX_TEXT_LEN) -> str:
    text = text.replace(" ", "")  # 去掉分词空格（DuRecDial 特有）
    return text[:max_len] + "…" if len(text) > max_len else text


def _char_jaccard(a: str, b: str) -> float:
    sa = set(a.replace(" ", ""))
    sb = set(b.replace(" ", ""))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _extract_keywords(text: str) -> set[str]:
    """从策略指令或用户输入里提取 2+ 字的中文词组作为关键词集合。"""
    return set(re.findall(r"[\u4e00-\u9fa5]{2,}", text))


def _step_score(sample: dict[str, Any], strategy_keywords: set[str]) -> float:
    """step 标签与策略指令关键词的命中比例。"""
    if not strategy_keywords:
        return 0.0
    step = str(sample.get("strategy_step") or "")
    if step in ("", "unknown"):
        return 0.0
    step_kws = _extract_keywords(step)
    if not step_kws:
        return 0.0
    hit = len(strategy_keywords & step_kws)
    return hit / len(strategy_keywords)


def _pick_top_k(
    user_text: str,
    strategy_instruction: str,
    rows: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    strategy_kws = _extract_keywords(strategy_instruction)
    scored: list[tuple[float, dict[str, Any]]] = []

    for sample in rows:
        s_score = _step_score(sample, strategy_kws)
        u_score = _char_jaccard(user_text, sample.get("user_input", ""))
        # 策略标签权重 0.6，用户输入相似度权重 0.4
        total = s_score * 0.6 + u_score * 0.4
        scored.append((total, sample))

    scored.sort(key=lambda x: x[0], reverse=True)
    # 过滤掉完全不相关的（双分均 0）
    selected = [s for sc, s in scored[:top_k * 3] if sc > 0.0][:top_k]
    return selected


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def build_few_shot_messages(
    user_text: str,
    strategy_instruction: str,
) -> list[dict[str, str]]:
    """返回要插入前台 messages 的 few-shot user/assistant 对列表。
    若未启用或无命中，返回空列表。
    """
    s = get_settings()
    if not s.few_shot_enable:
        return []

    rows = _ensure_loaded()
    if not rows:
        return []

    top_k = max(1, min(s.few_shot_max_samples, 3))
    selected = _pick_top_k(user_text, strategy_instruction, rows, top_k)
    if not selected:
        return []

    uids = [r.get("uid", "N/A") for r in selected]
    logger.info("few-shot samples selected: %s", uids)

    messages: list[dict[str, str]] = []
    for sample in selected:
        u = _truncate(sample.get("user_input", ""))
        b = _truncate(sample.get("bot_response", ""))
        if u and b:
            messages.append({"role": "user", "content": u})
            messages.append({"role": "assistant", "content": b})
    return messages


def reload_cache_for_tests() -> None:
    """测试用：清空缓存以便重新加载。"""
    global _samples
    _samples = None
