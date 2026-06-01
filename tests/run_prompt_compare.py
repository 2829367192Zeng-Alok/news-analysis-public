#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在同一批原始新闻上对比 prompts.py（旧）与 prompts_new.py（新）的筛选 + 详细分析结果，
输出 tests/prompts_test.csv。

用法（在项目根目录）：
  python tests/run_prompt_compare.py
  python tests/run_prompt_compare.py --limit 10 --baseline config/macro_baseline.yaml
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 先于 config 加载项目根 .env，避免从其他 cwd 启动时读不到密钥
try:
    import dotenv  # type: ignore

    dotenv.load_dotenv(ROOT / ".env", override=True)
    dotenv.load_dotenv(Path.home() / ".financial_news_analysis.env", override=True)
except ImportError:
    pass

from config import settings
from doubao_client import chat_with_usage, parse_json_from_text
from macro_baseline import load_macro_baseline
import prompts as prompts_old
import prompts_new
from prompts_new import format_system_prompt


def _first_dict_from_list(lst: list) -> dict:
    for x in lst:
        if isinstance(x, dict):
            return x
        if isinstance(x, list):
            found = _first_dict_from_list(x)
            if found:
                return found
    return {}


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    if not isinstance(obj, dict):
        return default
    return obj.get(key, default)


def call_doubao_filter_api(
    title: str,
    content: str,
    filter_template: str,
    token_accumulator: Optional[List[Dict[str, int]]] = None,
) -> Dict[str, Any]:
    """与 news_filter 逻辑一致，但不依赖 DB / models。"""
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在项目根 .env 或环境变量中设置")
    default = {"relevance": False, "direction": 0, "impact": 0}
    try:
        user_text = filter_template.format(
            title=title, content=(content or "")[:8000]
        )
        model_filter = (
            settings.doubao.model_id_filter or settings.doubao.model_id or ""
        ).strip() or None
        raw_text, usage = chat_with_usage(
            model=model_filter, user_text=user_text, timeout=30
        )
        if token_accumulator is not None:
            token_accumulator.append(usage)
        data = parse_json_from_text(raw_text)
        if not isinstance(data, dict):
            data = _first_dict_from_list(data) if isinstance(data, list) else {}
        if not isinstance(data, dict):
            data = {}

        def _bool(v) -> bool:
            if v is None:
                return False
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("true", "1", "是", "yes", "相关")

        def _int(v: Any, default_val: int = 0) -> int:
            try:
                return int(v) if v is not None else default_val
            except (TypeError, ValueError):
                return default_val

        relevance = _bool(
            _safe_get(data, "relevance")
            or _safe_get(data, "相关")
            or _safe_get(data, "is_relevant")
            or _safe_get(data, "relevant")
        )
        direction = _int(
            _safe_get(data, "direction")
            or _safe_get(data, "方向")
            or _safe_get(data, "direction_score")
        )
        impact = _int(
            _safe_get(data, "impact")
            or _safe_get(data, "影响程度")
            or _safe_get(data, "impact_level")
        )
        return {"relevance": relevance, "direction": direction, "impact": impact}
    except Exception as e:
        return {**default, "_error": str(e)}


def call_doubao_analyze_api(
    title: str,
    content: str,
    analyze_template: str,
    token_accumulator: Optional[List[Dict[str, int]]] = None,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在项目根 .env 或环境变量中设置")
    analyze_timeout = 240
    user_text = analyze_template.format(
        title=title,
        content=(content or "")[:12000],
    )
    model_analyze = (
        settings.doubao.model_id_analyze or settings.doubao.model_id or ""
    ).strip() or None
    raw_text, usage = chat_with_usage(
        model=model_analyze,
        user_text=user_text,
        timeout=analyze_timeout,
        max_retries=0,
        system_text=system_prompt,
    )
    if token_accumulator is not None:
        token_accumulator.append(usage)
    return parse_json_from_text(raw_text)


def _json_cell(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False)


def _filter_summary(
    old_r: Dict[str, Any], new_r: Dict[str, Any]
) -> str:
    parts: List[str] = []
    if bool(old_r.get("relevance")) != bool(new_r.get("relevance")):
        parts.append(
            f"relevance old={old_r.get('relevance')} new={new_r.get('relevance')}"
        )
    if int(old_r.get("direction") or 0) != int(new_r.get("direction") or 0):
        parts.append(
            f"direction old={old_r.get('direction')} new={new_r.get('direction')}"
        )
    if int(old_r.get("impact") or 0) != int(new_r.get("impact") or 0):
        parts.append(f"impact old={old_r.get('impact')} new={new_r.get('impact')}")
    return "; ".join(parts) if parts else "filter_same"


def _analyze_summary(
    old_a: Optional[Dict[str, Any]], new_a: Optional[Dict[str, Any]]
) -> str:
    if old_a is None and new_a is None:
        return "both_skipped"
    if old_a is None:
        return "old_skipped"
    if new_a is None:
        return "new_skipped"
    parts: List[str] = []
    if int(old_a.get("direction") or 0) != int(new_a.get("direction") or 0):
        parts.append(
            f"direction old={old_a.get('direction')} new={new_a.get('direction')}"
        )
    if int(old_a.get("impact") or 0) != int(new_a.get("impact") or 0):
        parts.append(f"impact old={old_a.get('impact')} new={new_a.get('impact')}")
    oc = (old_a.get("conclusion") or "").strip()
    nc = (new_a.get("conclusion") or "").strip()
    if oc != nc:
        parts.append("conclusion_diff")
    return "; ".join(parts) if parts else "analyze_same"


def _usage_total(usages: List[Dict[str, int]]) -> int:
    return sum(int(u.get("total_tokens") or 0) for u in usages)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="对比旧/新提示词：筛选 + 分析，写入 tests/prompts_test.csv"
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=ROOT / "news" / "raw_news_recent_30m.csv",
        help="原始新闻 CSV",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=ROOT / "tests" / "prompts_test.csv",
        help="对比结果输出路径",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="宏观基线 YAML/JSON；省略则按 macro_baseline.load_macro_baseline 默认查找",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="最多处理条数，0 表示全部（注意 API 费用）",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="跳过前 N 条（0 表示从头）",
    )
    args = parser.parse_args()

    if not settings.doubao.api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY")

    if not args.input_csv.exists():
        raise FileNotFoundError(f"未找到输入: {args.input_csv}")

    baseline_path = args.baseline
    if baseline_path is None and settings.macro_baseline_path:
        baseline_path = Path(settings.macro_baseline_path)
    baseline = load_macro_baseline(baseline_path)
    system_prompt = format_system_prompt(baseline)

    with args.input_csv.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if args.offset:
        rows = rows[args.offset :]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "row_index",
        "content_hash",
        "title",
        "source",
        "news_datetime",
        "old_filter_relevance",
        "old_filter_direction",
        "old_filter_impact",
        "old_filter_error",
        "new_filter_relevance",
        "new_filter_direction",
        "new_filter_impact",
        "new_filter_error",
        "filter_diff_summary",
        "old_ran_analyze",
        "new_ran_analyze",
        "old_analyze_direction",
        "old_analyze_impact",
        "old_analyze_conclusion",
        "new_analyze_direction",
        "new_analyze_impact",
        "new_analyze_conclusion",
        "new_analyze_confidence",
        "new_analyze_uncertain",
        "analyze_diff_summary",
        "old_analyze_json",
        "new_analyze_json",
        "old_filter_tokens_total",
        "new_filter_tokens_total",
        "old_analyze_tokens_total",
        "new_analyze_tokens_total",
    ]

    with args.output_csv.open("w", encoding="utf-8-sig", newline="") as out:
        w = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()

        for i, row in enumerate(rows, start=1):
            title = (row.get("title") or "").strip()
            content = (row.get("content") or "").strip()
            chash = (row.get("content_hash") or "").strip()
            src = (row.get("source") or "").strip()
            ndt = (row.get("news_datetime") or "").strip()

            old_f_tokens: List[Dict[str, int]] = []
            new_f_tokens: List[Dict[str, int]] = []
            old_a_tokens: List[Dict[str, int]] = []
            new_a_tokens: List[Dict[str, int]] = []

            old_filter = call_doubao_filter_api(
                title,
                content,
                prompts_old.FILTER_PROMPT_TEMPLATE,
                token_accumulator=old_f_tokens,
            )
            old_ferr = old_filter.pop("_error", None)

            new_filter = call_doubao_filter_api(
                title,
                content,
                prompts_new.FILTER_PROMPT_TEMPLATE,
                token_accumulator=new_f_tokens,
            )
            new_ferr = new_filter.pop("_error", None)

            old_rel = bool(old_filter.get("relevance"))
            new_rel = bool(new_filter.get("relevance"))

            old_analyze: Optional[Dict[str, Any]] = None
            new_analyze: Optional[Dict[str, Any]] = None
            old_a_err: Optional[str] = None
            new_a_err: Optional[str] = None

            if old_rel:
                try:
                    old_analyze = call_doubao_analyze_api(
                        title,
                        content,
                        prompts_old.ANALYZE_PROMPT_TEMPLATE,
                        token_accumulator=old_a_tokens,
                        system_prompt=None,
                    )
                except Exception as e:
                    old_a_err = str(e)

            if new_rel:
                try:
                    new_analyze = call_doubao_analyze_api(
                        title,
                        content,
                        prompts_new.ANALYZE_PROMPT_TEMPLATE,
                        token_accumulator=new_a_tokens,
                        system_prompt=system_prompt,
                    )
                except Exception as e:
                    new_a_err = str(e)

            diff_parts: List[str] = []
            if old_a_err:
                diff_parts.append(f"old_analyze_error:{old_a_err[:120]}")
            if new_a_err:
                diff_parts.append(f"new_analyze_error:{new_a_err[:120]}")
            if not old_a_err and not new_a_err:
                diff_parts.append(_analyze_summary(old_analyze, new_analyze))
            analyze_diff = "; ".join(p for p in diff_parts if p)

            rec = {
                "row_index": str(args.offset + i),
                "content_hash": chash,
                "title": title[:500],
                "source": src,
                "news_datetime": ndt,
                "old_filter_relevance": old_rel,
                "old_filter_direction": old_filter.get("direction", ""),
                "old_filter_impact": old_filter.get("impact", ""),
                "old_filter_error": old_ferr or "",
                "new_filter_relevance": new_rel,
                "new_filter_direction": new_filter.get("direction", ""),
                "new_filter_impact": new_filter.get("impact", ""),
                "new_filter_error": new_ferr or "",
                "filter_diff_summary": _filter_summary(old_filter, new_filter),
                "old_ran_analyze": old_rel,
                "new_ran_analyze": new_rel,
                "old_analyze_direction": (
                    old_analyze.get("direction", "") if old_analyze else ""
                ),
                "old_analyze_impact": old_analyze.get("impact", "") if old_analyze else "",
                "old_analyze_conclusion": (
                    (old_analyze.get("conclusion") or "") if old_analyze else ""
                ),
                "new_analyze_direction": (
                    new_analyze.get("direction", "") if new_analyze else ""
                ),
                "new_analyze_impact": (
                    new_analyze.get("impact", "") if new_analyze else ""
                ),
                "new_analyze_conclusion": (
                    (new_analyze.get("conclusion") or "") if new_analyze else ""
                ),
                "new_analyze_confidence": (
                    new_analyze.get("confidence", "") if new_analyze else ""
                ),
                "new_analyze_uncertain": (
                    new_analyze.get("uncertain", "") if new_analyze else ""
                ),
                "analyze_diff_summary": analyze_diff,
                "old_analyze_json": _json_cell(old_analyze) if old_analyze else "",
                "new_analyze_json": _json_cell(new_analyze) if new_analyze else "",
                "old_filter_tokens_total": _usage_total(old_f_tokens),
                "new_filter_tokens_total": _usage_total(new_f_tokens),
                "old_analyze_tokens_total": _usage_total(old_a_tokens),
                "new_analyze_tokens_total": _usage_total(new_a_tokens),
            }
            if old_a_err:
                rec["old_analyze_json"] = json.dumps(
                    {"_error": old_a_err}, ensure_ascii=False
                )
            if new_a_err:
                rec["new_analyze_json"] = json.dumps(
                    {"_error": new_a_err}, ensure_ascii=False
                )

            w.writerow(rec)
            out.flush()

    print(f"已写入: {args.output_csv}（共 {len(rows)} 条）")


if __name__ == "__main__":
    main()
