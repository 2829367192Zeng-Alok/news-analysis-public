# -*- coding: utf-8 -*-
"""
豆包（火山引擎 Ark）Responses API 调用封装 — OpenAI SDK 版。

通过 OpenAI SDK 调用 Ark Responses API：
  base_url : https://ark.cn-beijing.volces.com/api/v3
  model    : 豆包模型名（如 doubao-seed-1-8-251228）
             或在线推理接入点 ID（如 ep-20250101xxxxxx-xxxxx）

v3 改动：
- 底层从 requests 手动 HTTP 改为 OpenAI SDK（client.responses.create）
- 响应解析由 SDK 接管，_extract_text() 的 7 个 fallback 分支精简为对象属性访问
- 异常捕获从 HTTP 状态码判断改为 openai 异常类型匹配
- 新增模块级客户端单例（_get_client），避免每次调用重建连接
- 所有公开接口签名（chat / chat_with_usage / parse_json_from_text）保持不变
- 所有自定义异常类（DoubaoError / DoubaoRateLimitError / DoubaoUnavailableError）保持不变
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import openai
from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


# ---------- 自定义异常（保持不变）----------

class DoubaoError(RuntimeError):
    """豆包 API 调用基础异常。"""


class DoubaoRateLimitError(DoubaoError):
    """429 Too Many Requests：触发限流，调用方应回退等待。"""
    def __init__(self, msg: str = "", retry_after: float = 0.0):
        super().__init__(msg)
        self.retry_after = retry_after


class DoubaoUnavailableError(DoubaoError):
    """404 / 403 / 503 接口或模型不可用：配置或服务端问题，重试无意义。"""


# ---------- OpenAI SDK 客户端（懒加载单例）----------

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """
    返回模块级缓存的 OpenAI 客户端，首次调用时初始化。
    max_retries=0：重试策略由 chat_with_usage() 统一控制，不交给 SDK。
    """
    global _client
    if _client is None:
        base = (settings.doubao.api_base_url or "https://ark.cn-beijing.volces.com").rstrip("/")
        # OpenAI SDK 要求 base_url 包含 /api/v3
        if not base.endswith("/api/v3"):
            base = f"{base}/api/v3"
        _client = OpenAI(
            api_key=settings.doubao.api_key or "placeholder",
            base_url=base,
            max_retries=0,
        )
    return _client


# ---------- 内部工具函数 ----------

def _build_content(text: str) -> List[Dict[str, str]]:
    """构建 Responses API input content 块（input_text 类型）。"""
    return [{"type": "input_text", "text": text}]


def _extract_text_from_response(response: Any) -> Optional[str]:
    """
    从 SDK 响应对象中提取文本内容。
    1. 优先用 output_text 快捷属性（openai SDK >= 1.x Responses API）
    2. 回退到遍历 output 列表中的 content 块
    """
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)

    for item in (getattr(response, "output", None) or []):
        for block in (getattr(item, "content", None) or []):
            text = getattr(block, "text", None)
            if text:
                return str(text)
    return None


def _extract_usage_from_response(response: Any) -> Dict[str, int]:
    """从 SDK 响应对象中提取 token 用量。"""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_t = int(getattr(usage, "input_tokens", 0) or 0)
    output_t = int(getattr(usage, "output_tokens", 0) or 0)
    total_t = int(getattr(usage, "total_tokens", 0) or 0)
    if total_t == 0:
        total_t = input_t + output_t
    return {"input_tokens": input_t, "output_tokens": output_t, "total_tokens": total_t}


# ---------- 公开 API（签名保持不变）----------

def chat(
    model: Optional[str] = None,
    user_text: str = "",
    timeout: int = 60,
    system_text: Optional[str] = None,
) -> str:
    """调用豆包 API，返回模型回复的纯文本。遇 429 做指数退避重试（最多 4 次）。"""
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
    同 chat()，但同时返回 (回复文本, token 用量)。
    - max_retries=0：仅请求 1 次，不重试。
    - 429 限流：指数退避（最小 4s，最大 64s），优先采用响应头 Retry-After。
    - 404 / 403 / 503：立即抛 DoubaoUnavailableError，不消耗重试次数。
    """
    last_err: Optional[Exception] = None
    attempts = max(1, max_retries + 1)

    for attempt in range(attempts):
        try:
            return _chat_once(model, user_text, timeout, system_text=system_text)
        except DoubaoUnavailableError:
            raise
        except DoubaoRateLimitError as e:
            last_err = e
            if attempt >= attempts - 1:
                break
            wait = min(64.0, max(4.0, 2 ** (attempt + 2)))
            if e.retry_after > 0:
                wait = min(64.0, e.retry_after)
            logger.warning(
                "豆包 429 限流，等待 %.1fs 后重试（attempt %s/%s）",
                wait, attempt + 1, attempts,
            )
            time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                time.sleep(min(16.0, 1.0 * (attempt + 1)))

    raise last_err  # type: ignore


# ---------- 核心调用（单次请求，不含重试）----------

def _chat_once(
    model: Optional[str],
    user_text: str,
    timeout: int,
    system_text: Optional[str] = None,
) -> Tuple[str, Dict[str, int]]:
    if not settings.doubao.api_key:
        raise DoubaoError("未配置 DOUBAO_API_KEY，请在 .env 中设置")

    model_id = (model or settings.doubao.model_id or "").strip()
    if not model_id:
        raise DoubaoError("未配置豆包模型 ID，请在 .env 中设置 DOUBAO_MODEL_ID")

    # 构建 Responses API input 列表
    input_messages: List[Dict[str, Any]] = []
    if system_text and str(system_text).strip():
        input_messages.append({
            "role": "system",
            "content": _build_content(str(system_text).strip()),
        })
    input_messages.append({
        "role": "user",
        "content": _build_content(user_text),
    })

    try:
        response = _get_client().responses.create(
            model=model_id,
            input=input_messages,
            timeout=float(timeout),
        )
    except openai.RateLimitError as e:
        retry_after = 0.0
        try:
            retry_after = float(e.response.headers.get("Retry-After", 0))
        except Exception:
            pass
        raise DoubaoRateLimitError(f"豆包 API 429 限流: {e}", retry_after=retry_after)
    except openai.NotFoundError as e:
        raise DoubaoUnavailableError(
            f"豆包 API 404 接口/模型不可用（model={model_id}）: {e}"
        )
    except openai.AuthenticationError as e:
        raise DoubaoUnavailableError(f"豆包 API 鉴权失败（API Key 无效或无权限）: {e}")
    except openai.APITimeoutError as e:
        raise DoubaoError(f"豆包 API 请求超时（{timeout}s）: {e}")
    except openai.APIConnectionError as e:
        raise DoubaoError(f"豆包 API 连接失败: {e}")
    except openai.APIStatusError as e:
        raise DoubaoError(f"豆包 API HTTP 错误 {e.status_code}: {e}")

    text = _extract_text_from_response(response)
    if not text:
        raise DoubaoError(f"无法从豆包 API 响应中提取文本，响应对象: {response!r}")

    return text.strip(), _extract_usage_from_response(response)


# ---------- 工具函数（保持不变）----------

def parse_json_from_text(raw: str) -> Dict[str, Any]:
    """从模型返回的文本中解析 JSON。支持整段为 JSON 或 ```json ... ``` 代码块。"""
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
