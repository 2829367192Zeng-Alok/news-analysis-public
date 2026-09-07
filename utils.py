import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

# 北京时间 UTC+8，用于 create_time / news_datetime 等统一按北京时间存储
TZ_BEIJING = timezone(timedelta(hours=8))


def now_beijing_naive() -> datetime:
    """返回当前北京时间（naive datetime），用于统一写入 create_time、news_datetime 等字段。"""
    return datetime.now(TZ_BEIJING).replace(tzinfo=None)


def compute_content_hash(title: str, content: str) -> str:
    """
    基于标题和正文计算内容哈希，用于跨来源去重。

    统一实现：blake2b（64 hex 字符）。
    历史上本函数曾是 MD5 实现，news_fetcher 曾自带 blake2b 副本；两者已合并到这里，
    采集、回补、评估脚本必须全部经由本函数计算，禁止再各自实现。
    """
    raw = f"{title}\n{content}".encode("utf-8", errors="replace")
    return hashlib.blake2b(raw, digest_size=32).hexdigest()  # 32 bytes = 64 hex chars


def compute_content_hash_legacy_md5(title: str, content: str) -> str:
    """
    旧版 MD5 内容哈希（32 hex）。仅用于迁移脚本对比/排查历史数据，勿在生产代码中使用。
    分隔符为 "::"，与当前 blake2b 实现的 "\\n" 不同，两者结果不可互换。
    """
    m = hashlib.md5()
    key = (title or "") + "::" + (content or "")
    m.update(key.encode("utf-8"))
    return m.hexdigest()


def parse_news_datetime(dt_str: str) -> Optional[datetime]:
    """将 Tushare 等返回的时间字符串解析为 datetime（接口一般为北京时间，返回 naive 即按北京时间理解）。"""
    if not dt_str or not isinstance(dt_str, str):
        return None
    dt_str = dt_str.strip()
    # 去掉末尾 .0 等毫秒（部分接口返回）
    if dt_str and dt_str[-2:] == ".0":
        dt_str = dt_str[:-2]
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y%m%d%H%M%S",
        "%Y-%m-%d",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None

