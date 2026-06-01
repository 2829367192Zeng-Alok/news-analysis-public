# -*- coding: utf-8 -*-
"""
飞书 Webhook 推送。

支持两种 Webhook 类型，根据 URL 自动识别：
  1. 自定义机器人（open.feishu.cn/open-apis/bot/v2/hook/）
     payload: {"msg_type": "text", "content": {"text": "..."}}
  2. 自动化 Flow 触发器（feishu.cn/flow/api/trigger-webhook/）
     payload: {"content": "..."}  平铺 JSON，对应触发器中配置的变量字段
"""
from __future__ import annotations

from typing import Any

import requests


def _is_flow_webhook(url: str) -> bool:
    """判断是否为飞书自动化 Flow Webhook 触发器地址。"""
    return "flow/api/trigger-webhook" in url


def send_text_message(
    *,
    webhook_url: str,
    text: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    POST 飞书 Webhook。自动根据 URL 选择正确的请求体格式。

    - 自定义机器人：{"msg_type": "text", "content": {"text": text}}
    - Flow 自动化触发器：{"content": text}
    """
    url = webhook_url.strip()

    if _is_flow_webhook(url):
        # 飞书自动化 Flow：平铺 JSON，content 字段对应触发器变量
        payload: dict[str, Any] = {"content": text}
    else:
        # 飞书自定义机器人：标准消息卡片格式
        payload = {"msg_type": "text", "content": {"text": text}}

    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, dict):
        raise RuntimeError(f"飞书 Webhook 返回非 JSON 对象: {data!r}")

    code = data.get("code")
    if code is not None and int(code) != 0:
        raise RuntimeError(
            f"飞书 Webhook 业务错误: code={code!r} msg={data.get('msg')!r} data={data!r}"
        )
    # 部分网关返回 StatusCode
    sc = data.get("StatusCode")
    if sc is not None and int(sc) != 0:
        raise RuntimeError(
            f"飞书 Webhook StatusCode: {sc!r} {data.get('StatusMessage')!r}"
        )
    return data
