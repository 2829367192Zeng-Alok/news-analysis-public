# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import sys

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from news_analyzer import analyze_news
from doubao_client import DoubaoRateLimitError, DoubaoUnavailableError
from feishu_webhook import push_analysis_details, PipelineHealthChecker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("run_task")

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
    logger.info("=== 开始执行定时任务 ===")

    # 步骤 1：采集
    try:
        added_raw, _ = fetch_latest_news()
        logger.info("新增 raw_news: %s 条", len(added_raw))
    except Exception as e:
        logger.exception("新闻采集失败: %s", e)
        _health_checker.check_and_alert()
        return

    # 步骤 2：筛选
    try:
        filter_tokens: list = []
        selected = filter_news(token_accumulator=filter_tokens)
        u2 = _sum_usage(filter_tokens)
        logger.info("新增 selected_news: %s 条, tokens=%s", len(selected), u2["total_tokens"])
    except DoubaoUnavailableError as e:
        logger.error("筛选步骤遇到接口不可用错误（404/403）: %s", e)
        _health_checker.notify_api_error("步骤2筛选", "接口不可用", str(e))
        _health_checker.check_and_alert()
        return
    except DoubaoRateLimitError as e:
        logger.warning("筛选步骤遇到限流（429）: %s", e)
        _health_checker.notify_api_error("步骤2筛选", "429限流", str(e))
        _health_checker.check_and_alert()
        return
    except Exception as e:
        logger.exception("AI 筛选失败: %s", e)
        _health_checker.check_and_alert()
        return

    # 步骤 3：详细分析
    try:
        analyze_tokens: list = []
        analyzed = analyze_news(token_accumulator=analyze_tokens)
        u3 = _sum_usage(analyze_tokens)
        logger.info("新增 news_analysis_detail: %s 条, tokens=%s", len(analyzed), u3["total_tokens"])
        try:
            push_analysis_details(analyzed)
        except Exception:
            logger.exception("飞书 Webhook 推送环节异常（已忽略，不中断任务）")
    except DoubaoUnavailableError as e:
        logger.error("分析步骤遇到接口不可用错误（404/403）: %s", e)
        _health_checker.notify_api_error("步骤3分析", "接口不可用", str(e))
    except DoubaoRateLimitError as e:
        logger.warning("分析步骤遇到限流（429）: %s", e)
        _health_checker.notify_api_error("步骤3分析", "429限流", str(e))
    except Exception as e:
        logger.exception("AI 详细分析失败: %s", e)

    _health_checker.check_and_alert()
    logger.info("=== 定时任务执行完成 ===")


if __name__ == "__main__":
    main()

