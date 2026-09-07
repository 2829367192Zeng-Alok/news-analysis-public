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

from config import settings
from doubao_client import chat_with_usage, parse_json_from_text
from prompts import ANALYZE_PROMPT_TEMPLATE


# ==============================
# 在这里填写你的“旧提示词 / 新提示词”
# 1) 需要包含 {title} 和 {content} 两个占位符
# 2) 默认 OLD 使用当前项目提示词，NEW 请替换为你的改进版
# ==============================
OLD_PROMPT_TEMPLATE = ANALYZE_PROMPT_TEMPLATE

NEW_PROMPT_TEMPLATE = """
【在此粘贴你的新提示词】
请基于以下新闻进行分析，并只输出 JSON：
标题：{title}
内容：{content}
"""


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _call_analyze_with_prompt(
    title: str,
    content: str,
    prompt_template: str,
    token_accumulator: list[dict[str, int]],
) -> dict[str, Any]:
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在环境变量或 .env 中设置")
    model_analyze = (settings.doubao.model_id_analyze or settings.doubao.model_id or "").strip() or None
    user_text = prompt_template.format(title=title, content=(content or "")[:12000])
    raw_text, usage = chat_with_usage(
        model=model_analyze,
        user_text=user_text,
        timeout=240,
        max_retries=0,
    )
    token_accumulator.append(usage)
    return parse_json_from_text(raw_text)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="对 selected_news CSV 执行旧/新提示词多轮对比，并输出 Markdown"
    )
    parser.add_argument(
        "--input-csv",
        default=str(ROOT / "news" / "selected_news_latest_20.csv"),
        help="输入 CSV 路径",
    )
    parser.add_argument("--start-row", type=int, default=1, help="起始行号（从1开始）")
    parser.add_argument("--end-row", type=int, default=3, help="结束行号（从1开始）")
    parser.add_argument("--rounds", type=int, default=2, help="每条新闻每种提示词运行轮数（默认2）")
    parser.add_argument(
        "--output-md",
        default="",
        help="输出 Markdown 路径（默认写到 news 目录）",
    )
    args = parser.parse_args()

    if args.start_row < 1 or args.end_row < args.start_row:
        raise ValueError("参数范围无效：需满足 start-row >= 1 且 end-row >= start-row")
    if args.rounds < 1:
        raise ValueError("rounds 必须 >= 1")

    input_csv = Path(args.input_csv)
    if not input_csv.exists():
        raise FileNotFoundError(f"未找到输入文件: {input_csv}")

    with input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        all_rows = list(csv.DictReader(f))

    rows = all_rows[args.start_row - 1 : args.end_row]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_md = (
        Path(args.output_md)
        if args.output_md
        else ROOT / "news" / f"prompt_compare_{args.start_row}_{args.end_row}_r{args.rounds}_{ts}.md"
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)

    old_tokens: list[dict[str, int]] = []
    new_tokens: list[dict[str, int]] = []
    lines: list[str] = [
        "# 提示词多轮对比结果",
        "",
        f"- 输入文件: `{input_csv}`",
        f"- 对比范围: 第 {args.start_row} 到 {args.end_row} 条",
        f"- 每组轮数: {args.rounds}",
        f"- 实际样本数: {len(rows)}",
        "",
    ]

    for idx, row in enumerate(rows, start=args.start_row):
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

        lines.append("### 旧提示词结果")
        lines.append("")
        for r in range(1, args.rounds + 1):
            lines.append(f"#### OLD Round {r}")
            try:
                result_old = _call_analyze_with_prompt(
                    title=title,
                    content=content,
                    prompt_template=OLD_PROMPT_TEMPLATE,
                    token_accumulator=old_tokens,
                )
                lines.append("```json")
                lines.append(json.dumps(result_old, ensure_ascii=False, indent=2))
                lines.append("```")
                lines.append("")
            except Exception as e:
                lines.append(f"> OLD Round {r} 失败: {e}")
                lines.append("")

        lines.append("### 新提示词结果")
        lines.append("")
        for r in range(1, args.rounds + 1):
            lines.append(f"#### NEW Round {r}")
            try:
                result_new = _call_analyze_with_prompt(
                    title=title,
                    content=content,
                    prompt_template=NEW_PROMPT_TEMPLATE,
                    token_accumulator=new_tokens,
                )
                lines.append("```json")
                lines.append(json.dumps(result_new, ensure_ascii=False, indent=2))
                lines.append("```")
                lines.append("")
            except Exception as e:
                lines.append(f"> NEW Round {r} 失败: {e}")
                lines.append("")

    def _token_sum(usages: list[dict[str, int]]) -> tuple[int, int, int]:
        # doubao_client 返回的用量键为 input_tokens / output_tokens / total_tokens
        p = sum(int(u.get("input_tokens", 0)) for u in usages)
        c = sum(int(u.get("output_tokens", 0)) for u in usages)
        t = sum(int(u.get("total_tokens", 0)) for u in usages)
        return p, c, t

    old_p, old_c, old_t = _token_sum(old_tokens)
    new_p, new_c, new_t = _token_sum(new_tokens)

    lines.extend(
        [
            "## Token 对比汇总",
            "",
            f"- OLD prompt_tokens: {old_p}",
            f"- OLD completion_tokens: {old_c}",
            f"- OLD total_tokens: {old_t}",
            f"- NEW prompt_tokens: {new_p}",
            f"- NEW completion_tokens: {new_c}",
            f"- NEW total_tokens: {new_t}",
            "",
            "## 观察建议",
            "",
            "- 对比同一条新闻在 OLD/NEW 下的 relevance、direction、impact 是否更稳定",
            "- 对比 shorttime/midtime/longtime 与 conclusion 是否更具体、可执行",
            "- 对比 token 消耗与输出质量，评估新提示词成本收益",
            "",
        ]
    )

    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"输出文件: {output_md}")


if __name__ == "__main__":
    main()
