# -*- coding: utf-8 -*-
"""
豆包（火山引擎 Ark）Responses API 调用封装。

请求格式参考官方示例：
  POST https://ark.cn-beijing.volces.com/api/v3/responses
  Authorization: Bearer <api_key>
  Body: { "model": "<model_id>", "input": [ { "role": "user", "content": [ { "type": "input_text", "text": "..." } ] } ] }

v2 改动：
- 429 限流：指数退避重试（最长等待 64s），并记录限流状态供上层熔断判断。
- 404 接口不可用：立即抛出 DoubaoUnavailableError，不重试（重试无意义）。
- 5xx 服务错误：指数退避重试。
- 新增 DoubaoRateLimitError / DoubaoUnavailableError 异常类，方便上层区分错误类型。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests

from config import settings


# ---------- 自定义异常 ----------

class DoubaoError(RuntimeError):
    """豆包 API 调用基础异常。"""


class DoubaoRateLimitError(DoubaoError):
    """429 Too Many Requests：触发限流，调用方应回退等待。"""
    def __init__(self, msg: str = "", retry_after: float = 0.0):
        super().__init__(msg)
        self.retry_after = retry_after  # 建议等待秒数（来自响应头或默认值）


class DoubaoUnavailableError(DoubaoError):
    """404/503 接口/模型不可用：配置或服务端问题，重试无意义。"""


# ---------- 内部构建函数 ----------

def _build_input_text_message(text: str) -> list:
    """构建仅包含文本的 user 消息 content（Ark input 格式）。"""
    return [{"type": "input_text", "text": text}]


# ---------- 公开 API ----------

def chat(
    model: Optional[str] = None,
    user_text: str = "",
    timeout: int = 60,
    system_text: Optional[str] = None,
) -> str:
    """
    调用豆包 Ark Responses API，返回模型回复的纯文本。
    遇 429 做指数退避重试（最多 4 次），遇 404/503 立即抛 DoubaoUnavailableError。
    """
    text, _ = chat_with_usage(
        model=model,
        user_text=user_text,
        timeout=timeout,
        system_text=system_text,
        max_retries=4,
    )
    return text


def chat_with_usage(
    model: Optional[str] = None,
    user_text: str = "",
    timeout: int = 60,
    max_retries: int = 3,
    system_text: Optional[str] = None,
) -> Tuple[str, Dict[str, int]]:
    """
    同 chat()，但返回 (回复文本, token 用量)。
    - max_retries=0：仅请求 1 次，不重试。
    - 429 限流：指数退避（2^attempt 秒，最长 64s），最多重试 max_retries 次。
    - 404/503：立即抛 DoubaoUnavailableError，不消耗重试次数。
    """
    last_err: Optional[Exception] = None
    attempts = max(1, max_retries + 1)

    for attempt in range(attempts):
        try:
            return _chat_once(model, user_text, timeout, system_text=system_text)
        except DoubaoUnavailableError:
            # 404 / 503：配置或服务端问题，重试无意义，立即上抛
            raise
        except DoubaoRateLimitError as e:
            last_err = e
            if attempt >= attempts - 1:
                break
            # 指数退避：2^attempt 秒，最小 4s，最大 64s
            wait = min(64.0, max(4.0, 2 ** (attempt + 2)))
            if e.retry_after > 0:
                wait = min(64.0, e.retry_after)
            import logging
            logging.getLogger(__name__).warning(
                "豆包 429 限流，等待 %.1fs 后重试（attempt %s/%s）", wait, attempt + 1, attempts
            )
            time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                wait = min(16.0, 1.0 * (attempt + 1))
                time.sleep(wait)

    raise last_err  # type: ignore


# ---------- 内部实现 ----------

def _extract_usage(data: Dict[str, Any]) -> Dict[str, int]:
    """从 API 响应中解析 token 用量。"""
    out = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if not isinstance(data, dict):
        return out

    def _usage_node(obj: Any) -> Optional[Dict]:
        if not isinstance(obj, dict):
            return None
        u = obj.get("usage")
        return u if isinstance(u, dict) else None

    output = data.get("output")
    output = output if isinstance(output, dict) else None
    data_node = data.get("data")
    data_node = data_node if isinstance(data_node, dict) else None

    for node in (
        _usage_node(data),
        _usage_node(output) if output else None,
        _usage_node(data_node) if data_node else None,
    ):
        if not isinstance(node, dict):
            continue
        out["input_tokens"] = int(node.get("input_tokens") or node.get("prompt_tokens") or 0)
        out["output_tokens"] = int(node.get("output_tokens") or node.get("completion_tokens") or 0)
        out["total_tokens"] = int(node.get("total_tokens") or 0)
        if out["total_tokens"] == 0 and (out["input_tokens"] or out["output_tokens"]):
            out["total_tokens"] = out["input_tokens"] + out["output_tokens"]
        break
    return out


def _chat_once(
    model: Optional[str],
    user_text: str,
    timeout: int,
    system_text: Optional[str] = None,
) -> Tuple[str, Dict[str, int]]:
    base_url = (settings.doubao.api_base_url or "").rstrip("/") or "https://ark.cn-beijing.volces.com"
    url = f"{base_url}/api/v3/responses"
    api_key = settings.doubao.api_key
    if not api_key:
        raise DoubaoError("未配置 DOUBAO_API_KEY，请在 config 或环境变量中设置")

    model_id = model or settings.doubao.model_id or "doubao-seed-2-0-lite-260215"
    input_messages: list = []
    if system_text and str(system_text).strip():
        input_messages.append({
            "role": "system",
            "content": _build_input_text_message(str(system_text).strip()),
        })
    input_messages.append({
        "role": "user",
        "content": _build_input_text_message(user_text),
    })

    payload = {"model": model_id, "input": input_messages}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.Timeout:
        raise DoubaoError(f"豆包 API 请求超时（{timeout}s）")
    except requests.ConnectionError as e:
        raise DoubaoError(f"豆包 API 连接失败: {e}")

    # --- 根据 HTTP 状态码分类处理 ---
    if resp.status_code == 429:
        retry_after = 0.0
        ra = resp.headers.get("Retry-After", "")
        try:
            retry_after = float(ra)
        except (ValueError, TypeError):
            pass
        raise DoubaoRateLimitError(
            f"豆包 API 429 限流: {resp.text[:200]}",
            retry_after=retry_after,
        )
    if resp.status_code == 404:
        raise DoubaoUnavailableError(
            f"豆包 API 404 接口/模型不可用（url={url} model={model_id}）: {resp.text[:200]}"
        )
    if resp.status_code == 503:
        raise DoubaoUnavailableError(
            f"豆包 API 503 服务不可用: {resp.text[:200]}"
        )
    if resp.status_code == 403:
        raise DoubaoUnavailableError(
            f"豆包 API 403 鉴权失败（API Key 无效或无权限）: {resp.text[:200]}"
        )

    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise DoubaoError(f"豆包 API HTTP 错误 {resp.status_code}: {resp.text[:200]}") from e

    data = resp.json()

    text = _extract_text(data)
    if text is None:
        raise DoubaoError(
            f"无法从豆包 API 响应中解析文本，响应键: {list(data.keys()) if isinstance(data, dict) else type(data)}"
        )
    return text.strip(), _extract_usage(data)


def _extract_text(data: Any) -> Optional[str]:
    """从 API 响应 dict 中提取文本，兼容多种 Ark 响应结构。"""
    if not isinstance(data, dict):
        return None

    output = data.get("output")
    if output is None and "data" in data:
        output = (data.get("data") or {}).get("output")

    # 1. output.text
    if isinstance(output, dict) and "text" in output:
        return output.get("text")

    # 2. output.choices[0].message.content
    if isinstance(output, dict) and "choices" in output:
        choices = output.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message")
            if isinstance(msg, dict):
                return msg.get("content")

    # 3. 顶层 choices[0].message.content（OpenAI 兼容）
    if "choices" in data:
        choices = data.get("choices") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message")
            if isinstance(msg, dict):
                return msg.get("content")

    # 4. output 直接为字符串
    if isinstance(data.get("output"), str):
        return data.get("output")

    # 5. output 为 list（Ark Responses API 新版）
    if isinstance(output, list):
        parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("text"):
                parts.append(str(item["text"]))
            elif item.get("content") is not None:
                c = item["content"]
                if isinstance(c, str):
                    parts.append(c)
                elif isinstance(c, list):
                    for block in c:
                        if isinstance(block, dict) and "text" in block:
                            parts.append(block["text"] or "")
        if parts:
            return "\n".join(parts)

    # 6. output.results 数组
    if isinstance(output, dict) and "results" in output:
        parts = [r.get("text", "") for r in (output.get("results") or []) if isinstance(r, dict) and r.get("text")]
        if parts:
            return "\n".join(parts)

    # 7. output.message.content
    if isinstance(output, dict):
        msg = output.get("message")
        if isinstance(msg, dict) and msg.get("content"):
            return msg["content"]

    return None


def parse_json_from_text(raw: str) -> Dict[str, Any]:
    """从模型返回的文本中解析 JSON。支持整段为 JSON，或 ```json ... ``` 代码块。"""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for pattern in (r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"):
        m = re.search(pattern, raw)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
    raise ValueError("模型返回文本中未找到有效 JSON")
