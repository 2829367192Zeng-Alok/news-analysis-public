# -*- coding: utf-8 -*-
"""
流水线脚本 - 90 秒窗口版（自动化用）。
供阿里云/ECS 每 90 秒触发一次：采集近 90 秒新闻 -> 筛选 -> 详细分析。
不写报告文件、不尝试打开文件，仅打日志，适合无人值守定时执行。
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from news_analyzer import analyze_news
from utils import now_beijing_naive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 采集窗口：90 秒 = 1.5 分钟（Tushare 接口按分钟，此处用小数）
FETCH_WINDOW_MINUTES = 1.5


def _sum_usage(usages: list) -> dict:
    """汇总多轮调用的 token 用量。"""
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for u in usages:
        if isinstance(u, dict):
            total["input_tokens"] += int(u.get("input_tokens") or 0)
            total["output_tokens"] += int(u.get("output_tokens") or 0)
            total["total_tokens"] += int(u.get("total_tokens") or 0)
    if total["total_tokens"] == 0 and (total["input_tokens"] or total["output_tokens"]):
        total["total_tokens"] = total["input_tokens"] + total["output_tokens"]
    return total


def main() -> None:
    started = now_beijing_naive()
    logger.info("流水线开始（90 秒窗口）: %s", started)

    t0 = time.perf_counter()
    try:
        new_raw, new_raw_hashes = fetch_latest_news(minutes=FETCH_WINDOW_MINUTES)
        new_raw_count = len(new_raw)
        step1 = time.perf_counter() - t0
        logger.info("步骤1 采集: 新增 %s 条, 耗时 %.2fs", new_raw_count, step1)
    except Exception as e:
        logger.exception("步骤1 失败: %s", e)
        return

    if new_raw_count == 0:
        logger.info("无新新闻，跳过筛选与分析")
        return

    t0 = time.perf_counter()
    try:
        filter_tokens: list = []
        only_hashes = set(new_raw_hashes)
        new_selected = filter_news(
            limit=100,
            token_accumulator=filter_tokens,
            only_content_hashes=only_hashes,
        )
        step2 = time.perf_counter() - t0
        u2 = _sum_usage(filter_tokens)
        logger.info(
            "步骤2 筛选: 新增 %s 条, 耗时 %.2fs, tokens=%s",
            len(new_selected), step2, u2["total_tokens"],
        )
    except Exception as e:
        logger.exception("步骤2 失败: %s", e)
        return

    t0 = time.perf_counter()
    try:
        analyze_tokens: list = []
        new_details = analyze_news(limit=50, token_accumulator=analyze_tokens)
        step3 = time.perf_counter() - t0
        u3 = _sum_usage(analyze_tokens)
        logger.info(
            "步骤3 分析: 新增 %s 条, 耗时 %.2fs, tokens=%s",
            len(new_details), step3, u3["total_tokens"],
        )
    except Exception as e:
        logger.exception("步骤3 失败: %s", e)
        return

    logger.info("流水线结束（90 秒窗口）")


if __name__ == "__main__":
    main()
