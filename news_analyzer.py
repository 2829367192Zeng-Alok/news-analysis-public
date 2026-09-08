# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select

from config import settings

logger = logging.getLogger(__name__)
from doubao_client import chat_with_usage, parse_json_from_text
from doubao_client import DoubaoRateLimitError, DoubaoUnavailableError
from models import SelectedNews, NewsAnalysisDetail, get_db_session
from prompts import ANALYZE_PROMPT_TEMPLATE
from utils import now_beijing_naive


def _load_v2_prompts():
    """按开关加载 v2 提示词与宏观基线 System Prompt；未开 v2 返回 (None, None)。"""
    if not settings.doubao.use_prompts_v2:
        return None, None
    import prompts_new
    from macro_baseline import load_macro_baseline

    baseline = load_macro_baseline()
    system_prompt = prompts_new.format_system_prompt(baseline)
    return prompts_new.ANALYZE_PROMPT_TEMPLATE, system_prompt


def _norm_list(v: Any) -> List[str] | None:
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
    title: str,
    content: str,
    token_accumulator: Optional[List[Dict[str, int]]] = None,
    analyze_template: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """
    调用豆包详细分析接口。
    DoubaoRateLimitError / DoubaoUnavailableError 直接上抛。
    """
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在 config 或环境变量中设置")

    analyze_timeout = 240
    v2_template, v2_system = _load_v2_prompts()
    if analyze_template is not None:
        tpl = analyze_template
    else:
        tpl = v2_template if v2_template is not None else ANALYZE_PROMPT_TEMPLATE
    if system_prompt is None and settings.doubao.use_prompts_v2:
        system_prompt = v2_system
    user_text = tpl.format(title=title, content=(content or "")[:12000])
    model_analyze = (settings.doubao.model_id_analyze or settings.doubao.model_id or "").strip() or None
    # max_retries=0：分析阶段不在 client 层重试（耗时长、token 贵），由上层决策
    raw_text, usage = chat_with_usage(
        model=model_analyze,
        user_text=user_text,
        timeout=analyze_timeout,
        max_retries=0,
        system_text=system_prompt,
    )
    if token_accumulator is not None:
        token_accumulator.append(usage)
    return parse_json_from_text(raw_text)


def analyze_news(
    limit: int = 20,
    token_accumulator: Optional[List[Dict[str, int]]] = None,
    only_content_hashes: Optional[Set[str]] = None,
) -> List[NewsAnalysisDetail]:
    """
    对 selected_news 中尚未写入 news_analysis_detail 的新闻进行详细分析。

    v3 改动：
    - 新增 only_content_hashes：仅分析指定 content_hash 集合内的条目（与 filter_news 对齐）。
      传 None 表示分析所有待处理条目（默认，用于补跑/回补场景）。
    - DoubaoUnavailableError（404/403/503）：立即上抛，由流水线记录告警。
    - DoubaoRateLimitError（429）：立即上抛（analyze 阶段 token 贵，不在此重试）。
    - 其他异常：仍"连续相同错误 ≥2 次熔断"，并 continue 下一条。
    - 修复：每条分析成功后单独提交，避免中途异常导致已成功条目全部丢失。
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
        if only_content_hashes is not None:
            q = q.where(SelectedNews.content_hash.in_(only_content_hashes))
        selected_items: List[SelectedNews] = [row[0] for row in session.execute(q).all()]
        if not selected_items:
            return []

        new_details: List[NewsAnalysisDetail] = []
        last_misc_error: Optional[str] = None
        same_misc_error_count = 0

        for item in selected_items:
            try:
                result = call_doubao_analyze_api(
                    item.title, item.content, token_accumulator=token_accumulator
                )
            except (DoubaoUnavailableError, DoubaoRateLimitError):
                raise
            except Exception as e:
                err = str(e)
                same_misc_error_count = same_misc_error_count + 1 if err == last_misc_error else 1
                last_misc_error = err
                logger.warning("详细分析 API 单条异常: %s", e)
                if same_misc_error_count >= 2:
                    raise RuntimeError(
                        f"分析步骤相同报错连续出现 2 次，停止本轮以节省 tokens: {last_misc_error}"
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
                confidence=_norm_int(result.get("confidence"), default=0)
                if settings.doubao.use_prompts_v2
                else None,
                uncertain=bool(result.get("uncertain"))
                if settings.doubao.use_prompts_v2 and result.get("uncertain") is not None
                else None,
                content_hash=item.content_hash,
            )
            session.add(detail)
            # 修复：每条单独提交，中途异常不丢已成功数据
            session.commit()
            # 修复 DetachedInstanceError：commit 默认 expire 全部属性，session.close
            # 后对象脱管，调用方（飞书推送）访问属性会报错。refresh 重载全部属性后
            # expunge 脱离会话，返回的对象可安全在会话外使用。
            session.refresh(detail)
            session.expunge(detail)
            new_details.append(detail)

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
