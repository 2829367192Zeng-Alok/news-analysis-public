#!/usr/bin/env python3
"""数据库连通性检查（方言无关，MySQL / PostgreSQL 通用）。部署验收时执行，期望输出 DB_OK。"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from sqlalchemy import create_engine, text

from config import settings


def main() -> None:
    try:
        engine = create_engine(settings.db.sqlalchemy_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("DB_OK")
    except Exception as e:
        print("DB_FAIL:", type(e).__name__, str(e)[:200])
        sys.exit(1)


if __name__ == "__main__":
    main()
