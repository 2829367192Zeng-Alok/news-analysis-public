# 金融新闻分析系统 LLM 调用架构参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 适用代码：`doubao_client.py`、`prompts.py`、`prompts_new.py`、`news_filter.py`、`news_analyzer.py`

本文说明项目的 LLM（豆包 / 火山引擎 Ark）调用封装、异常分类、重试策略、提示词组织和 token 统计方式。涉及模型更换、提示词调整或异常处理的修改，都应先阅读本文。

---

## 1. 总体结构

```text
news_filter / news_analyzer
        │
        ▼
doubao_client（统一入口）
        │
        ▼
OpenAI SDK（Responses API）
        │
        ▼
火山引擎 Ark（豆包模型）
```

所有业务代码都必须通过 `doubao_client.py` 调用模型，不允许绕过封装直接发 HTTP 请求。

---

## 2. `doubao_client.py` 核心 API

### 2.1 `chat()`

```python
chat(model=None, user_text="", timeout=60, system_text=None) -> str
```

返回纯文本回复，默认内置 4 次重试。

### 2.2 `chat_with_usage()`

```python
chat_with_usage(model=None, user_text="", timeout=60, max_retries=3, system_text=None) -> (str, usage)
```

在回复之外同时返回 token 用量：

- `input_tokens`
- `output_tokens`
- `total_tokens`

筛选与分析阶段都用该函数做 token 统计。

### 2.3 `parse_json_from_text()`

负责从模型回复中提取 JSON：

- 优先直接 `json.loads`；
- 回退解析 ```json``` 代码块；
- 失败抛 `ValueError`。

---

## 3. 异常分类与处理策略

### 3.1 异常类型

- `DoubaoError`：基础异常
- `DoubaoRateLimitError`：429 限流
- `DoubaoUnavailableError`：404 / 403 / 503 等不可用状态

### 3.2 处理原则

| 异常 | 客户端层 | 流水线层 |
|---|---|---|
| 429 限流 | 指数退避重试（4s–64s，尊重 Retry-After） | 记告警后跳过本轮 |
| 404 / 403 | 立即抛出，不重试 | 记告警后终止本轮 |
| 超时 / 连接失败 | 在重试次数内重试 | 记日志 |
| JSON 解析失败 | 不在客户端层处理 | 单条忽略并计数 |

### 3.3 熔断策略

`news_filter` 和 `news_analyzer` 内部有“连续相同错误 ≥ 2 次熔断”的保护逻辑，用于避免无意义地烧 token。

---

## 4. 模型配置

配置位于 `config.py` 的 `DoubaoConfig`：

- `DOUBAO_API_KEY`：API Key
- `DOUBAO_API_BASE_URL`：默认 `https://ark.cn-beijing.volces.com`
- `DOUBAO_MODEL_ID`：默认模型
- `DOUBAO_MODEL_ID_FILTER`：筛选阶段模型（可选）
- `DOUBAO_MODEL_ID_ANALYZE`：分析阶段模型（可选）

规则：

- 筛选阶段优先 `DOUBAO_MODEL_ID_FILTER`，为空回退 `DOUBAO_MODEL_ID`；
- 分析阶段优先 `DOUBAO_MODEL_ID_ANALYZE`，为空回退 `DOUBAO_MODEL_ID`；
- 模型 ID 可以是模型名，也可以是在线推理接入点 ID。

---

## 5. 提示词体系

### 5.1 `prompts.py`（v1，默认运行版）

- `FILTER_PROMPT_TEMPLATE`：筛选阶段，输出 `{relevance, direction, impact}`；
- `ANALYZE_PROMPT_TEMPLATE`：详细分析阶段，输出与 `news_analysis_detail` 表对齐的 25 字段 JSON。

### 5.2 `prompts_new.py`（v2，`USE_PROMPTS_V2` 控制，默认关闭）

- `FILTER_PROMPT_TEMPLATE`：更宽松的筛选门控（"宁可放行存疑新闻"）；
- `SYSTEM_PROMPT_TEMPLATE`：宏观基线注入的 System Prompt；
- 配合 `macro_baseline.py` 使用，将人工维护的宏观基线（美联储立场、实际利率、美元指数、金价、情绪动量、地缘风险等级、人工研判层）注入上下文；
- 分析输出额外包含 `confidence`（0–100 自评置信度）与 `uncertain`（路径冲突/低置信标记），落库至 `news_analysis_detail` 两个可空列。

**切换机制（2026-09-07 接入）**：`news_filter.call_doubao_filter_api` / `news_analyzer.call_doubao_analyze_api` 按 `settings.doubao.use_prompts_v2`（环境变量 `USE_PROMPTS_V2`）选择模板与 System Prompt；关闭时行为与 v1 完全一致。**开闸前置条件**：先跑 `init_db.py` 建列 + 维护 `config/macro_baseline.yaml`，详见 `docs/production_update_ops_2026-09-07.md` §3。

### 5.3 提示词 A/B 对比

`scripts/compare_prompts_on_selected_csv.py` 支持在同一批 CSV 上对比旧/新提示词效果，修改提示词前建议先做一次 A/B；`tests/run_prompt_compare.py` 可在整批真实新闻上离线对比 v1/v2 的筛选与分析差异（含 token 成本）。

---

## 6. 宏观基线机制

`macro_baseline.py` 负责加载人工维护的基线文件：

- 查找顺序：`config/macro_baseline.yaml` → `.yml` → `.json` → `config/macro_baseline.example.yaml` → 空基线；
- 支持环境变量 `MACRO_BASELINE_PATH` 显式指定；
- 输出的字段与 `SYSTEM_PROMPT_TEMPLATE` 占位符一一对应。

基线使用原则（写入 System Prompt）：

1. 新闻影响是基线上的边际变化，不是绝对判断；
2. 人工研判层提供长链路逻辑，优先于简单线性推断；
3. 新闻与基线矛盾时须在 `conclusion` 中显式说明。

---

## 7. Token 用量统计

流水线入口（`run_task.py`、`run_pipeline_90s.py`、`run_pipeline_manual.py`）通过 `token_accumulator` 列表收集每轮用量，再由 `_sum_usage()` 汇总输出：

- 筛选阶段：`filter_tokens`
- 分析阶段：`analyze_tokens`

日志示例：

```text
步骤2 筛选: 新增 3 条, 耗时 4.21s, tokens=5231
步骤3 分析: 新增 2 条, 耗时 18.90s, tokens=14028
```

---

## 8. 修改 LLM 相关代码时的检查清单

- [ ] 是否继续通过 `doubao_client.py` 调用？
- [ ] 新异常是否需要映射为 `DoubaoRateLimitError` / `DoubaoUnavailableError`？
- [ ] 提示词输出字段是否与 `news_analysis_detail` 一致？
- [ ] 是否需要更新 `prompts_new.py` 的 v2 版本？
- [ ] 是否影响 token 统计？
- [ ] 是否需要同步更新 `docs/pipeline_reference.md` 与 `docs/project_context_index.md`？

---

## 9. 已知注意事项

1. 分析阶段 `max_retries=0`，不在客户端层重试，因为单次调用昂贵。
2. 筛选阶段 `timeout=30s`，分析阶段 `timeout=240s`，不要随意调小。
3. `parse_json_from_text` 对“模型输出多余说明文字”容忍度有限，调整提示词时要保持“仅输出 JSON”。
4. `Reference` 是历史遗留字段名（首字母大写），模型输出和数据库列名都保持一致，不要单方面改名。
