# 临时脚本：打印豆包筛选 API 返回的原始内容与解析结果
from doubao_client import chat, parse_json_from_text
from prompts import FILTER_PROMPT_TEMPLATE

title, content = "A股航运板块持续走强", "简短测试内容"
user_text = FILTER_PROMPT_TEMPLATE.format(title=title, content=(content or "")[:8000])
raw_text = chat(user_text=user_text, timeout=30)
print("raw_text type:", type(raw_text))
print("raw_text (first 800 chars):", repr(raw_text[:800]))
data = parse_json_from_text(raw_text)
print("parsed data type:", type(data))
print("parsed data:", data)
if isinstance(data, dict):
    print("keys:", list(data.keys()))
