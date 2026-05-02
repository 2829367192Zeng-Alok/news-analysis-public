# -*- coding: utf-8 -*-
"""
豆包（火山引擎 Ark）Responses API 调用封装。

请求格式参考官方示例：
  POST https://ark.cn-beijing.volces.com/api/v3/responses
  Authorization: Bearer <api_key>
  Body: { "model": "<model_id>", "input": [ { "role": "user", "content": [ { "type": "input_text", "text": "..." } ] } ] }
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

import requests

from config import settings


def _build_input_text_message(text: str) -> list:
    """构建仅包含文本的 user 消息 content（Ark input 格式）。"""
    return [
        {
            "type": "input_text",
            "text": text,
        }
    ]


def chat(model: Optional[str] = None, user_text: str = "", timeout: int = 60) -> str:
    """
    调用豆包 Ark Responses API，发送一段用户文本，返回模型回复的纯文本。
    失败时自动重试最多 3 次。

    :param model: 模型 ID，默认使用 config 中的 DOUBAO_MODEL
    :param user_text: 用户输入内容（含系统提示词时可一并放入）
    :param timeout: 请求超时秒数
    :return: 模型输出的文本；若响应结构无法解析则抛出 ValueError
    """
    import time
    last_err = None
    for attempt in range(3):
        try:
            text, usage = _chat_once(model, user_text, timeout)
            return text
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    raise last_err  # type: ignore


def chat_with_usage(
    model: Optional[str] = None,
    user_text: str = "",
    timeout: int = 60,
    max_retries: int = 3,
) -> Tuple[str, Dict[str, int]]:
    """
    同 chat()，但返回 (回复文本, token 用量)。
    用量为 {"input_tokens": int, "output_tokens": int, "total_tokens": int}，缺失则为 0。
    :param max_retries: 失败后重试次数，0 表示不重试（只请求 1 次）。
    """
    import time
    last_err = None
    attempts = max(1, max_retries + 1)  # max_retries=0 -> 1 次，max_retries=2 -> 3 次
    for attempt in range(attempts):
        try:
            return _chat_once(model, user_text, timeout)
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                time.sleep(1.0 * (attempt + 1))
    raise last_err  # type: ignore


def _extract_usage(data: Dict[str, Any]) -> Dict[str, int]:
    """从 API 响应中解析 token 用量，返回 input_tokens, output_tokens, total_tokens（缺失则为 0）。"""
    out = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if not isinstance(data, dict):
        return out
    # 常见位置：data.usage, data.output.usage, data.data.usage（output/data 可能为 list，避免对 list 调用 .get）
    def _usage_node(obj: Any) -> Optional[Dict]:
        if not isinstance(obj, dict):
            return None
        u = obj.get("usage")
        return u if isinstance(u, dict) else None
    output = data.get("output")
    output = output if isinstance(output, dict) else None
    data_node = data.get("data")
    data_node = data_node if isinstance(data_node, dict) else None
    for node in (_usage_node(data), _usage_node(output) if output else None, _usage_node(data_node) if data_node else None):
        if not isinstance(node, dict):
            continue
        out["input_tokens"] = int(node.get("input_tokens") or node.get("prompt_tokens") or 0)
        out["output_tokens"] = int(node.get("output_tokens") or node.get("completion_tokens") or 0)
        out["total_tokens"] = int(node.get("total_tokens") or 0)
        if out["total_tokens"] == 0 and (out["input_tokens"] or out["output_tokens"]):
            out["total_tokens"] = out["input_tokens"] + out["output_tokens"]
        break
    return out


def _chat_once(model: Optional[str], user_text: str, timeout: int) -> Tuple[str, Dict[str, int]]:
    base_url = (settings.doubao.api_base_url or "").rstrip("/")
    if not base_url:
        base_url = "https://ark.cn-beijing.volces.com"
    url = f"{base_url}/api/v3/responses"
    api_key = settings.doubao.api_key
    if not api_key:
        raise RuntimeError("未配置 DOUBAO_API_KEY，请在 config 或环境变量中设置")

    model_id = model or settings.doubao.model_id or "doubao-seed-2-0-lite-260215"
    payload = {
        "model": model_id,
        "input": [
            {
                "role": "user",
                "content": _build_input_text_message(user_text),
            }
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    # 兼容多种常见响应结构（含火山引擎 Ark Responses API 新版）
    text = None
    if isinstance(data, dict):
        # 1. output.text 或 data.output.text（部分 Ark 文档）
        output = data.get("output")
        if output is None and "data" in data:
            output = (data.get("data") or {}).get("output")
        if isinstance(output, dict) and "text" in output:
            text = output.get("text")
        # 2. output.choices[0].message.content
        if text is None and isinstance(output, dict) and "choices" in output:
            choices = output.get("choices") or []
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message")
                if isinstance(msg, dict):
                    text = msg.get("content")
        # 3. 顶层 choices[0].message.content（OpenAI 兼容）
        if text is None and "choices" in data:
            choices = data.get("choices") or []
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message")
                if isinstance(msg, dict):
                    text = msg.get("content")
        # 4. output 直接为字符串
        if text is None and isinstance(data.get("output"), str):
            text = data.get("output")
        # 5. Ark Responses API：output 为 list，项为 {"type":"message","content":[{"type":"output_text","text":"..."}]}
        if text is None and isinstance(output, list):
            parts = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("text"):
                    parts.append(str(item.get("text")))
                elif item.get("content") is not None:
                    c = item.get("content")
                    if isinstance(c, str):
                        parts.append(c)
                    elif isinstance(c, list):
                        for block in c:
                            if isinstance(block, dict) and "text" in block:
                                # output_text / input_text 等均带 text 字段
                                parts.append(block.get("text") or "")
            if parts:
                text = "\n".join(parts)
        # 6. output.results 数组，项含 text
        if text is None and isinstance(output, dict) and "results" in output:
            results = output.get("results") or []
            parts = []
            for r in results:
                if isinstance(r, dict) and r.get("text"):
                    parts.append(r.get("text"))
            if parts:
                text = "\n".join(parts)
        # 7. output.message.content（单条 message）
        if text is None and isinstance(output, dict):
            msg = output.get("message")
            if isinstance(msg, dict) and msg.get("content"):
                text = msg.get("content")

    if text is None:
        raise ValueError(
            f"无法从豆包 API 响应中解析文本，响应键: {list(data.keys()) if isinstance(data, dict) else type(data)}"
        )
    return text.strip(), _extract_usage(data)


def parse_json_from_text(raw: str) -> Dict[str, Any]:
    """
    从模型返回的文本中解析 JSON。支持整段为 JSON，或 ```json ... ``` 代码块。
    """
    raw = raw.strip()
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 或 ``` ... ```
    for pattern in (r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"):
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
    raise ValueError("模型返回文本中未找到有效 JSON")
