# -*- coding: utf-8 -*-
"""
流水线脚本 - 90 秒窗口版（自动化用）。
供阿里云/ECS 每 90 秒触发一次：采集近 90 秒新闻 -> 筛选 -> 详细分析。

v3 改动：
- 采集窗口可通过环境变量 FETCH_WINDOW_MINUTES 覆盖（默认 1.5 = 90 秒）。
- 新增"补偿筛选"：若存在超过 CATCHUP_STALE_MINUTES 仍未筛选的 raw_news（此前窗口
  因 429/接口不可用失败遗留），本轮限量补筛，避免数据静默滞留。
- 分析阶段通过 only_content_hashes 限制在本批新增内，避免历史积压把单轮拖过
  shell 的 timeout 导致在途调用被截断、token 白烧。
v2 改动：
- 集成 PipelineHealthChecker，每轮结束后检查各层数据时效并在超阈值时飞书告警。
- DoubaoUnavailableError（404/403）：捕获后调用 notify_api_error，避免静默吞掉。
- DoubaoRateLimitError（429）：捕获后记录告警，等待下轮自然重试（不阻塞当前进程）。
"""
from __future__ import annotations

import logging
import os
import time
from datetime import timedelta
from typing import Optional, Set

from sqlalchemy import select, func

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from news_analyzer import analyze_news
from doubao_client import DoubaoRateLimitError, DoubaoUnavailableError
from feishu_webhook import push_analysis_details, PipelineHealthChecker
from utils import now_beijing_naive, sum_token_usage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 采集窗口：90 秒 = 1.5 分钟；可被环境变量覆盖（run_pipeline_90s_loop.sh 同步导出）
FETCH_WINDOW_MINUTES = float(os.environ.get("FETCH_WINDOW_MINUTES", "1.5"))

# 补偿筛选阈值（分钟）：raw_news 超过该时长仍未筛选时，本轮限量补筛
CATCHUP_STALE_MINUTES = float(os.environ.get("CATCHUP_STALE_MINUTES", "30"))
# 补偿筛选单轮上限，避免补偿拖垮本轮时长
CATCHUP_FILTER_LIMIT = int(os.environ.get("CATCHUP_FILTER_LIMIT", "15"))

# 单例健康检查器（进程级复用，维护告警抑制状态）
_health_checker = PipelineHealthChecker()


def _count_stale_unfiltered(older_than_minutes: float) -> int:
    """统计 create_time 早于 N 分钟前、且 relevance 仍为 NULL 的 raw_news 数量。"""
    from models import RawNews, get_db_session

    session = get_db_session()
    try:
        threshold = now_beijing_naive() - timedelta(minutes=older_than_minutes)
        return int(
            session.scalar(
                select(func.count(RawNews.id)).where(
                    RawNews.relevance.is_(None),
                    RawNews.create_time < threshold,
                )
            )
            or 0
        )
    finally:
        session.close()


def main() -> None:
    started = now_beijing_naive()
    logger.info("流水线开始（%s 分钟窗口）: %s", FETCH_WINDOW_MINUTES, started)

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

    # ── 步骤 2：筛选（本批） ─────────────────────────────────────────
    new_selected = []
    if new_raw_count > 0:
        t0 = time.perf_counter()
        try:
            filter_tokens: list = []
            only_hashes: Set[str] = set(new_raw_hashes)
            new_selected = filter_news(
                limit=100,
                token_accumulator=filter_tokens,
                only_content_hashes=only_hashes,
            )
            u2 = sum_token_usage(filter_tokens)
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
    else:
        logger.info("无新新闻，跳过本批筛选")

    # ── 步骤 2.5：补偿筛选（历史滞留的未筛 raw_news） ────────────────
    catchup_ran = False
    try:
        stale = _count_stale_unfiltered(CATCHUP_STALE_MINUTES)
        if stale > 0:
            logger.warning("[补偿筛选] 发现 %s 条超过 %s 分钟仍未筛选的 raw_news，本轮限量补筛 %s 条",
                           stale, CATCHUP_STALE_MINUTES, CATCHUP_FILTER_LIMIT)
            catchup_tokens: list = []
            catchup_selected = filter_news(
                limit=CATCHUP_FILTER_LIMIT,
                token_accumulator=catchup_tokens,
            )
            catchup_ran = True
            u2c = sum_token_usage(catchup_tokens)
            logger.info(
                "[补偿筛选] 新增 %s 条, tokens=%s",
                len(catchup_selected), u2c["total_tokens"],
            )
    except (DoubaoUnavailableError, DoubaoRateLimitError) as e:
        # 补偿失败不影响主流程，也不额外告警（主流程失败已发告警）
        logger.warning("[补偿筛选] 失败（下轮重试）: %s", e)
    except Exception as e:
        logger.exception("[补偿筛选] 异常（忽略，不中断流水线）: %s", e)

    # ── 步骤 3：详细分析 ──────────────────────────────────────────────
    # 发生过补偿筛选时放开 hash 限制，让补偿产出的 selected 同轮进入分析；
    # 否则仅分析本批新增，防止历史积压把单轮拖过 shell timeout。
    analyze_only: Optional[Set[str]] = None if catchup_ran else set(new_raw_hashes)
    t0 = time.perf_counter()
    new_details = []
    try:
        analyze_tokens: list = []
        new_details = analyze_news(
            limit=50,
            token_accumulator=analyze_tokens,
            only_content_hashes=analyze_only,
        )
        u3 = sum_token_usage(analyze_tokens)
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

    logger.info("流水线结束（%s 分钟窗口）", FETCH_WINDOW_MINUTES)


if __name__ == "__main__":
    main()
