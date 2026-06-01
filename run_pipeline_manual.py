# -*- coding: utf-8 -*-
"""
流水线脚本 - 手动执行版（可配置采集窗口）。
采集 -> 筛选 -> 详细分析，结果写入 pipeline_report.txt，本机可自动打开。
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from news_analyzer import analyze_news
from feishu_webhook import push_analysis_details
from utils import now_beijing_naive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ========== 采集窗口（可修改）==========
# 单位：分钟。支持小数。可通过环境变量 FETCH_WINDOW_MINUTES 覆盖（供阿里云定时触发用）。
# 示例：1=1分钟, 10=10分钟, 60=1小时, 600=10小时
FETCH_WINDOW_MINUTES = float(os.environ.get("FETCH_WINDOW_MINUTES", "60"))
# ========================================


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
    report_lines: list[str] = []
    step1_seconds = 0.0
    step2_seconds = 0.0
    step2_tokens: list = []
    step3_seconds = 0.0
    step3_tokens: list = []
    new_raw_count = 0
    new_selected_count = 0
    new_detail_count = 0

    report_lines.append("=" * 60)
    report_lines.append("定时任务流水线执行报告（单次）")
    report_lines.append(f"开始时间: {started}")
    report_lines.append("=" * 60)

    logger.info("步骤 1：采集近 %s 分钟新闻 -> raw_news", FETCH_WINDOW_MINUTES)
    t0 = time.perf_counter()
    try:
        new_raw, new_raw_hashes = fetch_latest_news(minutes=FETCH_WINDOW_MINUTES)
        new_raw_count = len(new_raw)
        step1_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append(f"[步骤 1] 采集（近 {FETCH_WINDOW_MINUTES} 分钟）-> raw_news")
        report_lines.append(f"  耗时: {step1_seconds:.2f} 秒")
        report_lines.append(f"  新增 raw_news: {new_raw_count} 条")
    except Exception as e:
        step1_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[步骤 1] 采集 -> raw_news  失败")
        report_lines.append(f"  耗时: {step1_seconds:.2f} 秒")
        report_lines.append(f"  错误: {e}")
        logger.exception("步骤 1 失败")

    if new_raw_count == 0:
        report_lines.append("")
        report_lines.append("未采集到新新闻，已跳过筛选与分析（未调用 AI API）。")
        report_lines.append("-" * 60)
        report_lines.append("汇总")
        report_lines.append(f"  总耗时: {step1_seconds:.2f} 秒")
        report_lines.append("=" * 60)
        report_path = Path(__file__).resolve().parent / "pipeline_report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        logger.info("报告已写入: %s", report_path)
        try:
            import sys
            if sys.platform == "win32":
                import os
                os.startfile(str(report_path))
            else:
                import subprocess
                subprocess.run(["xdg-open", str(report_path)], check=False)
        except Exception as e:
            logger.warning("无法自动打开报告文件: %s", e)
        return

    logger.info("步骤 2：筛选（仅本批采集）-> selected_news")
    t0 = time.perf_counter()
    try:
        filter_token_list: list = []
        only_hashes = set(new_raw_hashes)
        new_selected = filter_news(
            limit=100,
            token_accumulator=filter_token_list,
            only_content_hashes=only_hashes,
        )
        new_selected_count = len(new_selected)
        step2_seconds = time.perf_counter() - t0
        step2_tokens = filter_token_list
        u2 = _sum_usage(step2_tokens)
        report_lines.append("")
        report_lines.append("[步骤 2] 筛选 -> selected_news")
        report_lines.append(f"  耗时: {step2_seconds:.2f} 秒")
        report_lines.append(f"  新增 selected_news: {new_selected_count} 条")
        report_lines.append(
            f"  Token 消耗: input={u2['input_tokens']}, output={u2['output_tokens']}, total={u2['total_tokens']}"
        )
    except Exception as e:
        step2_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[步骤 2] 筛选 -> selected_news  失败")
        report_lines.append(f"  耗时: {step2_seconds:.2f} 秒")
        report_lines.append(f"  错误: {e}")
        logger.exception("步骤 2 失败")

    logger.info("步骤 3：详细分析 -> news_analysis_detail")
    t0 = time.perf_counter()
    try:
        analyze_token_list: list = []
        new_details = analyze_news(limit=50, token_accumulator=analyze_token_list)
        new_detail_count = len(new_details)
        step3_seconds = time.perf_counter() - t0
        step3_tokens = analyze_token_list
        u3 = _sum_usage(step3_tokens)
        report_lines.append("")
        report_lines.append("[步骤 3] 详细分析 -> news_analysis_detail")
        report_lines.append(f"  耗时: {step3_seconds:.2f} 秒")
        report_lines.append(f"  新增 news_analysis_detail: {new_detail_count} 条")
        report_lines.append(
            f"  Token 消耗: input={u3['input_tokens']}, output={u3['output_tokens']}, total={u3['total_tokens']}"
        )
        try:
            push_analysis_details(new_details)
        except Exception:
            logger.exception("飞书 Webhook 推送环节异常（已忽略，不中断流水线）")
    except Exception as e:
        step3_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[步骤 3] 详细分析 -> news_analysis_detail  失败")
        report_lines.append(f"  耗时: {step3_seconds:.2f} 秒")
        report_lines.append(f"  错误: {e}")
        logger.exception("步骤 3 失败")

    total_seconds = step1_seconds + step2_seconds + step3_seconds
    u2 = _sum_usage(step2_tokens)
    u3 = _sum_usage(step3_tokens)
    report_lines.append("")
    report_lines.append("-" * 60)
    report_lines.append("汇总")
    report_lines.append(f"  总耗时: {total_seconds:.2f} 秒")
    report_lines.append(
        f"  步骤 2 筛选 Token 合计: {u2['total_tokens']} (input={u2['input_tokens']}, output={u2['output_tokens']})"
    )
    report_lines.append(
        f"  步骤 3 分析 Token 合计: {u3['total_tokens']} (input={u3['input_tokens']}, output={u3['output_tokens']})"
    )
    report_lines.append("=" * 60)

    report_path = Path(__file__).resolve().parent / "pipeline_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("报告已写入: %s", report_path)

    try:
        import sys
        if sys.platform == "win32":
            import os
            os.startfile(str(report_path))
        else:
            import subprocess
            subprocess.run(["xdg-open", str(report_path)], check=False)
    except Exception as e:
        logger.warning("无法自动打开报告文件: %s", e)


if __name__ == "__main__":
    main()
