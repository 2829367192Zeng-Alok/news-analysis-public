#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""初始化或更新数据库表结构（兼容 MySQL / PostgreSQL）。"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from sqlalchemy import inspect, text

from models import Base, engine


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    cols = inspector.get_columns(table_name)
    return any(c.get("name") == column_name for c in cols)


def _add_column_if_missing(
    conn,
    inspector,
    table_name: str,
    check_column_name: str,
    ddl_column_name: str,
    col_spec: str,
) -> None:
    if _column_exists(inspector, table_name, check_column_name):
        return
    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl_column_name} {col_spec}"))
    conn.commit()
    print(f"已为 {table_name} 添加 {check_column_name}")


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    indexes = inspector.get_indexes(table_name)
    return any(i.get("name") == index_name for i in indexes)


def _create_index_if_missing(conn, inspector, table_name: str, index_name: str, column_name: str) -> None:
    if _index_exists(inspector, table_name, index_name):
        return
    conn.execute(text(f"CREATE INDEX {index_name} ON {table_name} ({column_name})"))
    conn.commit()
    print(f"已为 {table_name} 创建索引 {index_name}")


def _drop_legacy_column_indexes(conn, inspector, table_name: str, column_name: str = "content_hash") -> None:
    """
    清理历史遗留的冗余索引（列级 index=True 与显式 Index 同时声明导致每个
    content_hash 上存在 ix_* 与 idx_* 两份索引）。幂等：不存在则跳过。
    """
    legacy = [
        i["name"]
        for i in inspector.get_indexes(table_name)
        if i.get("name", "").startswith("ix_") and column_name in (i.get("column_names") or [])
    ]
    for name in legacy:
        try:
            if engine.dialect.name == "mysql":
                conn.execute(text(f"DROP INDEX {name} ON {table_name}"))
            else:
                conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
            conn.commit()
            print(f"已删除 {table_name} 的冗余索引 {name}")
        except Exception as e:
            print(f"删除 {table_name}.{name} 时: {e}")


def main():
    dialect = engine.dialect.name
    print(f"当前数据库方言: {dialect}")

    # 1) 创建所有表（若不存在）
    Base.metadata.create_all(engine)
    print("表结构已同步（缺失表已创建）")

    with engine.connect() as conn:
        inspector = inspect(conn)
        # 2) 确保核心去重字段及索引存在
        for tbl, idx_name in (
            ("raw_news", "idx_raw_content_hash"),
            ("selected_news", "idx_selected_content_hash"),
            ("news_analysis_detail", "idx_detail_content_hash"),
        ):
            try:
                _add_column_if_missing(
                    conn, inspector, tbl, "content_hash", "content_hash", "VARCHAR(64) NOT NULL DEFAULT ''"
                )
                inspector = inspect(conn)
                _create_index_if_missing(conn, inspector, tbl, idx_name, "content_hash")
                inspector = inspect(conn)
                _drop_legacy_column_indexes(conn, inspector, tbl)
                inspector = inspect(conn)
            except Exception as e:
                print(f"检查/更新 {tbl}.content_hash 时: {e}")

        # 3) raw_news.relevance（1=相关，0=不相关，NULL=未筛选）
        try:
            _add_column_if_missing(conn, inspector, "raw_news", "relevance", "relevance", "BOOLEAN NULL")
            inspector = inspect(conn)
        except Exception as e:
            print(f"检查/更新 raw_news.relevance 时: {e}")

        # 3.5) raw_news.content_hash 唯一约束（L4 硬兜底）
        # - news_fetcher 的幂等写入兜底以该约束为前提；
        # - 库内尚有重复 hash 时创建会失败：非致命，按提示先执行
        #   python scripts/normalize_content_hash.py --dedupe 后重跑本脚本即可。
        try:
            if not _index_exists(inspector, "raw_news", "uq_raw_content_hash"):
                conn.execute(text(
                    "CREATE UNIQUE INDEX uq_raw_content_hash ON raw_news (content_hash)"
                ))
                conn.commit()
                print("已创建唯一索引 uq_raw_content_hash（raw_news.content_hash）")
            inspector = inspect(conn)
        except Exception as e:
            conn.rollback()
            print(
                "创建 uq_raw_content_hash 失败（通常因库内存在重复 content_hash，非致命）：\n"
                f"  {e}\n"
                "  请先执行: python scripts/normalize_content_hash.py --dry-run 然后 --update --dedupe，"
                "再重跑本脚本。"
            )

        # 4) news_analysis_detail 旧表补列
        detail_columns = [
            ("interest_direction", "interest_direction", "INTEGER NULL"),
            ("interest_impact", "interest_impact", "INTEGER NULL"),
            ("dollar_direction", "dollar_direction", "INTEGER NULL"),
            ("dollar_impact", "dollar_impact", "INTEGER NULL"),
            ("warrisk_direction", "warrisk_direction", "INTEGER NULL"),
            ("warrisk_impact", "warrisk_impact", "INTEGER NULL"),
            ("liquidity_direction", "liquidity_direction", "INTEGER NULL"),
            ("liquidity_impact", "liquidity_impact", "INTEGER NULL"),
            ("emotion_direction", "emotion_direction", "INTEGER NULL"),
            ("emotion_impact", "emotion_impact", "INTEGER NULL"),
            ("keyword", "keyword", "JSON NULL"),
            ("Reference", '"Reference"', "JSON NULL"),
            ("interest", "interest", "TEXT NULL"),
            ("dollar", "dollar", "TEXT NULL"),
            ("warrisk", "warrisk", "TEXT NULL"),
            ("liquidity", "liquidity", "TEXT NULL"),
            ("emotion", "emotion", "TEXT NULL"),
            ("shorttime", "shorttime", "TEXT NULL"),
            ("midtime", "midtime", "TEXT NULL"),
            ("longtime", "longtime", "TEXT NULL"),
            ("insight", "insight", "TEXT NULL"),
            ("conclusion", "conclusion", "TEXT NULL"),
            # v2 提示词字段（USE_PROMPTS_V2=1 时使用，必须先补列再开 v2）
            ("confidence", "confidence", "INTEGER NULL"),
            ("uncertain", "uncertain", "BOOLEAN NULL"),
        ]
        for check_name, ddl_name, col_spec in detail_columns:
            try:
                _add_column_if_missing(
                    conn, inspector, "news_analysis_detail", check_name, ddl_name, col_spec
                )
                inspector = inspect(conn)
            except Exception as e:
                print(f"检查/更新 news_analysis_detail.{check_name} 时: {e}")

        # 5) 内容字段类型修正：MySQL 扩到 MEDIUMTEXT，PostgreSQL 保持 TEXT
        for tbl in ("raw_news", "selected_news", "news_analysis_detail"):
            try:
                if dialect == "mysql":
                    conn.execute(text(f"ALTER TABLE {tbl} MODIFY COLUMN content MEDIUMTEXT NOT NULL"))
                    conn.commit()
                    print(f"已把 {tbl}.content 改为 MEDIUMTEXT")
                elif dialect == "postgresql":
                    conn.execute(text(f"ALTER TABLE {tbl} ALTER COLUMN content TYPE TEXT"))
                    conn.execute(text(f"ALTER TABLE {tbl} ALTER COLUMN content SET NOT NULL"))
                    conn.commit()
                    print(f"已确认 {tbl}.content 为 TEXT NOT NULL")
            except Exception as e:
                print(f"修改 {tbl}.content 时: {e}")
    print("完成")


if __name__ == "__main__":
    main()
