# -*- coding: utf-8 -*-
"""调用 go-cqhttp / OneBot11 HTTP 发送群消息。"""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


def send_group_msg(
    *,
    api_root: str,
    group_id: int,
    message: str,
    access_token: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    POST {api_root}/send_group_msg
    go-cqhttp 若配置了 access-token，需 Header: Authorization: Bearer <token>
    """
    base = api_root.rstrip("/")
    url = f"{base}/send_group_msg"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = (access_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"group_id": group_id, "message": message}
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"OneBot 返回非 JSON 对象: {data!r}")
    status = data.get("status")
    retcode = data.get("retcode")
    if status != "ok" or retcode not in (0, None):
        raise RuntimeError(f"send_group_msg 失败: status={status!r} retcode={retcode!r} data={data!r}")
    return data
