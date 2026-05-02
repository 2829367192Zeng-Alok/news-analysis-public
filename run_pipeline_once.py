# -*- coding: utf-8 -*-
"""
????????????????? ? ?? ? ?????
???????????????????????????????? token ???
???? pipeline_report.txt????????
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


def _sum_usage(usages: list) -> dict:
    """??????? token ???"""
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
    report_lines.append("???????????????")
    report_lines.append(f"????: {started}")
    report_lines.append("=" * 60)

    # ?? 1???? 10 ???? ? raw_news
    logger.info("?? 1???? 10 ???? ? raw_news")
    t0 = time.perf_counter()
    try:
        new_raw, new_raw_hashes = fetch_latest_news(minutes=10)
        new_raw_count = len(new_raw)
        step1_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 1] ???? 10 ???? raw_news")
        report_lines.append(f"  ??: {step1_seconds:.2f} ?")
        report_lines.append(f"  ?? raw_news: {new_raw_count} ?")
    except Exception as e:
        step1_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 1] ?? ? raw_news  ??")
        report_lines.append(f"  ??: {step1_seconds:.2f} ?")
        report_lines.append(f"  ??: {e}")
        logger.exception("?? 1 ??")

    # ???????????????? AI API
    if new_raw_count == 0:
        report_lines.append("")
        report_lines.append("???????????????????? AI API??")
        report_lines.append("-" * 60)
        report_lines.append("??")
        report_lines.append(f"  ???: {step1_seconds:.2f} ?")
        report_lines.append("=" * 60)
        report_path = Path(__file__).resolve().parent / "pipeline_report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        logger.info("?????: %s", report_path)
        try:
            import sys
            if sys.platform == "win32":
                import os
                os.startfile(str(report_path))
            else:
                import subprocess
                subprocess.run(["xdg-open", str(report_path)], check=False)
        except Exception as e:
            logger.warning("??????????: %s", e)
        return

    # ?? 2???????????????? ? selected_news
    logger.info("?? 2??????????? selected_news")
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
        report_lines.append("[?? 2] ?? ? selected_news")
        report_lines.append(f"  ??: {step2_seconds:.2f} ?")
        report_lines.append(f"  ?? selected_news: {new_selected_count} ?")
        report_lines.append(
            f"  Token ??: input={u2['input_tokens']}, output={u2['output_tokens']}, total={u2['total_tokens']}"
        )
    except Exception as e:
        step2_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 2] ?? ? selected_news  ??")
        report_lines.append(f"  ??: {step2_seconds:.2f} ?")
        report_lines.append(f"  ??: {e}")
        logger.exception("?? 2 ??")

    # ?? 3????? ? news_analysis_detail??? token?
    logger.info("?? 3????? ? news_analysis_detail")
    t0 = time.perf_counter()
    try:
        analyze_token_list: list = []
        new_details = analyze_news(limit=50, token_accumulator=analyze_token_list)
        new_detail_count = len(new_details)
        step3_seconds = time.perf_counter() - t0
        step3_tokens = analyze_token_list
        u3 = _sum_usage(step3_tokens)
        report_lines.append("")
        report_lines.append("[?? 3] ???? ? news_analysis_detail")
        report_lines.append(f"  ??: {step3_seconds:.2f} ?")
        report_lines.append(f"  ?? news_analysis_detail: {new_detail_count} ?")
        report_lines.append(
            f"  Token ??: input={u3['input_tokens']}, output={u3['output_tokens']}, total={u3['total_tokens']}"
        )
    except Exception as e:
        step3_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 3] ???? ? news_analysis_detail  ??")
        report_lines.append(f"  ??: {step3_seconds:.2f} ?")
        report_lines.append(f"  ??: {e}")
        logger.exception("?? 3 ??")

    # ??
    total_seconds = step1_seconds + step2_seconds + step3_seconds
    u2 = _sum_usage(step2_tokens)
    u3 = _sum_usage(step3_tokens)
    report_lines.append("")
    report_lines.append("-" * 60)
    report_lines.append("??")
    report_lines.append(f"  ???: {total_seconds:.2f} ?")
    report_lines.append(
        f"  ?? 2 ?? Token ??: {u2['total_tokens']} (input={u2['input_tokens']}, output={u2['output_tokens']})"
    )
    report_lines.append(
        f"  ?? 3 ?? Token ??: {u3['total_tokens']} (input={u3['input_tokens']}, output={u3['output_tokens']})"
    )
    report_lines.append("=" * 60)

    report_path = Path(__file__).resolve().parent / "pipeline_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("?????: %s", report_path)

    # ????
    try:
        import subprocess
        import sys
        if sys.platform == "win32":
            import os
            os.startfile(str(report_path))
        else:
            subprocess.run(["xdg-open", str(report_path)], check=False)
    except Exception as e:
        logger.warning("??????????: %s", e)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
???????????????????????????????
?????????????????????????????????token ???
???? pipeline_report.txt ????????
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from news_fetcher import fetch_latest_news
from utils import now_beijing_naive
from news_filter import filter_news
from news_analyzer import analyze_news

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _sum_usage(usages: list) -> dict:
    """??????? token ????""
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
    report_lines.append("????????????????)
    report_lines.append(f"????? {started}")
    report_lines.append("=" * 60)

    # ?? 1???? 7 ???? ??raw_news
    logger.info("?? 1???? 7 ???? ??raw_news")
    t0 = time.perf_counter()
    try:
        new_raw, new_raw_hashes = fetch_latest_news(minutes=10)
        new_raw_count = len(new_raw)
        step1_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 1] ???? 7 ???? raw_news")
        report_lines.append(f"  ??: {step1_seconds:.2f} ??)
        report_lines.append(f"  ?? raw_news: {new_raw_count} ??)
    except Exception as e:
        step1_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 1] ?? ??raw_news  ??")
        report_lines.append(f"  ??: {step1_seconds:.2f} ??)
        report_lines.append(f"  ??: {e}")
        logger.exception("?? 1 ??")

    # ???????????????? AI API
    if new_raw_count == 0:
        report_lines.append("")
        report_lines.append("???????????????????? AI API???)
        report_lines.append("-" * 60)
        report_lines.append("???)
        report_lines.append(f"  ???: {step1_seconds:.2f} ??)
        report_lines.append("=" * 60)
        report_path = Path(__file__).resolve().parent / "pipeline_report.txt"
        report_path.write_text("\n".join(report_lines), encoding="utf-8")
        logger.info("?????? %s", report_path)
        try:
            import sys
            if sys.platform == "win32":
                import os
                os.startfile(str(report_path))
            else:
                import subprocess
                subprocess.run(["xdg-open", str(report_path)], check=False)
        except Exception as e:
            logger.warning("??????????: %s", e)
        return

    # ?? 2???????????????????selected_news
    logger.info("?? 2????????????selected_news")
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
        report_lines.append("[?? 2] ?????selected_news")
        report_lines.append(f"  ??: {step2_seconds:.2f} ??)
        report_lines.append(f"  ?? selected_news: {new_selected_count} ??)
        report_lines.append(
            f"  Token ??? input={u2['input_tokens']}, output={u2['output_tokens']}, total={u2['total_tokens']}"
        )
    except Exception as e:
        step2_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 2] ?????selected_news  ??")
        report_lines.append(f"  ??: {step2_seconds:.2f} ??)
        report_lines.append(f"  ??: {e}")
        logger.exception("?? 2 ??")

    # ?? 3????????news_analysis_detail????token??
    logger.info("?? 3????????news_analysis_detail")
    t0 = time.perf_counter()
    try:
        analyze_token_list: list = []
        new_details = analyze_news(limit=50, token_accumulator=analyze_token_list)
        new_detail_count = len(new_details)
        step3_seconds = time.perf_counter() - t0
        step3_tokens = analyze_token_list
        u3 = _sum_usage(step3_tokens)
        report_lines.append("")
        report_lines.append("[?? 3] ???? ??news_analysis_detail")
        report_lines.append(f"  ??: {step3_seconds:.2f} ??)
        report_lines.append(f"  ?? news_analysis_detail: {new_detail_count} ??)
        report_lines.append(
            f"  Token ??? input={u3['input_tokens']}, output={u3['output_tokens']}, total={u3['total_tokens']}"
        )
    except Exception as e:
        step3_seconds = time.perf_counter() - t0
        report_lines.append("")
        report_lines.append("[?? 3] ???? ??news_analysis_detail  ??")
        report_lines.append(f"  ??: {step3_seconds:.2f} ??)
        report_lines.append(f"  ??: {e}")
        logger.exception("?? 3 ??")

    # ???
    total_seconds = step1_seconds + step2_seconds + step3_seconds
    u2 = _sum_usage(step2_tokens)
    u3 = _sum_usage(step3_tokens)
    report_lines.append("")
    report_lines.append("-" * 60)
    report_lines.append("???)
    report_lines.append(f"  ???: {total_seconds:.2f} ??)
    report_lines.append(f"  ?? 2 ???Token ??: {u2['total_tokens']} (input={u2['input_tokens']}, output={u2['output_tokens']})")
    report_lines.append(f"  ?? 3 ?? Token ??: {u3['total_tokens']} (input={u3['input_tokens']}, output={u3['output_tokens']})")
    report_lines.append("=" * 60)

    report_path = Path(__file__).resolve().parent / "pipeline_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    logger.info("?????? %s", report_path)

    # ????
    try:
        import subprocess
        import sys
        if sys.platform == "win32":
            import os
            os.startfile(str(report_path))
        else:
            subprocess.run(["xdg-open", str(report_path)], check=False)
    except Exception as e:
        logger.warning("??????????: %s", e)


if __name__ == "__main__":
    main()
