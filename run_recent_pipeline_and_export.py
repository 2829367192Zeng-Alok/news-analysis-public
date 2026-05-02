#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from news_fetcher import fetch_latest_news
from news_filter import filter_news
from scripts.export_recent_news_csv import main as export_main


def main() -> None:
    print("STEP 1: fetch latest 30 minutes")
    added, hashes = fetch_latest_news(minutes=30)
    print(f"fetched new raw_news: {len(added)}")

    print("STEP 2: filter only fetched hashes")
    selected = filter_news(limit=200, only_content_hashes=set(hashes))
    print(f"new selected_news: {len(selected)}")

    print("STEP 3: export csv")
    # 调用导出脚本默认参数：最近 30 分钟到 news 目录
    export_main()
    print("DONE")


if __name__ == "__main__":
    main()
