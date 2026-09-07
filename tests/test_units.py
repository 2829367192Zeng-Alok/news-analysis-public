# -*- coding: utf-8 -*-
"""
纯函数级单元测试：筛选/分析字段规范化、token 汇总、告警抑制、ISO 时间解析。
不依赖真实 API / 数据库（mock 或纯内存），可在无密钥环境运行。
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

import pytest


# ---------- news_filter 辅助函数 ----------

def test_first_dict_from_list():
    from news_filter import _first_dict_from_list

    assert _first_dict_from_list([1, "x", {"a": 1}]) == {"a": 1}
    assert _first_dict_from_list([1, [2, {"b": 2}]]) == {"b": 2}
    assert _first_dict_from_list([1, [2, 3]]) == {}
    assert _first_dict_from_list([]) == {}


# ---------- news_analyzer 规范化 ----------

def test_norm_list():
    from news_analyzer import _norm_list

    assert _norm_list(None) is None
    assert _norm_list(["a", "b"]) == ["a", "b"]
    assert _norm_list([1, 2]) == ["1", "2"]
    # 中文逗号分隔的字符串应拆成列表
    assert _norm_list("a，b, c") == ["a", "b", "c"]
    assert _norm_list("   ") is None


def test_norm_str():
    from news_analyzer import _norm_str

    assert _norm_str(None) is None
    assert _norm_str("  hello  ") == "hello"
    assert _norm_str("") is None
    assert _norm_str(123) == "123"


def test_norm_int():
    from news_analyzer import _norm_int

    assert _norm_int(None) == 0
    assert _norm_int("3") == 3
    assert _norm_int(3.9) == 3
    assert _norm_int("abc") == 0


# ---------- utils.sum_token_usage ----------

def test_sum_token_usage():
    from utils import sum_token_usage

    assert sum_token_usage([]) == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    usages = [
        {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60},
    ]
    assert sum_token_usage(usages)["total_tokens"] == 180
    # 缺 total_tokens 时由 input+output 补齐
    assert sum_token_usage([{"input_tokens": 3, "output_tokens": 5}])["total_tokens"] == 8
    # 非 dict 条目应忽略
    assert sum_token_usage([None, "x", {"input_tokens": 1}])["input_tokens"] == 1


# ---------- feishu_webhook.alert_service 告警抑制 ----------

def test_alert_suppression_window():
    from feishu_webhook import alert_service
    from feishu_webhook.alert_service import PipelineHealthChecker
    from utils import now_beijing_naive

    checker = PipelineHealthChecker()
    now = now_beijing_naive()
    checker._last_alert = {}

    suppress_min = alert_service._SUPPRESS_MIN
    key = "api_error:步骤2筛选:429"
    # 从未告警 -> 不抑制
    assert checker._is_suppressed(key) is False

    # 刚刚告警 -> 抑制
    checker._last_alert[key] = now
    assert checker._is_suppressed(key) is True

    # 超过抑制窗口 -> 不再抑制（阈值取自模块实际配置）
    checker._last_alert[key] = now - timedelta(minutes=suppress_min + 1)
    assert checker._is_suppressed(key) is False


# ---------- app._parse_dt（ISO 时间解析） ----------

def test_parse_dt_iso_formats():
    from app import _parse_dt

    assert _parse_dt("2026-09-07T12:00:00") is not None
    assert _parse_dt("2026-09-07 12:00:00") is not None
    assert _parse_dt("2026-09-07") is not None
    # JS toISOString() 风格：带 Z 与毫秒
    dt = _parse_dt("2026-09-07T12:00:00.123Z")
    assert dt is not None
    assert dt.microsecond == 123000
    assert dt.tzinfo is None  # 统一转为 naive，与库内北京时间口径一致
    # 非法输入
    assert _parse_dt("") is None
    assert _parse_dt(None) is None
    assert _parse_dt("not-a-date") is None
