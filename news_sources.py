# -*- coding: utf-8 -*-
"""
新闻来源配置与扩展接口。

- 当前支持：Tushare pro.news()（华尔街见闻、新浪财经），返回的 content 为纯文本正文。
- 新增来源：在 TUSHARE_SOURCES 中追加配置，或实现 BaseNewsFetcher 后注册到 fetcher 工厂。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Protocol

if TYPE_CHECKING:
    from datetime import datetime

# 来源标识（用于存储与去重时的 source 字段）
SOURCE_ID_WALLSTREET = "华尔街见闻"
SOURCE_ID_SINA = "新浪财经"


@dataclass
class TushareSourceConfig:
    """Tushare 新闻来源配置。"""
    source_id: str   # 存库与展示用，如 华尔街见闻 / 新浪财经
    tushare_src: str  # Tushare pro.news() 的 src 参数，如 sina / wallstreetcn


# 默认启用的 Tushare 来源（pro.news 接口：华尔街快讯、新浪资讯）
# 接口返回的 content 即为纯文本新闻正文，直接入库
TUSHARE_SOURCES: List[TushareSourceConfig] = [
    TushareSourceConfig(source_id=SOURCE_ID_WALLSTREET, tushare_src="wallstreetcn"),
    TushareSourceConfig(source_id=SOURCE_ID_SINA, tushare_src="sina"),
]


def get_default_sources() -> List[TushareSourceConfig]:
    """返回默认新闻来源列表。"""
    return list(TUSHARE_SOURCES)


def get_sources_by_ids(source_ids: Optional[List[str]] = None) -> List[TushareSourceConfig]:
    """
    按 source_id 过滤来源；None 表示全部默认来源。
    """
    all_sources = get_default_sources()
    if not source_ids:
        return all_sources
    id_set = set(source_ids)
    return [s for s in all_sources if s.source_id in id_set]


# ---------- 扩展预留：其他来源的 Fetcher 协议 ----------


class NormalizedNewsRecord:
    """统一的一条新闻记录（用于去重与入库前）。"""
    __slots__ = ("title", "content", "news_datetime_str", "source_id")

    def __init__(
        self,
        title: str,
        content: str,
        news_datetime_str: str,
        source_id: str,
    ):
        self.title = title
        self.content = content
        self.news_datetime_str = news_datetime_str
        self.source_id = source_id


class BaseNewsFetcher(Protocol):
    """未来其他新闻来源（非 Tushare）可实现此协议并注册，返回统一格式。"""

    def fetch(
        self,
        start_time: "datetime",  # noqa: F821
        end_time: "datetime",    # noqa: F821
        limit: Optional[int] = None,
    ) -> List[NormalizedNewsRecord]:
        ...


# 可在此注册自定义 Fetcher： fetcher_registry: Dict[str, BaseNewsFetcher] = {}
# 当前仅使用 Tushare，由 news_fetcher 直接调用 major_news。
