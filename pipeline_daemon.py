# -*- coding: utf-8 -*-
"""
流水线轮询守护进程（替代阿里云 90 秒定时触发方案）。

常驻运行，每 POLL_INTERVAL_SECONDS（默认 20 秒）执行一轮：
  1) 采集：拉取近 FETCH_WINDOW_MINUTES 分钟新闻写入 raw_news（同 hash 去重）；
  2) 有新数据 -> 本批筛选；无新数据 -> 跳过本批筛选；
  3) 滞留补偿筛选：存在超过 CATCHUP_STALE_MINUTES 未筛的 raw_news 时限量补筛；
  4) 详细分析（默认仅本批 + 补偿产出），成功后飞书推送；
  5) 每轮结束健康检查（采集/分析层停摆告警）；
  6) 有新分析结果时立即刷新 web_display/data/feed.json（静态站近实时）。

用法：
  python pipeline_daemon.py            # 常驻轮询
  python pipeline_daemon.py --once     # 只跑一轮（运维验证用）
  环境变量：POLL_INTERVAL_SECONDS / FETCH_WINDOW_MINUTES / CATCHUP_STALE_MINUTES /
            CATCHUP_FILTER_LIMIT / USE_PROMPTS_V2 等（见 .env.example）

生产部署建议用 systemd 托管（见 docs/production_update_ops_2026-09-07.md）。
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import timedelta
from typing import List, Optional, Set

from sqlalchemy import select, func

from config import settings
from doubao_client import DoubaoRateLimitError, DoubaoUnavailableError
from feishu_webhook import push_analysis_details, PipelineHealthChecker
from news_analyzer import analyze_news
from news_fetcher import fetch_latest_news
from news_filter import filter_news
from utils import acquire_single_instance_lock, now_beijing_naive, sum_token_usage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline_daemon")

# 轮询间隔（秒）
POLL_INTERVAL_SECONDS = float(os.environ.get("POLL_INTERVAL_SECONDS", "20"))
# 每轮采集窗口（分钟）。略大于轮询间隔，保证处理耗时导致的空档不漏数据
FETCH_WINDOW_MINUTES = float(os.environ.get("FETCH_WINDOW_MINUTES", "2"))
# 补偿筛选阈值与上限（与旧 90s 方案语义一致）
CATCHUP_STALE_MINUTES = float(os.environ.get("CATCHUP_STALE_MINUTES", "30"))
CATCHUP_FILTER_LIMIT = int(os.environ.get("CATCHUP_FILTER_LIMIT", "15"))

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


def _refresh_feed() -> None:
    """有新分析结果后立即刷新静态站数据；失败不影响流水线。"""
    try:
        from sync_news_to_display import run_sync

        run_sync(no_change=True)
    except Exception:
        logger.exception("刷新 web_display feed 失败（已忽略，不影响流水线）")


def run_pipeline_round() -> None:
    """执行一轮：采集 -> 筛选 -> 补偿筛选 -> 分析 -> 推送 -> 健康检查 -> 刷新展示。"""
    started = now_beijing_naive()
    logger.info("轮次开始（窗口 %s 分钟）: %s", FETCH_WINDOW_MINUTES, started)

    # ── 1. 采集 ───────────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        new_raw, new_raw_hashes = fetch_latest_news(minutes=FETCH_WINDOW_MINUTES)
        new_raw_count = len(new_raw)
        logger.info("采集: 新增 %s 条, 耗时 %.2fs", new_raw_count, time.perf_counter() - t0)
    except Exception as e:
        logger.exception("采集失败: %s", e)
        _health_checker.check_and_alert()
        return

    # ── 2. 本批筛选 ──────────────────────────────────────────────────
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
                "筛选: 新增 %s 条, 耗时 %.2fs, tokens=%s",
                len(new_selected), time.perf_counter() - t0, u2["total_tokens"],
            )
        except DoubaoUnavailableError as e:
            logger.error("筛选接口不可用（404/403），本轮中止: %s", e)
            _health_checker.notify_api_error("筛选", "接口不可用", str(e))
            _health_checker.check_and_alert()
            return
        except DoubaoRateLimitError as e:
            logger.warning("筛选限流（429），本轮中止，下轮自动重试: %s", e)
            _health_checker.notify_api_error("筛选", "429限流", str(e))
            _health_checker.check_and_alert()
            return
        except Exception as e:
            logger.exception("筛选失败: %s", e)
            _health_checker.check_and_alert()
            return
    else:
        logger.info("无新数据，跳过本批筛选")

    # ── 3. 滞留补偿筛选 ──────────────────────────────────────────────
    catchup_ran = False
    try:
        stale = _count_stale_unfiltered(CATCHUP_STALE_MINUTES)
        if stale > 0:
            logger.warning(
                "[补偿筛选] %s 条超过 %s 分钟未筛，限量补筛 %s 条",
                stale, CATCHUP_STALE_MINUTES, CATCHUP_FILTER_LIMIT,
            )
            catchup_tokens: list = []
            catchup_selected = filter_news(
                limit=CATCHUP_FILTER_LIMIT,
                token_accumulator=catchup_tokens,
            )
            catchup_ran = True
            u2c = sum_token_usage(catchup_tokens)
            logger.info("[补偿筛选] 新增 %s 条, tokens=%s", len(catchup_selected), u2c["total_tokens"])
    except (DoubaoUnavailableError, DoubaoRateLimitError) as e:
        logger.warning("[补偿筛选] 失败（下轮重试）: %s", e)
    except Exception as e:
        logger.exception("[补偿筛选] 异常（忽略）: %s", e)

    # ── 4. 详细分析 ──────────────────────────────────────────────────
    # 发生过补偿筛选时放开 hash 限制，让补偿产出同轮进入分析；否则仅分析本批
    analyze_only: Optional[Set[str]] = None if catchup_ran else set(new_raw_hashes)
    new_details: List = []
    if analyze_only is None or len(analyze_only) > 0:
        t0 = time.perf_counter()
        try:
            analyze_tokens: list = []
            new_details = analyze_news(
                limit=50,
                token_accumulator=analyze_tokens,
                only_content_hashes=analyze_only,
            )
            u3 = sum_token_usage(analyze_tokens)
            logger.info(
                "分析: 新增 %s 条, 耗时 %.2fs, tokens=%s, v2=%s",
                len(new_details), time.perf_counter() - t0, u3["total_tokens"],
                settings.doubao.use_prompts_v2,
            )
        except DoubaoUnavailableError as e:
            logger.error("分析接口不可用（404/403），本轮中止: %s", e)
            _health_checker.notify_api_error("分析", "接口不可用", str(e))
            _health_checker.check_and_alert()
            return
        except DoubaoRateLimitError as e:
            logger.warning("分析限流（429），本轮中止，下轮自动重试: %s", e)
            _health_checker.notify_api_error("分析", "429限流", str(e))
            _health_checker.check_and_alert()
            return
        except Exception as e:
            logger.exception("分析失败: %s", e)
            _health_checker.check_and_alert()
            return

    # ── 5. 飞书推送 ──────────────────────────────────────────────────
    if new_details:
        try:
            push_analysis_details(new_details)
        except Exception:
            logger.exception("飞书推送异常（已忽略）")

    # ── 6. 健康检查 + 刷新静态站 ─────────────────────────────────────
    _health_checker.check_and_alert()
    if new_details:
        _refresh_feed()

    logger.info("轮次结束")


def main() -> None:
    parser = argparse.ArgumentParser(description="流水线轮询守护进程（默认 20s 一轮）")
    parser.add_argument("--once", action="store_true", help="只执行一轮后退出（运维验证）")
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="覆盖轮询间隔秒数（默认读 POLL_INTERVAL_SECONDS，缺省 20）",
    )
    args = parser.parse_args()

    interval = args.interval if args.interval is not None else POLL_INTERVAL_SECONDS

    # 单实例保护（常驻模式）；--once 模式用于运维验证，不加锁
    _lock = None
    if not args.once:
        _lock = acquire_single_instance_lock("financial_news_daemon")
        if _lock is None:
            if sys.platform == "win32":
                logger.warning("Windows 无 flock，单实例锁不可用，继续运行")
            else:
                logger.error("已有 pipeline_daemon 实例在运行，本次退出")
                return

    logger.info(
        "守护进程启动: interval=%ss window=%smin v2=%s once=%s",
        interval, FETCH_WINDOW_MINUTES, settings.doubao.use_prompts_v2, args.once,
    )

    if args.once:
        run_pipeline_round()
        return

    while True:
        round_start = time.monotonic()
        try:
            run_pipeline_round()
        except KeyboardInterrupt:
            logger.info("收到中断，退出")
            break
        except Exception:
            # run_pipeline_round 内部已兜底，这里防御编程层面未捕获的异常
            logger.exception("轮次出现未预期异常（继续下一轮）")
        elapsed = time.monotonic() - round_start
        sleep_s = max(0.0, interval - elapsed)
        if sleep_s > 0:
            time.sleep(sleep_s)


if __name__ == "__main__":
    main()
