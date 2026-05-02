# -*- coding: utf-8 -*-
"""
检查 news_analysis_detail 表是否有新数据，并导出到静态展示系统（web_display/data/feed.json）。
用于定时任务（cron）：在服务器上周期性执行，使前端页面展示最新分析结果。

用法：
  python sync_news_to_display.py              # 始终导出（覆盖 feed.json）
  python sync_news_to_display.py --no-change  # 仅当有新数据时才写入文件（避免多余 IO）

依赖：与主项目相同（config, models），需能连接 news_analysis_detail 所在数据库。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录：脚本可能在项目根或子目录被调用
PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DISPLAY_DATA = PROJECT_ROOT / "web_display" / "data"
STATE_FILE = PROJECT_ROOT / "web_display" / ".sync_state.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _serialize_value(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def build_feed(session, limit: int = 100):
    from sqlalchemy import select, func
    from models import NewsAnalysisDetail

    # 统计
    total_news = session.scalar(select(func.count(NewsAnalysisDetail.id))) or 0
    latest_time = session.scalar(select(func.max(NewsAnalysisDetail.news_datetime)))

    # 列表（最近 limit 条）
    q = (
        select(NewsAnalysisDetail)
        .order_by(NewsAnalysisDetail.news_datetime.desc())
        .limit(limit)
    )
    rows = [r[0] for r in session.execute(q).all()]

    items = []
    details = {}
    for n in rows:
        item = {
            "id": n.id,
            "title": n.title,
            "source": n.source,
            "news_datetime": _serialize_value(n.news_datetime),
            "relevance": bool(n.relevance),
            "direction": n.direction,
            "impact": n.impact,
            "shorttime": n.shorttime,
            "midtime": n.midtime,
            "longtime": n.longtime,
            "insight": n.insight,
            "conclusion": n.conclusion,
        }
        items.append(item)
        details[n.id] = {
            "id": n.id,
            "title": n.title,
            "content": n.content,
            "source": n.source,
            "news_datetime": _serialize_value(n.news_datetime),
            "relevance": bool(n.relevance),
            "direction": n.direction,
            "impact": n.impact,
            "interest_direction": n.interest_direction,
            "interest_impact": n.interest_impact,
            "dollar_direction": n.dollar_direction,
            "dollar_impact": n.dollar_impact,
            "warrisk_direction": n.warrisk_direction,
            "warrisk_impact": n.warrisk_impact,
            "liquidity_direction": n.liquidity_direction,
            "liquidity_impact": n.liquidity_impact,
            "emotion_direction": n.emotion_direction,
            "emotion_impact": n.emotion_impact,
            "keyword": n.keyword,
            "Reference": n.Reference,
            "interest": n.interest,
            "dollar": n.dollar,
            "warrisk": n.warrisk,
            "liquidity": n.liquidity,
            "emotion": n.emotion,
            "shorttime": n.shorttime,
            "midtime": n.midtime,
            "longtime": n.longtime,
            "insight": n.insight,
            "conclusion": n.conclusion,
        }

    return {
        "stats": {
            "total_news": int(total_news),
            "latest_news_time": _serialize_value(latest_time),
        },
        "items": items,
        "details": details,
    }


def get_last_state():
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_state(total_news: int, max_id: int):
    WEB_DISPLAY_DATA.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"total_news": total_news, "max_id": max_id}, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="同步 news_analysis_detail 到静态展示数据")
    parser.add_argument(
        "--no-change",
        action="store_true",
        help="仅当有新数据时才写入 feed.json（根据 total_news 与 max_id 判断）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="导出列表与详情的最大条数（默认 100）",
    )
    args = parser.parse_args()

    # 确保从项目根加载 config/models
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    os.chdir(PROJECT_ROOT)

    from models import NewsAnalysisDetail, get_db_session
    from sqlalchemy import select, func

    session = get_db_session()
    try:
        feed = build_feed(session, limit=args.limit)
    finally:
        session.close()

    total_news = feed["stats"]["total_news"]
    max_id = max((x["id"] for x in feed["items"]), default=0)
    last = get_last_state()

    if args.no_change and last is not None:
        if last.get("total_news") == total_news and last.get("max_id") == max_id:
            logger.info("无新数据，跳过写入 (total=%s, max_id=%s)", total_news, max_id)
            return 0
    else:
        logger.info("导出 %s 条到展示系统 (total=%s)", len(feed["items"]), total_news)

    WEB_DISPLAY_DATA.mkdir(parents=True, exist_ok=True)
    feed_path = WEB_DISPLAY_DATA / "feed.json"
    with open(feed_path, "w", encoding="utf-8") as f:
        json.dump(feed, f, ensure_ascii=False, indent=2)
    save_state(total_news, max_id)
    logger.info("已写入 %s", feed_path)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.exception("同步失败: %s", e)
        sys.exit(1)
