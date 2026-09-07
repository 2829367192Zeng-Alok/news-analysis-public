#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 MySQL 的核心业务表全量迁移到 PostgreSQL。"""
from __future__ import annotations

import argparse
from typing import Iterable

from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import make_url

from config import settings

TABLES = ["raw_news", "selected_news", "news_analysis_detail"]


def _masked_url(url: str) -> str:
    """打印用：隐藏连接串中的密码，避免凭据落日志。"""
    try:
        return make_url(url).set(password="***").render_as_string(hide_password=True)
    except Exception:
        return "<unparseable-url>"


def _build_source_url() -> str:
    return settings.db.mysql_sqlalchemy_url


def _build_target_url() -> str:
    return settings.db.postgres_sqlalchemy_url


def _reset_pg_sequence(conn, table_name: str, id_column: str = "id") -> None:
    conn.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence(:table_name, :id_column),
                COALESCE((SELECT MAX(id) FROM {}), 1),
                COALESCE((SELECT MAX(id) FROM {}) IS NOT NULL, false)
            )
            """.format(table_name, table_name)
        ),
        {"table_name": table_name, "id_column": id_column},
    )


def _chunked_rows(result, size: int) -> Iterable[list[dict]]:
    while True:
        rows = result.mappings().fetchmany(size)
        if not rows:
            break
        yield [dict(r) for r in rows]


def migrate(chunk_size: int = 1000, truncate_target: bool = True) -> None:
    source_url = _build_source_url()
    target_url = _build_target_url()
    print(f"源库: {_masked_url(source_url)}")
    print(f"目标库: {_masked_url(target_url)}")

    source_engine = create_engine(source_url, pool_pre_ping=True)
    target_engine = create_engine(target_url, pool_pre_ping=True)

    with source_engine.connect() as src_conn, target_engine.connect() as tgt_conn:
        src_insp = inspect(src_conn)
        tgt_insp = inspect(tgt_conn)

        # 连接与权限基础检查
        src_conn.execute(text("SELECT 1"))
        tgt_conn.execute(text("SELECT 1"))
        print("数据库连通性检查通过")

        source_tables = set(src_insp.get_table_names())
        target_tables = set(tgt_insp.get_table_names())
        for t in TABLES:
            if t not in source_tables:
                raise RuntimeError(f"源库缺少表: {t}")
            if t not in target_tables:
                raise RuntimeError(
                    f"目标库缺少表: {t}。请先切到 PostgreSQL 后执行: python init_db.py"
                )

        src_meta = MetaData()
        tgt_meta = MetaData()
        src_objs: dict[str, Table] = {}
        tgt_objs: dict[str, Table] = {}
        for t in TABLES:
            src_objs[t] = Table(t, src_meta, autoload_with=src_conn)
            tgt_objs[t] = Table(t, tgt_meta, autoload_with=tgt_conn)

        if truncate_target:
            with tgt_conn.begin():
                # 有外键时先删子表，这里按明细 -> 选中 -> 原始 顺序清空
                for t in reversed(TABLES):
                    tgt_conn.execute(text(f"TRUNCATE TABLE {t} RESTART IDENTITY"))
                    print(f"已清空目标表: {t}")

        for t in TABLES:
            print(f"开始迁移表: {t}")
            total = 0
            with src_conn.execution_options(stream_results=True).execute(
                select(src_objs[t]).order_by(src_objs[t].c.id.asc())
            ) as rs:
                for batch in _chunked_rows(rs, chunk_size):
                    with tgt_conn.begin():
                        tgt_conn.execute(tgt_objs[t].insert(), batch)
                    total += len(batch)
                    print(f"  已迁移 {total} 行 -> {t}")
            # 保险起见重置一次序列（即使已 TRUNCATE）
            with tgt_conn.begin():
                _reset_pg_sequence(tgt_conn, t, "id")
            print(f"完成迁移表: {t}, 总计 {total} 行")

    print("全部表迁移完成")


def main() -> None:
    parser = argparse.ArgumentParser(description="MySQL -> PostgreSQL 全量迁移")
    parser.add_argument("--chunk-size", type=int, default=1000, help="每批迁移行数（默认 1000）")
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="不清空目标表，直接追加（默认会先清空目标表）",
    )
    args = parser.parse_args()

    migrate(chunk_size=args.chunk_size, truncate_target=(not args.no_truncate))


if __name__ == "__main__":
    main()
