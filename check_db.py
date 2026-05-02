#!/usr/bin/env python3
"""临时脚本：测试数据库连接（运行后可在 ECS 上执行并删除）。"""
import sys
sys.path.insert(0, ".")
try:
    from config import settings
    import pymysql
    c = settings.db
    conn = pymysql.connect(
        host=c.host, port=c.port, user=c.user, password=c.password,
        database=c.name, connect_timeout=10
    )
    conn.ping()
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.fetchone()
    cur.close()
    conn.close()
    print("DB_OK")
except Exception as e:
    print("DB_FAIL:", type(e).__name__, str(e)[:200])
    sys.exit(1)
