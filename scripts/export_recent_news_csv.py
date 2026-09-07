#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import select

from models import RawNews, SelectedNews, get_db_session
from utils import now_beijing_naive


def _write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="导出最近 N 分钟 raw_news 与 selected_news 为 CSV")
    parser.add_argument("--minutes", type=int, default=30, help="导出最近 N 分钟（默认 30）")
    parser.add_argument("--out-dir", type=str, default="news", help="输出目录（默认 news）")
    args = parser.parse_args()

    since_dt = now_beijing_naive() - timedelta(minutes=args.minutes)
    out_dir = Path(args.out_dir)

    session = get_db_session()
    try:
        raw_items = session.execute(
            select(RawNews)
            .where(RawNews.news_datetime >= since_dt)
            .order_by(RawNews.news_datetime.desc())
        ).scalars().all()

        selected_items = session.execute(
            select(SelectedNews)
            .where(SelectedNews.news_datetime >= since_dt)
            .order_by(SelectedNews.news_datetime.desc())
        ).scalars().all()

        raw_rows = [
            [
                i.id, i.title, i.content, i.news_datetime, i.source, i.create_time, i.content_hash, i.relevance
            ]
            for i in raw_items
        ]
        selected_rows = [
            [
                i.id, i.title, i.content, i.news_datetime, i.source, i.create_time,
                i.relevance, i.direction, i.impact, i.content_hash
            ]
            for i in selected_items
        ]

        _write_csv(
            out_dir / f"raw_news_recent_{args.minutes}m.csv",
            ["id", "title", "content", "news_datetime", "source", "create_time", "content_hash", "relevance"],
            raw_rows,
        )
        _write_csv(
            out_dir / f"selected_news_recent_{args.minutes}m.csv",
            ["id", "title", "content", "news_datetime", "source", "create_time", "relevance", "direction", "impact", "content_hash"],
            selected_rows,
        )

        print(f"raw_news rows: {len(raw_rows)}")
        print(f"selected_news rows: {len(selected_rows)}")
        print(f"output dir: {os.path.abspath(str(out_dir))}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
