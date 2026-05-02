#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from models import SelectedNews, get_db_session


def main() -> None:
    out_path = ROOT / "news" / "selected_news_latest_20.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    session = get_db_session()
    try:
        rows = session.execute(
            select(SelectedNews)
            .order_by(SelectedNews.news_datetime.desc())
            .limit(20)
        ).scalars().all()

        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "title",
                    "content",
                    "news_datetime",
                    "source",
                    "create_time",
                    "relevance",
                    "direction",
                    "impact",
                    "content_hash",
                ]
            )
            for i in rows:
                writer.writerow(
                    [
                        i.id,
                        i.title,
                        i.content,
                        i.news_datetime,
                        i.source,
                        i.create_time,
                        i.relevance,
                        i.direction,
                        i.impact,
                        i.content_hash,
                    ]
                )
        print(f"exported_rows={len(rows)}")
        print(f"out={out_path}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
