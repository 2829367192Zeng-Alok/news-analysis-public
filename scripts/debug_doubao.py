#!/usr/bin/env python3
"""临时：打印豆包 API 返回的 output 结构。"""
from __future__ import annotations

import sys

sys.path.insert(0, ".")

from doubao_client import chat_with_usage


if __name__ == "__main__":
    text, usage = chat_with_usage(user_text="回复：OK", timeout=15, max_retries=0)
    print("response:", text)
    print("usage:", usage)
