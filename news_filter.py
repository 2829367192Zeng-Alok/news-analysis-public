# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select

from config import settings

logger = logging.getLogger(__name__)
from doubao_client import chat as doubao_chat, chat_with_usage, parse_json_from_text
from models import RawNews, SelectedNews, get_db_session
from prompts import FILTER_PROMPT_TEMPLATE
from utils import now_beijing_naive


def _first_dict_from_list(lst: list) -> dict:
    """从可能嵌套的列表中取出第一个 dict，用于兼容 API 返回 list 或嵌套结构。"""
    for x in lst:
        if isinstance(x, dict):
            return x
        if isinstance(x, list):
            found = _first_dict_from_list(x)
            if found:
                return found
    return {}


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """仅当 obj 为 dict 时调用 .get，否则返回 default，避免对 list 等调用 .get 报错。"""
    if not isinstance(obj, dict):
        return default
    return obj.get(key, default)


def call_doubao_filter_api(
    title: str, content: str, token_accumulator: Optional[List[Dict[str, int]]] = None
) -> Dict[str, Any]:
    """
    调用豆包 Ark API，使用筛选提示词，返回 relevance, direction, impact。
    若传入 token_accumulator（list），每次调用的 token 用量会 append 到该列表。
    任何异常均不向外抛出，返回 relevance=False, direction=0, impact=0。
    """
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在 config 或环境变量中设置")
    default = {"relevance": False, "direction": 0, "impact": 0}
    try:
        user_text = FILTER_PROMPT_TEMPLATE.format(title=title, content=(content or "")[:8000])
        model_filter = (settings.doubao.model_id_filter or settings.doubao.model_id or "").strip() or None
        if token_accumulator is not None:
            raw_text, usage = chat_with_usage(
                model=model_filter, user_text=user_text, timeout=30
            )
            token_accumulator.append(usage)
        else:
            raw_text = doubao_chat(model=model_filter, user_text=user_text, timeout=30)
        data = parse_json_from_text(raw_text)
        # 确保得到 dict：兼容根为 list、嵌套 list、或非 dict 的情况
        if not isinstance(data, dict):
            data = _first_dict_from_list(data) if isinstance(data, list) else {}
        if not isinstance(data, dict):
            data = {}

        def _bool(v) -> bool:
            if v is None:
                return False
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("true", "1", "是", "yes", "相关")

        def _int(v, default_val: int = 0) -> int:
            try:
                return int(v) if v is not None else default_val
            except (TypeError, ValueError):
                return default_val

        # 使用 _safe_get 避免 data 因解析异常仍为 list 时调用 .get 报错
        relevance = _bool(
            _safe_get(data, "relevance")
            or _safe_get(data, "相关")
            or _safe_get(data, "is_relevant")
            or _safe_get(data, "relevant")
        )
        direction = _int(
            _safe_get(data, "direction")
            or _safe_get(data, "方向")
            or _safe_get(data, "direction_score")
        )
        impact = _int(
            _safe_get(data, "impact")
            or _safe_get(data, "影响程度")
            or _safe_get(data, "impact_level")
        )
        return {"relevance": relevance, "direction": direction, "impact": impact}
    except Exception as e:
        logger.warning("筛选 API 单条异常: %s", e)
        return {**default, "_error": str(e)}


def filter_news(
    limit: int = 50,
    token_accumulator: Optional[List[Dict[str, int]]] = None,
    only_content_hashes: Optional[Set[str]] = None,
) -> List[SelectedNews]:
    """
    从 raw_news 中找出尚未筛选的新闻，调用豆包筛选接口，
    对 relevance=True 的新闻写入 selected_news 表。
    若传入 token_accumulator，每次 API 调用的 token 用量会 append 到该列表。
    若传入 only_content_hashes（非空），仅处理 content_hash 在该集合内的 raw_news（用于只筛本批采集的新闻）。
    """
    session = get_db_session()
    try:
        q = (
            select(RawNews)
            .where(RawNews.relevance.is_(None))
            .order_by(RawNews.news_datetime.desc())
            .limit(limit)
        )
        if only_content_hashes:
            q = q.where(RawNews.content_hash.in_(only_content_hashes))
        raw_items: List[RawNews] = [row[0] for row in session.execute(q).all()]
        if not raw_items:
            return []

        new_selected: List[SelectedNews] = []
        last_error: Optional[str] = None
        same_error_count = 0
        for item in raw_items:
            result = call_doubao_filter_api(
                item.title, item.content, token_accumulator=token_accumulator
            )
            err = result.pop("_error", None)
            if err is not None:
                same_error_count = same_error_count + 1 if err == last_error else 1
                last_error = err
                if same_error_count >= 2:
                    raise RuntimeError(
                        f"相同报错连续出现 2 次，停止运行以节省 tokens: {last_error}"
                    )
            is_relevant = bool(result.get("relevance"))
            item.relevance = is_relevant
            if not is_relevant:
                continue

            sn = SelectedNews(
                title=item.title,
                content=item.content,
                news_datetime=item.news_datetime,
                source=item.source,
                create_time=now_beijing_naive(),
                relevance=is_relevant,
                direction=result.get("direction"),
                impact=result.get("impact"),
                content_hash=item.content_hash,
            )
            session.add(sn)
            new_selected.append(sn)

        if new_selected:
            session.commit()

        return new_selected
    except Exception as e:
        session.rollback()
        logger.exception("筛选写入 selected_news 失败: %s", e)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    items = filter_news()
    print(f"新增 selected_news 记录数: {len(items)}")
