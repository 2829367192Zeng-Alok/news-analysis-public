# 金融新闻分析系统飞书推送与健康告警参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 适用代码：`feishu_webhook/`（`service.py`、`alert_service.py`、`webhook_client.py`）、`pipeline_notify_format.py`

项目的飞书能力分为两条独立链路：

1. **分析结果推送**（业务消息）：每轮分析出的新结果推送到群；
2. **健康/API 告警**（运维消息）：流水线停摆或 API 异常时提醒人工介入。

两条链路共用同一组 `FEISHU_WEBHOOK_URL`，失败都只记日志、不阻断主流程。

---

## 1. 模块结构

```text
feishu_webhook/
├── __init__.py          # 导出 push_analysis_details / PipelineHealthChecker
├── webhook_client.py    # HTTP 层：发送文本消息，自动区分机器人/Flow 两种格式
├── service.py           # 业务推送：push_analysis_details()
└── alert_service.py     # 健康告警：PipelineHealthChecker()
pipeline_notify_format.py # 推送文案格式化（根目录）
```

---

## 2. Webhook 客户端（webhook_client.py）

`send_text_message(webhook_url, text, timeout=30)` 根据URL 自动选择 payload：

| 类型 | URL 特征 | payload |
|---|---|---|
| 自定义机器人 | `open.feishu.cn/open-apis/bot/v2/hook/` | `{"msg_type":"text","content":{"text":...}}` |
| 自动化 Flow 触发器 | `feishu.cn/flow/api/trigger-webhook/` | `{"content": ...}`（平铺 JSON） |

返回体校验：

- `code != 0` 抛错（业务错误）；
- `StatusCode != 0` 抛错（部分网关）。

---

## 3. 分析结果推送（service.py）

`push_analysis_details(details)`：

1. 检查 `FEISHU_WEBHOOK_ENABLED`；
2. 遍历本轮新增 `NewsAnalysisDetail`；
3. 用 `pipeline_notify_format.format_analysis_message()` 生成文案；
4. 逐条发到所有配置的群 URL，群间隔 `FEISHU_PUSH_SEND_DELAY_MS`；
5. 单条失败仅告警日志。

### 3.1 文案格式（pipeline_notify_format.py）

```text
【资讯】{标题}
方向：利多黄金｜影响强度 4/5
结论：{conclusion 截断至 400 字}
详情：https://goldnews-analysis.easypus.com/
```

方向标签映射：

- `direction > 0` → 利多黄金
- `direction < 0` → 利空黄金
- `0 / None` → 方向不确定 / 未给出

### 3.2 触发位置

- `run_task.py`：步骤 3 分析完成后推送；
- `run_pipeline_90s.py`：步骤 4 推送本轮 `new_details`；
- `run_pipeline_manual.py`：同样推送。

推送异常在所有入口都被包裹，不影响流水线状态。

---

## 4. 健康检查与告警（alert_service.py）

### 4.1 `PipelineHealthChecker`

流水线进程内单例（`run_task.py` / `run_pipeline_90s.py` 各持一份），每轮结束调用 `check_and_alert()`。

### 4.2 告警类型

| 告警 | 触发条件 | 默认阈值 |
|---|---|---|
| 【告警】采集层停止 | `raw_news.create_time` 最新值超阈值 | 30 分钟 |
| 【告警】分析层停止 | `news_analysis_detail.create_time` 最新值超阈值 | 60 分钟 |
| 【API告警】 | 筛选/分析步骤出现接口不可用或 429 | 即时 |
| 【恢复】采集/分析层已恢复 | 停摆后重新有写入 | 每类一次 |

### 4.3 抑制与恢复

- 同类告警在 `ALERT_SUPPRESS_MINUTES`（默认 60 分钟）内不重复发送；
- 恢复通知只发一次；
- 状态持久化到项目根 `.alert_state.json`（`last_alert` 时间戳 + `alerting` 标志），进程重启后抑制窗口仍然有效。

### 4.4 消息内容示例

```text
【告警】分析层停止（已停止约 73 分钟）
时间：2026-09-07 10:00:00
最后分析写入：2026-09-07 08:47:12
阈值：超过 60 分钟无新数据触发
可能原因：豆包 API 限流(429) / 接口变更(404) / API Key 失效
请检查 logs/ 中最新报错，并前往豆包控制台确认账户状态。
```

---

## 5. 排障指引

| 现象 | 排查 |
|---|---|
| 群里收不到分析推送 | `FEISHU_WEBHOOK_ENABLED` 是否开启；`FEISHU_WEBHOOK_URL` 是否配置；机器人是否被限频 |
| 收到【API告警】404/403 | 模型 ID 是否下线、API Key 是否失效、base_url 是否变更 |
| 收到【API告警】429 | 豆包配额用尽；确认是否需要升级或降频 |
| 告警重复轰炸 | 检查 `.alert_state.json` 是否被误删（删掉会重置抑制窗口） |
| Flow 触发器收不到 | 确认 URL 属于 Flow 类型（payload 平铺），触发器变量名应为 `content` |

---

## 6. 修改注意

1. 新增推送字段时同步改 `pipeline_notify_format.py` 与 `service.py`；
2. 不要在推送链路里抛异常中断流水线（现有入口都按“失败仅日志”处理）；
3. Webhook URL 属敏感配置，只放 `.env`，不得写进文档或提交库；
4. 调整告警阈值优先用环境变量，不要硬编码。
