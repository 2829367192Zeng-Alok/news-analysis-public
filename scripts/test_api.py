#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""临时脚本：测试 Tushare 与豆包接口是否跑通。运行后可在 ECS 上执行并删除。"""
import sys
sys.path.insert(0, ".")

def test_tushare():
    from config import settings
    if not settings.tushare.token:
        return False, "未配置 TUSHARE_TOKEN"
    try:
        import tushare as ts
        pro = ts.pro_api(settings.tushare.token)
        # 尝试新闻相关接口：major_news 或 news，按 Tushare 文档
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y-%m-%d %H:00:00")
        start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:00:00")
        try:
            df = pro.major_news(src="新浪财经", start_date=start_date, end_date=end_date)
        except Exception:
            # 部分账号可能是 news 接口
            start_d = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d%H%M%S")
            end_d = datetime.now().strftime("%Y%m%d%H%M%S")
            df = pro.news(src="sina", start_date=start_d, end_date=end_d)
        if df is None:
            return True, "接口调用成功，当前时间段无数据"
        return True, f"接口调用成功，返回 {len(df)} 条记录"
    except Exception as e:
        return False, str(e)[:200]

def test_doubao():
    from config import settings
    if not settings.doubao.api_key:
        return False, "未配置 DOUBAO_API_KEY"
    try:
        from doubao_client import chat
        reply = chat(user_text="请只回复一个字：好", timeout=15)
        reply = (reply or "").strip()[:50]
        return True, f"接口调用成功，回复: {reply}"
    except Exception as e:
        return False, str(e)[:200]

if __name__ == "__main__":
    print("=== Tushare 测试 ===")
    ok, msg = test_tushare()
    print("Tushare:", "通过" if ok else "失败", "-", msg)

    print("\n=== 豆包 AI 测试 ===")
    ok2, msg2 = test_doubao()
    print("豆包:", "通过" if ok2 else "失败", "-", msg2)

    sys.exit(0 if (ok and ok2) else 1)
