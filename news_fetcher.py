# -*- coding: utf-8 -*-
"""
新闻采集模块：从配置的多个来源拉取新闻，同源/跨源去重后写入 raw_news。

- 支持自动（定时任务调用）或手动（命令行）执行。
- 使用 Tushare pro.news() 接口，src 为 sina / wallstreetcn 等，返回的 content 为纯文本正文，直接入库。
- 同源去重：单次拉取中同一来源内按 content_hash 去重。
- 跨源去重：合并多来源后按 content_hash 去重，并与库中已有 hash 比对，不重复入库。
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select

from config import settings
from models import RawNews, get_db_session
from news_sources import TushareSourceConfig, get_sources_by_ids
from utils import compute_content_hash, now_beijing_naive, parse_news_datetime

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2
# Tushare pro.news() 时间格式，与官方示例一致；接口采用北京时间(UTC+8)
TUSHARE_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
# 北京时间 UTC+8，用于请求 API 的时间范围（避免用 UTC 导致时间窗错位拉不到数据）
TZ_BEIJING = timezone(timedelta(hours=8))


def _get_tushare_client():
    try:
        import tushare as ts  # type: ignore
    except ImportError as e:
        raise RuntimeError("tushare 未安装，请先在虚拟环境中安装 tushare") from e
    if not settings.tushare.token:
        raise RuntimeError("未配置 TUSHARE_TOKEN，请在环境变量或 .env 中设置")
    return ts.pro_api(settings.tushare.token)


def _fetch_one_source(
    pro,
    source: TushareSourceConfig,
    start_date: str,
    end_date: str,
) -> List[Dict]:
    """从单个 Tushare 来源拉取一页。使用 pro.news()，返回的 content 为纯文本正文。"""
    for attempt in range(MAX_RETRIES):
        try:
            df = pro.news(
                src=source.tushare_src,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None:
                logger.warning("pro.news(%s) 返回 None, start_date=%s end_date=%s", source.tushare_src, start_date, end_date)
                return []
            if df.empty:
                logger.warning("pro.news(%s) 返回空表, start_date=%s end_date=%s", source.tushare_src, start_date, end_date)
                return []
            records = df.to_dict("records")
            logger.info("pro.news(%s) 拉取 %s 条, 时间窗 %s ~ %s", source.tushare_src, len(records), start_date, end_date)
            return records
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.warning(
                    "Tushare 拉取 [%s] 失败（已重试 %s 次）: %s",
                    source.source_id, MAX_RETRIES, e,
                )
                return []
            time.sleep(RETRY_DELAY)
    return []


# 入库 content 最大长度（MEDIUMTEXT 约 16MB，保守截断避免超限）
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB


def _normalize_record(
    r: Dict,
    source_id: str,
    default_time: datetime,
) -> Optional[Tuple[str, str, datetime, str]]:
    """
    归一化为 (title, content, news_datetime, source_id)。
    pro.news() 返回的 content 即为纯文本正文，直接使用，不掺入其他字段。
    """
    # 接口返回字段见文档：title, content, datetime；兼容多种键名；pandas 空值为 nan，需转为 str 再判空
    def _str(v):
        if v is None:
            return ""
        s = str(v).strip()
        if s.lower() == "nan" or not s:
            return ""
        return s

    title = _str(r.get("title") or r.get("Title"))
    content = _str(r.get("content") or r.get("Content") or r.get("summary"))
    if not title and not content:
        return None
    if not title:
        title = content[:80] + "..." if len(content) > 80 else content
    if not content:
        content = title
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH]
    raw_time = r.get("datetime") or r.get("pub_time") or r.get("time") or r.get("news_time") or ""
    news_dt = parse_news_datetime(raw_time) or default_time
    return (title, content, news_dt, source_id)


def _dedupe_by_hash(
    records: List[Tuple[str, str, datetime, str]],
) -> List[Tuple[str, str, datetime, str]]:
    """同批内按 content_hash 去重，保留首次出现。"""
    seen: Set[str] = set()
    out: List[Tuple[str, str, datetime, str]] = []
    for t in records:
        h = compute_content_hash(t[0], t[1])
        if h in seen:
            continue
        seen.add(h)
        out.append(t)
    return out


def fetch_latest_news(
    minutes: int = 5,
    source_ids: Optional[List[str]] = None,
) -> Tuple[List[RawNews], List[str]]:
    """
    从配置的新闻来源拉取最近 minutes 分钟内的新闻，同源与跨源去重后写入 raw_news。

    :param minutes: 拉取时间窗口（分钟）。
    :param source_ids: 仅拉取这些 source_id；None 表示全部默认来源。
    :return: (本次新增的 RawNews 列表, 对应的 content_hash 列表)，便于调用方在 session 关闭后仍能使用 hashes。
    """
    sources = get_sources_by_ids(source_ids)
    if not sources:
        logger.warning("未选择任何新闻来源，跳过拉取")
        return [], []

    pro = _get_tushare_client()
    # 使用北京时间作为请求时间窗，与 Tushare 接口约定一致，避免拉不到数据
    now_bj = datetime.now(TZ_BEIJING)
    start_time_bj = now_bj - timedelta(minutes=minutes)
    start_date = start_time_bj.strftime(TUSHARE_DATETIME_FMT)
    end_date = now_bj.strftime(TUSHARE_DATETIME_FMT)
    now = now_beijing_naive()

    # 按来源拉取并归一化，同源内先去重，再合并做跨源去重
    all_normalized: List[Tuple[str, str, datetime, str]] = []
    for src_cfg in sources:
        raw_list = _fetch_one_source(pro, src_cfg, start_date, end_date)
        one_source: List[Tuple[str, str, datetime, str]] = []
        for r in raw_list:
            t = _normalize_record(r, src_cfg.source_id, now)
            if t:
                one_source.append(t)
        # 同源内按 hash 去重（同一来源不接收重复新闻）
        before_src = len(one_source)
        one_source = _dedupe_by_hash(one_source)
        logger.info(
            "同源去重 %s: 归一化 %s 条 -> content_hash 去重后 %s 条",
            src_cfg.source_id, before_src, len(one_source),
        )
        all_normalized.extend(one_source)

    # 客户端时间窗过滤：仅保留 news_datetime 在 [start_time_bj, now_bj] 内的记录。
    # 若接口返回了超出请求窗口的旧数据，会与库中历史 hash 误匹配，导致“新增”偏少。
    start_naive = start_time_bj.replace(tzinfo=None)
    end_naive = now_bj.replace(tzinfo=None)
    before_time_filter = len(all_normalized)
    all_normalized = [t for t in all_normalized if start_naive <= t[2] <= end_naive]
    if before_time_filter != len(all_normalized):
        logger.info(
            "时间窗过滤: 保留 news_datetime 在 [%s, %s] 内的记录: %s 条 -> %s 条",
            start_naive, end_naive, before_time_filter, len(all_normalized),
        )

    before_cross = len(all_normalized)
    # 跨源去重（不同来源的同一新闻只保留一条）
    all_normalized = _dedupe_by_hash(all_normalized)
    logger.info(
        "跨源去重: 合并后 %s 条 -> content_hash 去重后 %s 条",
        before_cross, len(all_normalized),
    )

    if not all_normalized:
        return [], []

    # 与库中已有 content_hash 比对
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
        logger.info(
            "与库比对: 本批唯一 %s 条，其中 %s 条已在 raw_news 中 -> 新增 %s 条",
            len(unique_hashes), len(existing), len(unique_hashes) - len(existing),
        )
        # 入库时统一使用“当前时间”作为 create_time，避免误用新闻时间或默认值
        insert_time = now_beijing_naive()
        new_items: List[RawNews] = []
        seen_in_run: Set[str] = set()
        for (title, content, news_dt, source_id) in all_normalized:
            h = compute_content_hash(title, content)
            if h in existing or h in seen_in_run:
                continue
            seen_in_run.add(h)
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
        if new_items:
            session.add_all(new_items)
            session.commit()
            new_hashes = [r.content_hash for r in new_items]
            return new_items, new_hashes
        return [], []
    except Exception as e:
        session.rollback()
        logger.exception("写入 raw_news 失败: %s", e)
        raise
    finally:
        session.close()


def main_cli() -> None:
    """命令行入口：支持手动执行、指定时间窗口与来源。"""
    parser = argparse.ArgumentParser(description="新闻采集：从 Tushare 拉取华尔街见闻、新浪财经等并去重入库")
    parser.add_argument(
        "--minutes",
        type=int,
        default=60,
        help="拉取最近 N 分钟内的新闻（默认 60）",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=None,
        help="逗号分隔的 source_id，如 华尔街见闻,新浪财经；不传则拉取全部默认来源",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅拉取并打印条数，不写入数据库",
    )
    args = parser.parse_args()
    source_ids = [s.strip() for s in args.sources.split(",")] if args.sources else None

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.dry_run:
        # dry-run：只调接口看条数，不入库
        sources = get_sources_by_ids(source_ids)
        if not sources:
            print("未选择任何来源")
            return
        pro = _get_tushare_client()
        now_bj = datetime.now(TZ_BEIJING)
        start_time_bj = now_bj - timedelta(minutes=args.minutes)
        start_date = start_time_bj.strftime(TUSHARE_DATETIME_FMT)
        end_date = now_bj.strftime(TUSHARE_DATETIME_FMT)
        now = now_beijing_naive()
        all_n: List[Tuple[str, str, datetime, str]] = []
        for src_cfg in sources:
            raw_list = _fetch_one_source(pro, src_cfg, start_date, end_date)
            one_s: List[Tuple[str, str, datetime, str]] = []
            for r in raw_list:
                t = _normalize_record(r, src_cfg.source_id, now)
                if t:
                    one_s.append(t)
            one_s = _dedupe_by_hash(one_s)
            print(f"  {src_cfg.source_id}: 拉取 {len(raw_list)} 条，同源去重后 {len(one_s)} 条")
            all_n.extend(one_s)
        all_n = _dedupe_by_hash(all_n)
        print(f"跨源去重后合计: {len(all_n)} 条（实际入库还需与 DB 已有 hash 比对）")
        return

    added, _ = fetch_latest_news(minutes=args.minutes, source_ids=source_ids)
    print(f"新增 raw_news 记录数: {len(added)}")


if __name__ == "__main__":
    main_cli()
