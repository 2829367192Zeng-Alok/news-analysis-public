#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 raw_news/raw__news 的 relevance 列状态。"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from sqlalchemy import inspect

from models import engine


def main() -> None:
    insp = inspect(engine)
    table_names = set(insp.get_table_names())

    if "raw_news" in table_names:
        cols = insp.get_columns("raw_news")
        relevance = [c for c in cols if c.get("name") == "relevance"]
        print("raw_news.relevance:", relevance)
    else:
        print("raw_news.relevance: table not found")

    print("raw__news exists:", "raw__news" in table_names)
    if "raw__news" in table_names:
        cols2 = insp.get_columns("raw__news")
        relevance2 = [c for c in cols2 if c.get("name") == "relevance"]
        print("raw__news.relevance:", relevance2)


if __name__ == "__main__":
    main()
