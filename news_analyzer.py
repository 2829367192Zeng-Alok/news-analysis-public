# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from config import settings

logger = logging.getLogger(__name__)
from doubao_client import chat_with_usage, parse_json_from_text
from models import SelectedNews, NewsAnalysisDetail, get_db_session
from prompts import ANALYZE_PROMPT_TEMPLATE
from utils import now_beijing_naive


def _norm_list(v: Any) -> List[str] | None:
    """将 keyword/Reference 转为 list 或 None。"""
    if v is None:
        return None
    if isinstance(v, list):
        return [str(x) for x in v]
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        return [s.strip() for s in v.replace("，", ",").split(",") if s.strip()]
    return None


def _norm_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _norm_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def call_doubao_analyze_api(
    title: str, content: str, token_accumulator: Optional[List[Dict[str, int]]] = None
) -> Dict[str, Any]:
    """
    调用豆包 Ark API，使用详细分析提示词，返回解析后的 32 字段字典。
    若传入 token_accumulator，本次调用的 token 用量会 append 到该列表。
    """
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在 config 或环境变量中设置")

    # 详细分析提示长、输出字段多，单次请求可能较慢，超时设为 240 秒
    analyze_timeout = 240
    user_text = ANALYZE_PROMPT_TEMPLATE.format(
        title=title,
        content=(content or "")[:12000],
    )
    # 步骤三不重试：超时即抛异常，由上层 continue 下一条
    model_analyze = (settings.doubao.model_id_analyze or settings.doubao.model_id or "").strip() or None
    raw_text, usage = chat_with_usage(
        model=model_analyze,
        user_text=user_text,
        timeout=analyze_timeout,
        max_retries=0,
    )
    if token_accumulator is not None:
        token_accumulator.append(usage)
    return parse_json_from_text(raw_text)


def analyze_news(
    limit: int = 20, token_accumulator: Optional[List[Dict[str, int]]] = None
) -> List[NewsAnalysisDetail]:
    """
    对 selected_news 中尚未写入 news_analysis_detail 的新闻进行详细分析。
    若传入 token_accumulator，每次 API 调用的 token 用量会 append 到该列表。
    """
    session = get_db_session()
    try:
        subq = select(NewsAnalysisDetail.content_hash).subquery()
        q = (
            select(SelectedNews)
            .where(~SelectedNews.content_hash.in_(select(subq.c.content_hash)))
            .order_by(SelectedNews.news_datetime.desc())
            .limit(limit)
        )
        selected_items: List[SelectedNews] = [row[0] for row in session.execute(q).all()]
        if not selected_items:
            return []

        new_details: List[NewsAnalysisDetail] = []
        last_error: Optional[str] = None
        same_error_count = 0
        for item in selected_items:
            try:
                result = call_doubao_analyze_api(
                    item.title, item.content, token_accumulator=token_accumulator
                )
            except Exception as e:
                err = str(e)
                same_error_count = same_error_count + 1 if err == last_error else 1
                last_error = err
                logger.warning("详细分析 API 单条异常: %s", e)
                if same_error_count >= 2:
                    raise RuntimeError(
                        f"相同报错连续出现 2 次，停止运行以节省 tokens: {last_error}"
                    )
                continue

            detail = NewsAnalysisDetail(
                title=item.title,
                content=item.content,
                news_datetime=item.news_datetime,
                source=item.source,
                create_time=now_beijing_naive(),
                relevance=bool(result.get("relevance", item.relevance)),
                direction=_norm_int(result.get("direction"), item.direction or 0),
                impact=_norm_int(result.get("impact"), item.impact or 0),
                interest_direction=_norm_int(result.get("interest_direction")),
                interest_impact=_norm_int(result.get("interest_impact")),
                dollar_direction=_norm_int(result.get("dollar_direction")),
                dollar_impact=_norm_int(result.get("dollar_impact")),
                warrisk_direction=_norm_int(result.get("warrisk_direction")),
                warrisk_impact=_norm_int(result.get("warrisk_impact")),
                liquidity_direction=_norm_int(result.get("liquidity_direction")),
                liquidity_impact=_norm_int(result.get("liquidity_impact")),
                emotion_direction=_norm_int(result.get("emotion_direction")),
                emotion_impact=_norm_int(result.get("emotion_impact")),
                keyword=_norm_list(result.get("keyword")),
                Reference=_norm_list(result.get("Reference")),
                interest=_norm_str(result.get("interest")),
                dollar=_norm_str(result.get("dollar")),
                warrisk=_norm_str(result.get("warrisk")),
                liquidity=_norm_str(result.get("liquidity")),
                emotion=_norm_str(result.get("emotion")),
                shorttime=_norm_str(result.get("shorttime")),
                midtime=_norm_str(result.get("midtime")),
                longtime=_norm_str(result.get("longtime")),
                insight=_norm_str(result.get("insight")),
                conclusion=_norm_str(result.get("conclusion")),
                content_hash=item.content_hash,
            )
            session.add(detail)
            new_details.append(detail)

        if new_details:
            session.commit()

        return new_details
    except Exception as e:
        session.rollback()
        logger.exception("详细分析写入 news_analysis_detail 失败: %s", e)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    items = analyze_news()
    print(f"新增 news_analysis_detail 记录数: {len(items)}")
