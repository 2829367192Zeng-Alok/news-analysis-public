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

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import SessionLocal, engine


def _parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_bool(v: Any) -> bool | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("", "none", "null"):
        return None
    if s in ("1", "true", "t", "yes", "y"):
        return True
    if s in ("0", "false", "f", "no", "n"):
        return False
    return None


def _parse_int(v: Any) -> int | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _parse_json_array(v: Any) -> list[str] | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        j = json.loads(s)
        if isinstance(j, list):
            return [str(x) for x in j]
    except Exception:
        pass
    return [x.strip() for x in s.replace("，", ",").split(",") if x.strip()]


def _clean(s: Any) -> str | None:
    if s is None:
        return None
    v = str(s)
    return v if v != "" else None


def _json_param(v: list[str] | None) -> str | None:
    if v is None:
        return None
    return json.dumps(v, ensure_ascii=False)


def _truncate_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE news_analysis_detail RESTART IDENTITY"))
        conn.execute(text("TRUNCATE TABLE selected_news RESTART IDENTITY"))
        conn.execute(text("TRUNCATE TABLE raw_news RESTART IDENTITY"))


def _import_raw(path: Path, batch_size: int) -> int:
    total = 0
    session = SessionLocal()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            batch: list[dict] = []
            for row in reader:
                batch.append(
                    {
                        "id": _parse_int(row.get("id")),
                        "title": _clean(row.get("title")) or "",
                        "content": _clean(row.get("content")) or "",
                        "news_datetime": _parse_dt(row.get("news_datetime")),
                        "source": _clean(row.get("source")) or "",
                        "create_time": _parse_dt(row.get("create_time")),
                        "content_hash": _clean(row.get("content_hash")) or "",
                        "relevance": _parse_bool(row.get("relevance")),
                    }
                )
                if len(batch) >= batch_size:
                    session.execute(
                        text(
                            """
                            INSERT INTO raw_news
                            (id,title,content,news_datetime,source,create_time,content_hash,relevance)
                            VALUES
                            (:id,:title,:content,:news_datetime,:source,:create_time,:content_hash,:relevance)
                            """
                        ),
                        batch,
                    )
                    session.commit()
                    total += len(batch)
                    batch = []
            if batch:
                session.execute(
                    text(
                        """
                        INSERT INTO raw_news
                        (id,title,content,news_datetime,source,create_time,content_hash,relevance)
                        VALUES
                        (:id,:title,:content,:news_datetime,:source,:create_time,:content_hash,:relevance)
                        """
                    ),
                    batch,
                )
                session.commit()
                total += len(batch)
    finally:
        session.close()
    return total


def _import_selected(path: Path, batch_size: int) -> int:
    total = 0
    session = SessionLocal()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            batch: list[dict] = []
            for row in reader:
                batch.append(
                    {
                        "id": _parse_int(row.get("id")),
                        "title": _clean(row.get("title")) or "",
                        "content": _clean(row.get("content")) or "",
                        "news_datetime": _parse_dt(row.get("news_datetime")),
                        "source": _clean(row.get("source")) or "",
                        "create_time": _parse_dt(row.get("create_time")),
                        "relevance": _parse_bool(row.get("relevance")) or False,
                        "direction": _parse_int(row.get("direction")),
                        "impact": _parse_int(row.get("impact")),
                        "content_hash": _clean(row.get("content_hash")) or "",
                    }
                )
                if len(batch) >= batch_size:
                    session.execute(
                        text(
                            """
                            INSERT INTO selected_news
                            (id,title,content,news_datetime,source,create_time,relevance,direction,impact,content_hash)
                            VALUES
                            (:id,:title,:content,:news_datetime,:source,:create_time,:relevance,:direction,:impact,:content_hash)
                            """
                        ),
                        batch,
                    )
                    session.commit()
                    total += len(batch)
                    batch = []
            if batch:
                session.execute(
                    text(
                        """
                        INSERT INTO selected_news
                        (id,title,content,news_datetime,source,create_time,relevance,direction,impact,content_hash)
                        VALUES
                        (:id,:title,:content,:news_datetime,:source,:create_time,:relevance,:direction,:impact,:content_hash)
                        """
                    ),
                    batch,
                )
                session.commit()
                total += len(batch)
    finally:
        session.close()
    return total


def _import_detail(path: Path, batch_size: int) -> int:
    total = 0
    session = SessionLocal()
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            batch: list[dict] = []
            for row in reader:
                batch.append(
                    {
                        "id": _parse_int(row.get("id")),
                        "title": _clean(row.get("title")) or "",
                        "content": _clean(row.get("content")) or "",
                        "news_datetime": _parse_dt(row.get("news_datetime")),
                        "source": _clean(row.get("source")) or "",
                        "create_time": _parse_dt(row.get("create_time")),
                        "relevance": _parse_bool(row.get("relevance")) or False,
                        "direction": _parse_int(row.get("direction")),
                        "impact": _parse_int(row.get("impact")),
                        "interest_direction": _parse_int(row.get("interest_direction")),
                        "interest_impact": _parse_int(row.get("interest_impact")),
                        "dollar_direction": _parse_int(row.get("dollar_direction")),
                        "dollar_impact": _parse_int(row.get("dollar_impact")),
                        "warrisk_direction": _parse_int(row.get("warrisk_direction")),
                        "warrisk_impact": _parse_int(row.get("warrisk_impact")),
                        "liquidity_direction": _parse_int(row.get("liquidity_direction")),
                        "liquidity_impact": _parse_int(row.get("liquidity_impact")),
                        "emotion_direction": _parse_int(row.get("emotion_direction")),
                        "emotion_impact": _parse_int(row.get("emotion_impact")),
                        "keyword": _json_param(_parse_json_array(row.get("keyword"))),
                        "Reference": _json_param(
                            _parse_json_array(row.get("Reference") or row.get("reference_content"))
                        ),
                        "interest": _clean(row.get("interest")),
                        "dollar": _clean(row.get("dollar")),
                        "warrisk": _clean(row.get("warrisk")),
                        "liquidity": _clean(row.get("liquidity")),
                        "emotion": _clean(row.get("emotion")),
                        "shorttime": _clean(row.get("shorttime") or row.get("conclusion_short")),
                        "midtime": _clean(row.get("midtime") or row.get("conclusion_mid")),
                        "longtime": _clean(row.get("longtime") or row.get("conclusion_long")),
                        "insight": _clean(row.get("insight")),
                        "conclusion": _clean(row.get("conclusion")),
                        "content_hash": _clean(row.get("content_hash")) or "",
                    }
                )
                if len(batch) >= batch_size:
                    session.execute(
                        text(
                            """
                            INSERT INTO news_analysis_detail
                            (id,title,content,news_datetime,source,create_time,relevance,direction,impact,
                             interest_direction,interest_impact,dollar_direction,dollar_impact,warrisk_direction,warrisk_impact,
                             liquidity_direction,liquidity_impact,emotion_direction,emotion_impact,keyword,"Reference",
                             interest,dollar,warrisk,liquidity,emotion,shorttime,midtime,longtime,insight,conclusion,content_hash)
                            VALUES
                            (:id,:title,:content,:news_datetime,:source,:create_time,:relevance,:direction,:impact,
                             :interest_direction,:interest_impact,:dollar_direction,:dollar_impact,:warrisk_direction,:warrisk_impact,
                             :liquidity_direction,:liquidity_impact,:emotion_direction,:emotion_impact,:keyword,:Reference,
                             :interest,:dollar,:warrisk,:liquidity,:emotion,:shorttime,:midtime,:longtime,:insight,:conclusion,:content_hash)
                            """
                        ),
                        batch,
                    )
                    session.commit()
                    total += len(batch)
                    batch = []
            if batch:
                session.execute(
                    text(
                        """
                        INSERT INTO news_analysis_detail
                        (id,title,content,news_datetime,source,create_time,relevance,direction,impact,
                         interest_direction,interest_impact,dollar_direction,dollar_impact,warrisk_direction,warrisk_impact,
                         liquidity_direction,liquidity_impact,emotion_direction,emotion_impact,keyword,"Reference",
                         interest,dollar,warrisk,liquidity,emotion,shorttime,midtime,longtime,insight,conclusion,content_hash)
                        VALUES
                        (:id,:title,:content,:news_datetime,:source,:create_time,:relevance,:direction,:impact,
                         :interest_direction,:interest_impact,:dollar_direction,:dollar_impact,:warrisk_direction,:warrisk_impact,
                         :liquidity_direction,:liquidity_impact,:emotion_direction,:emotion_impact,:keyword,:Reference,
                         :interest,:dollar,:warrisk,:liquidity,:emotion,:shorttime,:midtime,:longtime,:insight,:conclusion,:content_hash)
                        """
                    ),
                    batch,
                )
                session.commit()
                total += len(batch)
    finally:
        session.close()
    return total


def _fix_sequences() -> None:
    with engine.begin() as conn:
        for table in ("raw_news", "selected_news", "news_analysis_detail"):
            conn.execute(
                text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE((SELECT MAX(id) FROM {table}), 1),
                        COALESCE((SELECT MAX(id) FROM {table}) IS NOT NULL, false)
                    )
                    """
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="CSV -> PostgreSQL 全量导入")
    parser.add_argument("--csv-dir", type=str, default="migration_csv")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--no-truncate", action="store_true")
    args = parser.parse_args()

    csv_dir = Path(args.csv_dir)
    raw_csv = csv_dir / "raw_news.csv"
    selected_csv = csv_dir / "selected_news.csv"
    detail_csv = csv_dir / "news_analysis_detail.csv"
    for p in (raw_csv, selected_csv, detail_csv):
        if not p.exists():
            raise FileNotFoundError(f"缺少文件: {p}")

    if not args.no_truncate:
        _truncate_tables()
        print("已清空目标表")

    c1 = _import_raw(raw_csv, args.batch_size)
    print(f"raw_news 导入: {c1}")
    c2 = _import_selected(selected_csv, args.batch_size)
    print(f"selected_news 导入: {c2}")
    c3 = _import_detail(detail_csv, args.batch_size)
    print(f"news_analysis_detail 导入: {c3}")

    _fix_sequences()
    print("序列已重置，导入完成")


if __name__ == "__main__":
    main()
