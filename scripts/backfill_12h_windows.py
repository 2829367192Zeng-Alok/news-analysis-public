#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Set, Tuple

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import RawNews, get_db_session
from news_analyzer import analyze_news
from news_fetcher import (
    TUSHARE_DATETIME_FMT,
    TZ_BEIJING,
    _dedupe_by_hash,
    _fetch_one_source,
    _get_tushare_client,
    _normalize_record,
)
from news_filter import filter_news
from news_sources import get_sources_by_ids
from utils import compute_content_hash, now_beijing_naive, sum_token_usage

logger = logging.getLogger(__name__)


def _parse_bj_naive(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _fetch_window_raw(
    start_naive: datetime,
    end_naive: datetime,
    source_ids: Optional[List[str]] = None,
) -> Tuple[List[RawNews], List[str]]:
    sources = get_sources_by_ids(source_ids)
    if not sources:
        return [], []

    pro = _get_tushare_client()
    start_bj = start_naive.replace(tzinfo=TZ_BEIJING)
    end_bj = end_naive.replace(tzinfo=TZ_BEIJING)
    start_date = start_bj.strftime(TUSHARE_DATETIME_FMT)
    end_date = end_bj.strftime(TUSHARE_DATETIME_FMT)

    all_normalized = []
    default_time = now_beijing_naive()
    for src_cfg in sources:
        raw_list = _fetch_one_source(pro, src_cfg, start_date, end_date)
        one_source = []
        for r in raw_list:
            t = _normalize_record(r, src_cfg.source_id, default_time)
            if t:
                one_source.append(t)
        one_source = _dedupe_by_hash(one_source)
        all_normalized.extend(one_source)

    # 客户端时间窗再次过滤
    all_normalized = [t for t in all_normalized if start_naive <= t[2] <= end_naive]
    all_normalized = _dedupe_by_hash(all_normalized)
    if not all_normalized:
        return [], []

    hashes = [compute_content_hash(t[0], t[1]) for t in all_normalized]
    unique_hashes = list(dict.fromkeys(hashes))

    session = get_db_session()
    try:
        existing = {
            h
            for (h,) in session.execute(
                select(RawNews.content_hash).where(RawNews.content_hash.in_(unique_hashes))
            ).all()
        }
        new_items: List[RawNews] = []
        new_hashes: List[str] = []
        seen: Set[str] = set()
        insert_time = now_beijing_naive()
        for (title, content, news_dt, source_id) in all_normalized:
            h = compute_content_hash(title, content)
            if h in existing or h in seen:
                continue
            seen.add(h)
            existing.add(h)
            new_items.append(
                RawNews(
                    title=title,
                    content=content,
                    news_datetime=news_dt,
                    source=source_id,
                    create_time=insert_time,
                    content_hash=h,
                )
            )
            new_hashes.append(h)
        if new_items:
            session.add_all(new_items)
            session.commit()
        return new_items, new_hashes
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_backfill(start_dt: datetime, end_dt: datetime, window_hours: int) -> None:
    cursor = start_dt
    idx = 0
    while cursor < end_dt:
        idx += 1
        window_end = min(cursor + timedelta(hours=window_hours), end_dt)
        logger.info("窗口#%s: %s -> %s", idx, cursor, window_end)

        try:
            new_raw, new_raw_hashes = _fetch_window_raw(cursor, window_end)
            logger.info("窗口#%s 采集新增 raw_news=%s", idx, len(new_raw))
        except Exception as e:
            logger.exception("窗口#%s 采集失败: %s", idx, e)
            cursor = window_end
            continue

        if not new_raw_hashes:
            cursor = window_end
            continue

        try:
            filter_tokens = []
            selected = filter_news(
                limit=max(100, len(new_raw_hashes) + 20),
                token_accumulator=filter_tokens,
                only_content_hashes=set(new_raw_hashes),
            )
            u2 = sum_token_usage(filter_tokens)
            logger.info(
                "窗口#%s 筛选新增 selected_news=%s, tokens=%s",
                idx, len(selected), u2["total_tokens"],
            )
        except Exception as e:
            logger.exception("窗口#%s 筛选失败: %s", idx, e)
            cursor = window_end
            continue

        try:
            analyze_tokens = []
            details = analyze_news(
                limit=max(50, len(selected) + 10),
                token_accumulator=analyze_tokens,
            )
            u3 = sum_token_usage(analyze_tokens)
            logger.info(
                "窗口#%s 分析新增 detail=%s, tokens=%s",
                idx, len(details), u3["total_tokens"],
            )
        except Exception as e:
            logger.exception("窗口#%s 分析失败: %s", idx, e)

        cursor = window_end


def main() -> None:
    parser = argparse.ArgumentParser(description="按 12 小时窗口回补采集/筛选/分析")
    parser.add_argument(
        "--start",
        type=str,
        default="2026-04-27 00:00:00",
        help="起始北京时间（naive）格式: YYYY-mm-dd HH:MM:SS",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="结束北京时间（naive）格式: YYYY-mm-dd HH:MM:SS，不传则当前北京时间",
    )
    parser.add_argument("--window-hours", type=int, default=12)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    start_dt = _parse_bj_naive(args.start)
    if args.end:
        end_dt = _parse_bj_naive(args.end)
    else:
        end_dt = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

    if end_dt <= start_dt:
        raise ValueError("end 必须大于 start")

    logger.info("开始回补: %s -> %s, window=%sh", start_dt, end_dt, args.window_hours)
    run_backfill(start_dt, end_dt, args.window_hours)
    logger.info("回补完成")


if __name__ == "__main__":
    main()
