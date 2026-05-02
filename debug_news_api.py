#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时调试：直接调用 Tushare pro.news，打印时间窗与返回条数、首行键名。"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from config import settings

# 北京时间
TZ_BJ = timezone(timedelta(hours=8))
fmt = "%Y-%m-%d %H:%M:%S"
now_bj = datetime.now(TZ_BJ)
start_bj = now_bj - timedelta(minutes=120)
start_date = start_bj.strftime(fmt)
end_date = now_bj.strftime(fmt)

print("当前北京时间:", now_bj.strftime(fmt))
print("请求时间窗:  ", start_date, "~", end_date)
print()

if not settings.tushare.token:
    print("未配置 TUSHARE_TOKEN")
    sys.exit(1)

import tushare as ts
pro = ts.pro_api(settings.tushare.token)

for src_name, src in [("华尔街见闻", "wallstreetcn"), ("新浪财经", "sina")]:
    try:
        df = pro.news(src=src, start_date=start_date, end_date=end_date)
        if df is None:
            print(f"{src_name} ({src}): 返回 None")
        elif df.empty:
            print(f"{src_name} ({src}): 返回 0 行")
        else:
            print(f"{src_name} ({src}): 返回 {len(df)} 行")
            print("  列名:", list(df.columns))
            row = df.iloc[0].to_dict()
            print("  首行键:", list(row.keys()))
            t = str(row.get("title") or row.get("Title") or "")[:60]
            c = str(row.get("content") or row.get("Content") or "")[:80]
            print("  title 示例:", t)
            print("  content 示例:", c)
    except Exception as e:
        print(f"{src_name} ({src}): 异常 {e}")
    print()
