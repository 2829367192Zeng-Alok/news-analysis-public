#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对服务器最新 20 条 raw_news 依次执行 AI 筛选与详细分析，写入数据库，
并将分析结果导出为可读的文本文件供检查。
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# 项目根
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import select

from models import RawNews, SelectedNews, NewsAnalysisDetail, get_db_session
from news_filter import call_doubao_filter_api
from news_analyzer import call_doubao_analyze_api, _norm_int, _norm_list, _norm_str

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

def _build_detail_from_result(item, result):
    """根据 API 返回构建 NewsAnalysisDetail 并返回（未 add）。"""
    return NewsAnalysisDetail(
        title=item.title,
        content=item.content,
        news_datetime=item.news_datetime,
        source=item.source,
        create_time=datetime.now(timezone.utc).replace(tzinfo=None),
        relevance=bool(result.get("relevance", getattr(item, "relevance", False))),
        direction=_norm_int(result.get("direction"), getattr(item, "direction", 0) or 0),
        impact=_norm_int(result.get("impact"), getattr(item, "impact", 0) or 0),
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


def _format_dt(dt):
    if dt is None:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


def _section(title: str, body: str, indent: str = "  ") -> str:
    if not (body or "").strip():
        body = "（无）"
    return f"{title}\n{indent}{body.replace(chr(10), chr(10) + indent)}\n"


def main():
    session = get_db_session()
    try:
        # 1) 取最新 20 条 raw_news（按新闻时间倒序）
        q_raw = (
            select(RawNews)
            .order_by(RawNews.news_datetime.desc())
            .limit(20)
        )
        raw_list = [row[0] for row in session.execute(q_raw).all()]
        if not raw_list:
            logger.info("raw_news 表为空，无需处理")
            return

        logger.info("取到最新 %s 条 raw_news，开始筛选与分析", len(raw_list))
        hashes_20 = {r.content_hash for r in raw_list}

        # 2) 已存在于 selected_news 的 content_hash
        q_sel = select(SelectedNews.content_hash).where(SelectedNews.content_hash.in_(hashes_20))
        existing_selected = {row[0] for row in session.execute(q_sel).all()}

        # 3) 对尚未筛选的 raw 调用筛选 API，通过则写入 selected_news
        for raw in raw_list:
            if raw.content_hash in existing_selected:
                continue
            try:
                res = call_doubao_filter_api(raw.title, raw.content)
                if not res.get("relevance"):
                    continue
                sn = SelectedNews(
                    title=raw.title,
                    content=raw.content,
                    news_datetime=raw.news_datetime,
                    source=raw.source,
                    create_time=datetime.now(timezone.utc).replace(tzinfo=None),
                    relevance=True,
                    direction=res.get("direction"),
                    impact=res.get("impact"),
                    content_hash=raw.content_hash,
                )
                session.add(sn)
                existing_selected.add(raw.content_hash)
                logger.info("筛选通过并写入 selected_news: %s", raw.title[:50])
            except Exception as e:
                logger.warning("筛选单条失败 %s: %s", raw.title[:40], e)
        session.commit()

        # 4) 已存在于 news_analysis_detail 的 content_hash
        q_detail = select(NewsAnalysisDetail.content_hash).where(NewsAnalysisDetail.content_hash.in_(hashes_20))
        existing_detail = {row[0] for row in session.execute(q_detail).all()}

        # 5) 从 selected_news 中取本批 20 条里尚未详细分析的，调用分析 API 并写入
        q_sel_items = (
            select(SelectedNews)
            .where(SelectedNews.content_hash.in_(hashes_20))
            .where(~SelectedNews.content_hash.in_(existing_detail))
        )
        to_analyze = [row[0] for row in session.execute(q_sel_items).all()]
        for item in to_analyze:
            try:
                result = call_doubao_analyze_api(item.title, item.content)
                detail = _build_detail_from_result(item, result)
                session.add(detail)
                session.commit()
                existing_detail.add(item.content_hash)
                logger.info("详细分析并写入: %s", item.title[:50])
            except Exception as e:
                session.rollback()
                logger.warning("详细分析单条失败 %s: %s", item.title[:40], e)

        # 6) 查询本批 20 条对应的全部分析结果（按新闻时间倒序）
        q_final = (
            select(NewsAnalysisDetail)
            .where(NewsAnalysisDetail.content_hash.in_(hashes_20))
            .order_by(NewsAnalysisDetail.news_datetime.desc())
        )
        details = [row[0] for row in session.execute(q_final).all()]

        # 7) 写入可读文本
        report_path = Path(__file__).resolve().parent / "analysis_report.txt"
        lines = [
            "=" * 80,
            "金融新闻 AI 分析结果报告",
            f"生成时间: {_format_dt(datetime.now())}",
            f"共 {len(details)} 条分析记录（对应最新 20 条新闻中已筛选且已分析的条目）",
            "=" * 80,
            "",
        ]
        for i, d in enumerate(details, 1):
            block = [
                "",
                "-" * 80,
                f"【{i}】 {d.title}",
                f"来源: {d.source}  新闻时间: {_format_dt(d.news_datetime)}",
                "-" * 80,
                _section("■ 核心结论", d.conclusion or ""),
                _section("■ 投资启示", d.insight or ""),
                _section("■ 短期结论", d.shorttime or ""),
                _section("■ 中期结论", d.midtime or ""),
                _section("■ 长期结论", d.longtime or ""),
                _section("■ 实际利率", d.interest or ""),
                _section("■ 美元指数", d.dollar or ""),
                _section("■ 地缘政治风险", d.warrisk or ""),
                _section("■ 流动性", d.liquidity or ""),
                _section("■ 市场情绪", d.emotion or ""),
            ]
            if d.keyword:
                block.append(_section("■ 关键词", ", ".join(d.keyword)))
            block.append("")
            lines.extend(block)

        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("分析结果已写入: %s", report_path)
        print(f"分析完成。新增筛选/分析已入库；报告已生成: {report_path}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
