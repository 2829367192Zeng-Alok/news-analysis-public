#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from news_analyzer import call_doubao_analyze_api


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="读取 selected_news CSV 并调用 news_analyzer 生成 Markdown 分析结果"
    )
    parser.add_argument(
        "--input-csv",
        default=str(ROOT / "news" / "selected_news_latest_20.csv"),
        help="输入 CSV 路径",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=1,
        help="起始行号（从1开始，默认1）",
    )
    parser.add_argument(
        "--end-row",
        type=int,
        default=3,
        help="结束行号（从1开始，默认3）",
    )
    parser.add_argument(
        "--output-md",
        default="",
        help="输出 Markdown 文件路径（默认写到 news 目录并带时间戳）",
    )
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"未找到输入文件: {input_csv}")
    if args.start_row < 1 or args.end_row < args.start_row:
        raise ValueError("参数范围无效：需满足 start-row >= 1 且 end-row >= start-row")

    with input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    selected = rows[args.start_row - 1 : args.end_row]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_md = (
        Path(args.output_md)
        if args.output_md
        else ROOT / "news" / f"selected_news_analysis_{args.start_row}_{args.end_row}_{ts}.md"
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)

    token_usage: list[dict[str, int]] = []
    lines: list[str] = [
        "# Selected News 分析结果",
        "",
        f"- 输入文件: `{input_csv}`",
        f"- 分析范围: 第 {args.start_row} 到 {args.end_row} 条",
        f"- 实际条数: {len(selected)}",
        "",
    ]

    for idx, row in enumerate(selected, start=args.start_row):
        title = (row.get("title") or "").strip()
        content = (row.get("content") or "").strip()
        lines.append(f"## 第 {idx} 条")
        lines.append("")
        lines.append(f"- 标题: {title}")
        lines.append(f"- 来源: {row.get('source', '')}")
        lines.append(f"- 时间: {row.get('news_datetime', '')}")
        lines.append("")

        if not title and not content:
            lines.append("> 跳过：标题和内容均为空")
            lines.append("")
            continue

        try:
            result = call_doubao_analyze_api(
                title=title,
                content=content,
                token_accumulator=token_usage,
            )
            lines.append("### 分析 JSON")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(result, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")
            lines.append("### 关键信息摘录")
            lines.append("")
            for k in [
                "relevance",
                "direction",
                "impact",
                "shorttime",
                "midtime",
                "longtime",
                "insight",
                "conclusion",
            ]:
                lines.append(f"- {k}: {_fmt(result.get(k))}")
            lines.append("")
        except Exception as e:
            lines.append(f"> 分析失败: {e}")
            lines.append("")

    if token_usage:
        # doubao_client 返回的用量键为 input_tokens / output_tokens / total_tokens
        prompt_tokens = sum(int(u.get("input_tokens", 0)) for u in token_usage)
        completion_tokens = sum(int(u.get("output_tokens", 0)) for u in token_usage)
        total_tokens = sum(int(u.get("total_tokens", 0)) for u in token_usage)
        lines.extend(
            [
                "## Token 统计",
                "",
                f"- prompt_tokens: {prompt_tokens}",
                f"- completion_tokens: {completion_tokens}",
                f"- total_tokens: {total_tokens}",
                "",
            ]
        )

    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"输出文件: {output_md}")


if __name__ == "__main__":
    main()
