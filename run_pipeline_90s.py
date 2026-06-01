# -*- coding: utf-8 -*-
"""
流水线脚本 - 90 秒窗口版（自动化用）。
供阿里云/ECS 每 90 秒触发一次：采集近 90 秒新闻 -> 筛选 -> 详细分析。

v2 改动：
- 集成 PipelineHealthChecker，每轮结束后检查各层数据时效并在超阈值时飞书告警。
- DoubaoUnavailableError（404/403）：捕获后调用 notify_api_error，避免静默吞掉。
- DoubaoRateLimitError（429）：捕获后记录告警，等待下轮自然重试（不阻塞当前进程）。
"""
from __future__ import annotations

import logging
import time

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from news_analyzer import analyze_news
from doubao_client import DoubaoRateLimitError, DoubaoUnavailableError
from feishu_webhook import push_analysis_details, PipelineHealthChecker
from utils import now_beijing_naive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 采集窗口：90 秒 = 1.5 分钟
FETCH_WINDOW_MINUTES = 1.5

# 单例健康检查器（进程级复用，维护告警抑制状态）
_health_checker = PipelineHealthChecker()


def _sum_usage(usages: list) -> dict:
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

    # ── 步骤 1：采集 ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        new_raw, new_raw_hashes = fetch_latest_news(minutes=FETCH_WINDOW_MINUTES)
        new_raw_count = len(new_raw)
        logger.info("步骤1 采集: 新增 %s 条, 耗时 %.2fs", new_raw_count, time.perf_counter() - t0)
    except Exception as e:
        logger.exception("步骤1 失败: %s", e)
        _health_checker.check_and_alert()
        return

    if new_raw_count == 0:
        logger.info("无新新闻，跳过筛选与分析")
        _health_checker.check_and_alert()
        return

    # ── 步骤 2：筛选 ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    new_selected = []
    try:
        filter_tokens: list = []
        only_hashes = set(new_raw_hashes)
        new_selected = filter_news(
            limit=100,
            token_accumulator=filter_tokens,
            only_content_hashes=only_hashes,
        )
        u2 = _sum_usage(filter_tokens)
        logger.info(
            "步骤2 筛选: 新增 %s 条, 耗时 %.2fs, tokens=%s",
            len(new_selected), time.perf_counter() - t0, u2["total_tokens"],
        )
    except DoubaoUnavailableError as e:
        logger.error("步骤2 筛选遇到接口不可用错误（404/403），跳过本轮筛选与分析: %s", e)
        _health_checker.notify_api_error("步骤2筛选", "接口不可用", str(e))
        _health_checker.check_and_alert()
        return
    except DoubaoRateLimitError as e:
        logger.warning("步骤2 筛选遇到限流（429），本轮跳过，下轮自动重试: %s", e)
        _health_checker.notify_api_error("步骤2筛选", "429限流", str(e))
        _health_checker.check_and_alert()
        return
    except Exception as e:
        logger.exception("步骤2 失败: %s", e)
        _health_checker.check_and_alert()
        return

    # ── 步骤 3：详细分析 ──────────────────────────────────────────────
    t0 = time.perf_counter()
    new_details = []
    try:
        analyze_tokens: list = []
        new_details = analyze_news(limit=50, token_accumulator=analyze_tokens)
        u3 = _sum_usage(analyze_tokens)
        logger.info(
            "步骤3 分析: 新增 %s 条, 耗时 %.2fs, tokens=%s",
            len(new_details), time.perf_counter() - t0, u3["total_tokens"],
        )
    except DoubaoUnavailableError as e:
        logger.error("步骤3 分析遇到接口不可用错误（404/403），跳过本轮分析: %s", e)
        _health_checker.notify_api_error("步骤3分析", "接口不可用", str(e))
        _health_checker.check_and_alert()
        return
    except DoubaoRateLimitError as e:
        logger.warning("步骤3 分析遇到限流（429），本轮跳过，下轮自动重试: %s\n"
                       "提示：若持续限流，请在豆包控制台检查配额或升级套餐。", e)
        _health_checker.notify_api_error("步骤3分析", "429限流", str(e))
        _health_checker.check_and_alert()
        return
    except Exception as e:
        logger.exception("步骤3 失败: %s", e)
        _health_checker.check_and_alert()
        return

    # ── 步骤 4：飞书推送分析结果 ───────────────────────────────────────
    if new_details:
        try:
            push_analysis_details(new_details)
        except Exception:
            logger.exception("飞书分析结果推送异常（已忽略，不中断流水线）")

    # ── 每轮结束：健康检查（检查各层数据时效，超阈值发告警） ──────────
    _health_checker.check_and_alert()

    logger.info("流水线结束（90 秒窗口）")


if __name__ == "__main__":
    main()
