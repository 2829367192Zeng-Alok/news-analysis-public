# -*- coding: utf-8 -*-
"""分析结果推送共用文案（飞书 / QQ 等）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import NewsAnalysisDetail


def _direction_label(direction: int | None) -> str:
    if direction is None:
        return "未给出"
    if direction > 0:
        return "利多黄金"
    if direction < 0:
        return "利空黄金"
    return "方向不确定"


def _impact_label(impact: int | None) -> str:
    if impact is None or impact == 0:
        return "未给出"
    return f"影响强度 {int(impact)}/5"


def _truncate(text: str | None, max_len: int) -> str:
    if not text:
        return "（无）"
    t = text.strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def format_analysis_message(
    detail: NewsAnalysisDetail,
    *,
    web_base_url: str,
    conclusion_max_len: int,
) -> str:
    """标题 + 方向/影响 + 结论截断 + Web 链接。"""
    base = web_base_url.rstrip("/")
    link = f"{base}/"
    title = (detail.title or "").strip() or "（无标题）"
    direction = _direction_label(detail.direction)
    impact = _impact_label(detail.impact)
    conclusion = _truncate(detail.conclusion, conclusion_max_len)
    lines = [
        f"【资讯】{title}",
        f"方向：{direction}｜{impact}",
        f"结论：{conclusion}",
        f"详情：{link}",
    ]
    return "\n".join(lines)
