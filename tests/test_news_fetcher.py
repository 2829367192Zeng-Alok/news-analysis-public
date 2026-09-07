# -*- coding: utf-8 -*-
"""
新闻采集模块测试：来源配置、去重逻辑、命令行。

不依赖真实 Tushare Token 的单元测试（mock）；集成测试需在配置好 .env 的环境下运行。
"""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

# 将项目根加入 path
import os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

import pytest


def test_compute_content_hash():
    from utils import compute_content_hash
    h1 = compute_content_hash("标题", "内容")
    h2 = compute_content_hash("标题", "内容")
    assert h1 == h2
    assert compute_content_hash("A", "B") != compute_content_hash("B", "A")
    # 统一 blake2b 实现：32 bytes -> 64 hex 字符
    assert len(h1) == 64
    # 不同标题但内容相同时不应判为同一条
    assert compute_content_hash("A", "B") != compute_content_hash("B", "A")


def test_compute_content_hash_legacy_md5():
    """旧 MD5 实现保留给迁移对比用，两者结果必须不同（分隔符与算法均不同）。"""
    from utils import compute_content_hash, compute_content_hash_legacy_md5
    assert len(compute_content_hash_legacy_md5("A", "B")) == 32
    assert compute_content_hash("A", "B") != compute_content_hash_legacy_md5("A", "B")


def test_parse_news_datetime():
    from utils import parse_news_datetime
    assert parse_news_datetime("2025-01-01 12:00:00") is not None
    assert parse_news_datetime("20250101120000") is not None
    assert parse_news_datetime("") is None
    assert parse_news_datetime("invalid") is None


def test_sources_config():
    from news_sources import (
        SOURCE_ID_WALLSTREET,
        SOURCE_ID_SINA,
        get_default_sources,
        get_sources_by_ids,
        TushareSourceConfig,
    )
    default = get_default_sources()
    assert len(default) >= 2
    ids = [s.source_id for s in default]
    assert SOURCE_ID_WALLSTREET in ids
    assert SOURCE_ID_SINA in ids
    filtered = get_sources_by_ids([SOURCE_ID_SINA])
    assert len(filtered) == 1
    # source_id（存库/展示）与 tushare_src（API 参数）是两个字段，勿混淆
    assert filtered[0].source_id == SOURCE_ID_SINA
    assert filtered[0].tushare_src == "sina"
    assert get_sources_by_ids(None) == default


def test_dedupe_by_hash():
    from news_fetcher import _dedupe_by_hash
    from datetime import datetime
    now = datetime.now()
    # 两条相同内容应只留一条
    recs = [
        ("标题", "内容", now, "新浪财经"),
        ("标题", "内容", now, "新浪财经"),
    ]
    out = _dedupe_by_hash(recs)
    assert len(out) == 1
    # 不同内容保留两条
    recs2 = [
        ("A", "B", now, "新浪财经"),
        ("C", "D", now, "华尔街见闻"),
    ]
    out2 = _dedupe_by_hash(recs2)
    assert len(out2) == 2


def test_normalize_record():
    from news_fetcher import _normalize_record
    from datetime import datetime
    now = datetime.now()
    r = {"title": " 标题 ", "content": " 正文 ", "pub_time": "2025-03-01 10:00:00", "src": "新浪财经"}
    t = _normalize_record(r, "新浪财经", now)
    assert t is not None
    title, content, dt, src = t
    assert title == "标题"
    assert content == "正文"
    assert src == "新浪财经"
    assert dt.year == 2025
    # 无 title 用 content 前 80 字
    t2 = _normalize_record({"content": "只有正文"}, "新浪", now)
    assert t2 is not None
    assert t2[0] == "只有正文"
    # 空行
    assert _normalize_record({}, "x", now) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
