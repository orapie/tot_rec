"""DuRecDial strategies.json 懒加载与导航参考块生成（阶段 A）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_STRATEGIES_REL = "data/processed_data/strategies.json"

_strategies_rows: list[dict[str, Any]] | None = None


def _resolve_strategies_path(s: Settings) -> Path | None:
    if not s.durecdial_enable:
        return None
    raw = (s.durecdial_strategies_path or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else _PROJECT_ROOT / p
    return _PROJECT_ROOT / _DEFAULT_STRATEGIES_REL


def _ensure_loaded() -> list[dict[str, Any]]:
    global _strategies_rows
    if _strategies_rows is not None:
        return _strategies_rows

    s = get_settings()
    path = _resolve_strategies_path(s)
    if path is None or not path.is_file():
        if s.durecdial_enable and path is not None:
            logger.warning("DuRecDial strategies file missing: %s", path)
        _strategies_rows = []
        return _strategies_rows

    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.warning("DuRecDial strategies JSON root must be a list, got %s", type(data))
            _strategies_rows = []
        else:
            _strategies_rows = [x for x in data if isinstance(x, dict)]
            logger.info(
                "Loaded DuRecDial strategies: %d entries from %s",
                len(_strategies_rows),
                path,
            )
    except OSError as e:
        logger.warning("Failed to read DuRecDial strategies: %s", e)
        _strategies_rows = []
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in strategies file: %s", e)
        _strategies_rows = []

    return _strategies_rows


def _build_context_blob(history: list[dict[str, str]], user_text: str, max_turns: int = 12) -> str:
    parts: list[str] = []
    for m in history[-max_turns:]:
        parts.append(m.get("content", ""))
    parts.append(user_text)
    return " ".join(parts)


def _char_jaccard(a: str, b: str) -> float:
    sa = set(a.replace(" ", ""))
    sb = set(b.replace(" ", ""))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _item_blob(item: dict[str, Any]) -> str:
    sit = str(item.get("situation", "") or "")
    steps = item.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    step_text = " ".join(str(s) for s in steps if s)
    return f"{sit} {step_text}"


def _pick_best_item(
    ctx: str, rows: list[dict[str, Any]], situation_top_n: int = 64
) -> tuple[dict[str, Any] | None, float]:
    if not ctx.strip() or not rows:
        return None, 0.0
    # 先按 situation 粗排，再对全文精排，避免每条都拼接长 steps
    scored_sit: list[tuple[float, dict[str, Any]]] = []
    for item in rows:
        sit = str(item.get("situation", "") or "")
        scored_sit.append((_char_jaccard(ctx, sit), item))
    scored_sit.sort(key=lambda x: x[0], reverse=True)
    candidates = [it for _, it in scored_sit[:situation_top_n]]

    best: dict[str, Any] | None = None
    best_score = 0.0
    for item in candidates:
        blob = _item_blob(item)
        score = _char_jaccard(ctx, blob)
        if score > best_score:
            best_score = score
            best = item
    if best is None or best_score < 0.02:
        return None, best_score
    return best, best_score


def _format_reference(item: dict[str, Any], max_steps: int = 8) -> str:
    sit = str(item.get("situation", "") or "").strip()
    steps = item.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    lines = ["【DuRecDial 参考剧本】", f"情境：{sit}", "阶段概要："]
    for i, st in enumerate(steps[:max_steps], 1):
        lines.append(f"{i}. {str(st).strip()}")
    if len(steps) > max_steps:
        lines.append(f"…（共 {len(steps)} 阶段，此处截断）")
    return "\n".join(lines)


def pick_reference_for_navigator(
    history: list[dict[str, str]],
    user_text: str,
) -> tuple[str, str | None]:
    """返回 (参考文本, reference_uid)。未命中时为 ("", None)。"""
    s = get_settings()
    if not s.durecdial_enable:
        return "", None

    rows = _ensure_loaded()
    if not rows:
        return "", None

    ctx = _build_context_blob(history, user_text)
    item, score = _pick_best_item(ctx, rows)
    if item is None:
        logger.debug("DuRecDial reference miss")
        return "", None

    ref_uid = str(item.get("uid", "") or "").strip() or None
    logger.info("DuRecDial reference hit: uid=%s score=%.4f", ref_uid or "N/A", score)
    return _format_reference(item), ref_uid


def build_reference_for_navigator(
    history: list[dict[str, str]],
    user_text: str,
) -> str:
    """兼容旧调用：仅返回参考文本。"""
    ref, _ = pick_reference_for_navigator(history, user_text)
    return ref


def reload_strategies_cache_for_tests() -> None:
    """测试用：清空缓存以便重新加载。"""
    global _strategies_rows
    _strategies_rows = None
