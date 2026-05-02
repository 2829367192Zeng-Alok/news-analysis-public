# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import sys

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from news_analyzer import analyze_news

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("run_task")


def main() -> None:
    logger.info("=== 开始执行定时任务 ===")

    try:
        added_raw, _ = fetch_latest_news()
        logger.info("新增 raw_news: %s 条", len(added_raw))
    except Exception as e:
        logger.exception("新闻采集失败: %s", e)

    try:
        selected = filter_news()
        logger.info("新增 selected_news: %s 条", len(selected))
    except Exception as e:
        logger.exception("AI 筛选失败: %s", e)

    try:
        analyzed = analyze_news()
        logger.info("新增 news_analysis_detail: %s 条", len(analyzed))
    except Exception as e:
        logger.exception("AI 详细分析失败: %s", e)

    logger.info("=== 定时任务执行完成 ===")


if __name__ == "__main__":
    main()

