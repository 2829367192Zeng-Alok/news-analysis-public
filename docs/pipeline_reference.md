# 金融新闻分析系统数据流水线参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 适用代码：`run_task.py`、`run_pipeline_90s.py`、`run_pipeline_manual.py`、`news_fetcher.py`、`news_filter.py`、`news_analyzer.py`

本文说明项目核心数据流水线：每一轮任务如何从新闻源走到展示层，各阶段的输入、输出、判重和容错策略。

---

## 1. 流水线总览

```text
Tushare 新闻源
    │
    ▼
news_fetcher.fetch_latest_news()
    │  生成/去重
    ▼
raw_news
    │
    ▼
news_filter.filter_news()
    │  AI 判断相关性
    ▼
selected_news
    │
    ▼
news_analyzer.analyze_news()
    │  AI 结构化分析
    ▼
news_analysis_detail
    │
    ├──> app.py（Web API / 页面）
    ├──> sync_news_to_display.py（静态展示）
    └──> feishu_webhook（推送与健康告警）
```

---

## 2. 阶段一：采集

### 2.1 主要文件

- `news_sources.py`：来源配置
- `news_fetcher.py`：采集与入库

### 2.2 核心函数

```python
fetch_latest_news(minutes, source_ids) -> (List[RawNews], List[str])
```

### 2.3 执行流程

1. 读取来源列表；
2. 构建 Tushare 客户端；
3. 按时间窗拉取每来源新闻；
4. 归一化标题、正文、时间；
5. 计算内容哈希；
6. 同源去重；
7. 跨源去重；
8. 与库内已有 `raw_news.content_hash` 比对；
9. 写入新记录。

### 2.4 判重策略

当前采用多层去重：

1. 同来源内部去重
2. 跨来源去重
3. 与数据库历史记录去重
4. 时间窗过滤

### 2.5 输出

- 新增的 `RawNews` 记录列表
- 对应 `content_hash` 列表，供后续阶段只处理本批增量

---

## 3. 阶段二：筛选

### 3.1 主要文件

- `news_filter.py`
- `prompts.py`

### 3.2 核心函数

```python
filter_news(limit, token_accumulator, only_content_hashes) -> List[SelectedNews]
```

### 3.3 执行流程

1. 查询 `raw_news.relevance IS NULL` 的记录；
2. 如传入 `only_content_hashes`，只处理该批哈希；
3. 对每条新闻调用豆包筛选；
4. 解析 JSON 输出；
5. 更新 `raw_news.relevance`；
6. 若相关，写入 `selected_news`。

### 3.4 输出结构

AI 期望返回：

```json
{
  "relevance": true,
  "direction": 0,
  "impact": 0
}
```

### 3.5 容错策略

- 豆包接口不可用时立即终止本轮；
- 豆包限流时由 `doubao_client` 指数退避；
- 单条解析失败仅记日志；
- 同一错误连续出现两次以上会熔断本轮，避免浪费 token。

---

## 4. 阶段三：详细分析

### 4.1 主要文件

- `news_analyzer.py`
- `prompts.py`
- `macro_baseline.py`（配合 `prompts_new.py` 使用）

### 4.2 核心函数

```python
analyze_news(limit, token_accumulator) -> List[NewsAnalysisDetail]
```

### 4.3 执行流程

1. 查询 `selected_news` 中尚未进入 `news_analysis_detail` 的记录；
2. 对每条调用豆包详细分析；
3. 解析多字段 JSON；
4. 规范化字段；
5. 写入 `news_analysis_detail`；
6. 每条成功后立即提交。

### 4.4 输出结构

分析输出覆盖五维传导路径：

- 美债实际利率
- 美元指数
- 地缘政治风险
- 资本市场流动性
- 市场情绪

以及三档时间维度结论：

- 短期
- 中期
- 长期

最终输出 `insight` 与 `conclusion`。

### 4.5 与筛选阶段的区别

| 维度 | 筛选 | 详细分析 |
|---|---|---|
| 输入 | `raw_news` | `selected_news` |
| 输出 | `selected_news` | `news_analysis_detail` |
| 目标 | 判断是否相关 | 输出结构化分析 |
| 调用成本 | 低 | 高 |
| 超时 | 较短 | 较长 |

---

## 5. 阶段四：展示与推送

### 5.1 展示层读取

Web 与静态展示都只读 `news_analysis_detail`：

- `app.py` 直接查询数据库；
- `sync_news_to_display.py` 导出 JSON 供纯静态页使用。

### 5.2 飞书推送

- `feishu_webhook/service.py` 推送本轮分析摘要；
- `pipeline_notify_format.py` 负责文案；
- 推送失败只记日志，不阻塞主流程。

### 5.3 健康检查

`feishu_webhook/alert_service.py` 提供 `PipelineHealthChecker`：

- 检查 `raw_news` 最新写入时间；
- 检查 `news_analysis_detail` 最新写入时间；
- 超过阈值触发飞书告警；
- 支持告警抑制与恢复通知。

---

## 6. 定时任务入口

### 6.1 `run_task.py`

适用场景：

- 通用定时任务；
- 手动触发一轮全链路。

特点：

- 每阶段独立异常处理；
- 失败不影响后续阶段重试；
- 附带健康检查。

### 6.2 `run_pipeline_90s.py`

适用场景：

- 服务器上高频调度；
- 每轮只处理最近的 N 秒/分钟窗口（`FETCH_WINDOW_MINUTES`，默认 1.5）。

特点：

- 只处理本批新增哈希；
- **补偿筛选**：存在超过 `CATCHUP_STALE_MINUTES`（默认 30 分钟）仍未筛选的 raw_news 时，限量（`CATCHUP_FILTER_LIMIT`，默认 15）补筛，避免故障窗口数据滞留；
- **按批分析**：未触发补偿时，`analyze_news(only_content_hashes=本批 hash)` 只分析本批，避免历史积压把单轮拖过 shell timeout（`TIMEOUT_SEC` 默认 240，等于单条分析超时）；
- 每阶段有耗时与 token 统计；
- 无新数据时直接跳过本批筛选。

### 6.3 `run_pipeline_manual.py`

适用场景：

- 本地调试；
- 人工复盘一轮结果。

特点：

- 支持通过环境变量 `FETCH_WINDOW_MINUTES` 调整窗口；
- 输出 `pipeline_report.txt`；
- 适合排查历史积压。

### 6.4 选择建议

| 场景 | 推荐入口 |
|---|---|
| 服务器定时轮询 | `run_pipeline_90s.py` |
| 单机定时 | `run_task.py` |
| 本地联调 | `run_pipeline_manual.py` |
| 抽查最新数据 | `run_analysis_latest_20.py` |

---

## 7. 幂等与重复运行

当前设计允许同一轮流水线被安全地重复运行：

1. 采集阶段依赖 `content_hash` 去重；
2. 筛选阶段依赖 `relevance IS NULL`；
3. 分析阶段依赖 `content_hash` 是否已存在。

因此：

- 同一条新闻不会重复采集；
- 已筛选新闻不会重复筛选；
- 已分析新闻不会重复分析。

---

## 8. 常见问题排查

### 8.1 `raw_news` 无新增

可能原因：

- Tushare Token 失效；
- 时间窗为空；
- 网络问题；
- 数据库连接失败。

### 8.2 `selected_news` 无新增

可能原因：

- 筛选 API 不可用；
- 豆包 API Key 失效；
- 返回 JSON 无法解析；
- 所有新闻都被判定为不相关。

### 8.3 `news_analysis_detail` 无新增

可能原因：

- 筛选结果为空；
- 分析阶段超时；
- 分析模型返回结构异常；
- 连续两次相同错误触发熔断。

---

## 9. 维护建议

1. 修改提示词前，先确认输出 JSON 字段与 `news_analysis_detail` 一致。
2. 修改去重逻辑前，先确认三张表的 `content_hash` 关联链。
3. 修改任何 AI 输出字段，需同步更新：
   - `models.py`
   - `news_analyzer.py`
   - `app.py`
   - `sync_news_to_display.py`
   - 本文档与项目总索引
