#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单独测试 Tushare pro.news 接口：检查时间窗与是否有数据传输。
测试 3 分钟窗（与流水线一致）和 60 分钟窗（便于确认接口是否正常）。
"""
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")
from config import settings

TZ_BJ = timezone(timedelta(hours=8))
FMT = "%Y-%m-%d %H:%M:%S"


def test_window(pro, src_name: str, src: str, minutes: int) -> None:
    now_bj = datetime.now(TZ_BJ)
    start_bj = now_bj - timedelta(minutes=minutes)
    start_date = start_bj.strftime(FMT)
    end_date = now_bj.strftime(FMT)
    print(f"  时间窗（北京时间）: {start_date} ~ {end_date} ({minutes} 分钟)")
    try:
        df = pro.news(src=src, start_date=start_date, end_date=end_date)
        if df is None:
            print(f"  返回: None")
        elif df.empty:
            print(f"  返回: 0 行（空表）")
        else:
            print(f"  返回: {len(df)} 行")
            print(f"  列名: {list(df.columns)}")
            row = df.iloc[0].to_dict()
            title = str(row.get("title") or row.get("Title") or "")[:80]
            print(f"  首条 title: {title}")
    except Exception as e:
        print(f"  异常: {e}")
    print()


def main():
    print("=== Tushare pro.news 接口测试 ===\n")
    print("当前北京时间:", datetime.now(TZ_BJ).strftime(FMT))
    print()

    if not settings.tushare.token:
        print("未配置 TUSHARE_TOKEN，请设置环境变量或 .env")
        sys.exit(1)

    import tushare as ts
    pro = ts.pro_api(settings.tushare.token)

    for src_name, src in [("华尔街见闻", "wallstreetcn"), ("新浪财经", "sina")]:
        print(f"[{src_name}] src={src}")
        test_window(pro, src_name, src, 3)
        test_window(pro, src_name, src, 60)
    print("测试结束")


if __name__ == "__main__":
    main()
