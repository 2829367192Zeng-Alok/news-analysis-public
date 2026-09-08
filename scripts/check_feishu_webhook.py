#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
飞书 Webhook 连通性检查：逐个 URL 发送测试消息，打印精确的成功/失败详情。

用途：定位推送 403/失败的具体原因（机器人被移除、签名校验、IP 限制、
Flow 触发器停用等）——响应体会包含飞书返回的错误码与说明。

用法（在项目根目录）：
  python scripts/check_feishu_webhook.py            # 测试 .env 中配置的全部 Webhook
  python scripts/check_feishu_webhook.py --url ...  # 测试单个 URL
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402


def _mask(url: str) -> str:
    """日志展示用：隐藏 Webhook 地址中的 token 主体。"""
    if "/" not in url:
        return "<invalid-url>"
    head, _, tail = url.rpartition("/")
    shown = tail[:6] + "..." if len(tail) > 6 else tail
    return f"{head}/{shown}"


def check_one(url: str) -> bool:
    from feishu_webhook.webhook_client import send_text_message

    label = f"[{'Flow' if 'flow/api/trigger-webhook' in url else '机器人'}] {_mask(url)}"
    try:
        send_text_message(webhook_url=url, text="【连通性检查】financial-news 推送通道测试")
        print(f"OK   {label}")
        return True
    except Exception as e:
        print(f"FAIL {label}\n     {type(e).__name__}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="飞书 Webhook 连通性检查")
    parser.add_argument("--url", action="append", default=[], help="额外测试的 URL（可多次）")
    args = parser.parse_args()

    urls = list(settings.feishu_webhook.webhook_urls) + list(args.url)
    if not urls:
        print("未配置任何 Webhook（FEISHU_WEBHOOK_URL），请检查 .env")
        sys.exit(1)
    if not settings.feishu_webhook.enabled:
        print("注意：FEISHU_WEBHOOK_ENABLED 未开启（本次仍逐 URL 强制测试）")

    print(f"共 {len(urls)} 个 Webhook：\n")
    results = [check_one(u) for u in urls]
    ok = sum(results)
    print(f"\n结果: {ok}/{len(urls)} 成功")
    sys.exit(0 if ok == len(urls) else 1)


if __name__ == "__main__":
    main()
