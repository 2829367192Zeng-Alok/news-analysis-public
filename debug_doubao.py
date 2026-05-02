#!/usr/bin/env python3
"""临时：打印豆包 API 返回的 output 结构。"""
import sys, json
sys.path.insert(0, ".")
import requests
from config import settings
url = (settings.doubao.api_base_url or "").rstrip("/") + "/api/v3/responses"
payload = {
    "model": settings.doubao.model_id or "doubao-seed-2-0-lite-260215",
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "回复：OK"}]}],
}
headers = {"Authorization": f"Bearer {settings.doubao.api_key}", "Content-Type": "application/json"}
r = requests.post(url, json=payload, headers=headers, timeout=15)
r.raise_for_status()
data = r.json()
out = data.get("output")
print("type(output):", type(out).__name__)
if out is not None:
    if isinstance(out, dict):
        print("output.keys():", list(out.keys()))
        for k, v in out.items():
            print(f"  output[{k!r}]: type={type(v).__name__}, repr={repr(v)[:120]}")
    elif isinstance(out, list):
        print("output len:", len(out))
        for i, x in enumerate(out[:5]):
            if isinstance(x, dict):
                print(f"  output[{i}] keys:", list(x.keys()))
                if "content" in x:
                    print(f"    .content: type={type(x['content']).__name__}, repr={repr(x['content'])[:280]}")
            else:
                print(f"  output[{i}]:", type(x).__name__, repr(x)[:120])
    else:
        print("output value:", repr(out)[:200])
else:
    print("output is None")
for i, item in enumerate(out or []):
    if isinstance(item, dict) and "content" in item:
        c = item["content"]
        print(f"  output[{i}].content type={type(c).__name__}, repr={repr(c)[:250]}")
print("full data keys:", list(data.keys()))
