# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select

from config import settings

logger = logging.getLogger(__name__)
from doubao_client import chat as doubao_chat, chat_with_usage, parse_json_from_text
from doubao_client import DoubaoRateLimitError, DoubaoUnavailableError
from models import RawNews, SelectedNews, get_db_session
from prompts import FILTER_PROMPT_TEMPLATE
from utils import now_beijing_naive


def _first_dict_from_list(lst: list) -> dict:
    for x in lst:
        if isinstance(x, dict):
            return x
        if isinstance(x, list):
            found = _first_dict_from_list(x)
            if found:
                return found
    return {}


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    return obj.get(key, default)


def call_doubao_filter_api(
    title: str,
    content: str,
    token_accumulator: Optional[List[Dict[str, int]]] = None,
    filter_template: Optional[str] = None,
) -> Dict[str, Any]:
    """
    调用豆包筛选接口。
    - DoubaoRateLimitError / DoubaoUnavailableError 直接上抛，由 filter_news 决策。
    - 其他异常：返回 relevance=False 并附 _error，不影响下一条处理。
    """
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在 config 或环境变量中设置")
    default = {"relevance": False, "direction": 0, "impact": 0}
    try:
        tpl = filter_template if filter_template is not None else FILTER_PROMPT_TEMPLATE
        user_text = tpl.format(title=title, content=(content or "")[:8000])
        model_filter = (settings.doubao.model_id_filter or settings.doubao.model_id or "").strip() or None
        if token_accumulator is not None:
            raw_text, usage = chat_with_usage(
                model=model_filter, user_text=user_text, timeout=30, max_retries=4
            )
            token_accumulator.append(usage)
        else:
            raw_text = doubao_chat(model=model_filter, user_text=user_text, timeout=30)
        data = parse_json_from_text(raw_text)
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

        relevance = _bool(
            _safe_get(data, "relevance")
            or _safe_get(data, "相关")
            or _safe_get(data, "is_relevant")
            or _safe_get(data, "relevant")
        )
        direction = _int(_safe_get(data, "direction") or _safe_get(data, "方向") or _safe_get(data, "direction_score"))
        impact = _int(_safe_get(data, "impact") or _safe_get(data, "影响程度") or _safe_get(data, "impact_level"))
        return {"relevance": relevance, "direction": direction, "impact": impact}
    except (DoubaoRateLimitError, DoubaoUnavailableError):
        raise
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
    对 relevance=True 的写入 selected_news。

    v2 改动：
    - DoubaoUnavailableError（404/403）：立即停止本轮筛选并上抛，通知调用方记录告警。
    - DoubaoRateLimitError（429）：由 doubao_client 内部退避重试，超重试上限后上抛。
    - 其他零散异常：仍用原有"连续相同错误 ≥2 次熔断"逻辑。
    - 修复：无论是否有相关新闻，只要有条目被处理，均 commit relevance 字段更新。
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
        last_misc_error: Optional[str] = None
        same_misc_error_count = 0
        processed_count = 0

        for item in raw_items:
            try:
                result = call_doubao_filter_api(
                    item.title, item.content, token_accumulator=token_accumulator
                )
            except DoubaoUnavailableError:
                raise
            except DoubaoRateLimitError:
                raise
            except Exception as e:
                err = str(e)
                same_misc_error_count = same_misc_error_count + 1 if err == last_misc_error else 1
                last_misc_error = err
                if same_misc_error_count >= 2:
                    raise RuntimeError(
                        f"筛选步骤相同报错连续出现 2 次，停止本轮以节省 tokens: {last_misc_error}"
                    )
                continue

            err = result.pop("_error", None)
            if err is not None:
                same_misc_error_count = same_misc_error_count + 1 if err == last_misc_error else 1
                last_misc_error = err
                if same_misc_error_count >= 2:
                    raise RuntimeError(
                        f"筛选步骤相同报错连续出现 2 次，停止本轮以节省 tokens: {last_misc_error}"
                    )

            is_relevant = bool(result.get("relevance"))
            item.relevance = is_relevant
            processed_count += 1

            if is_relevant:
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

        # 修复：只要处理过任意条目，就提交（包含 relevance=False 的更新，避免下轮重复处理）
        if processed_count > 0:
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
