# 金融新闻分析系统部署与运维参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 用途：生产部署、环境变量、调度、展示站与告警运维的统一参考。历史逐步操作记录见 `docs/` 下各部署专题文档。

---

## 1. 部署拓扑

```text
阿里云定时任务（每 90 秒）
   │  触发
   ▼
ECS（/root/workspace/project/financial-news-analysis）
   ├── run_pipeline_90s_loop.sh（flock 防并发 + timeout 85s）
   │      └── run_pipeline_90s.py（采集→筛选→分析→推送→健康检查）
   ├── gunicorn app:app（Flask 动态站 :8000）
   └── sync_loop.sh ──> sync_news_to_display.py ──> Nginx 静态展示站
   │
   ▼（RDS 内网连接）
RDS（MySQL 或 PostgreSQL，库名 news_analysis）
```

- ECS 与 RDS 必须同地域/同 VPC，`DB_HOST` 填**内网地址**；
- 展示域名：`goldnews-analysis.easypus.com`（Nginx + SSL，配置模板 `scripts/nginx-domain-ssl.conf`）。

---

## 2. 环境变量清单

配置加载顺序（`config.py`）：环境变量 → `~/.financial_news_analysis.env` → 项目目录 `.env`（后加载覆盖先加载）。

### 2.1 数据库

| 变量 | 说明 |
|---|---|
| `DB_DIALECT` | `mysql`（默认）或 `postgresql` |
| `DATABASE_URL` | 完整 SQLAlchemy URL，最高优先级 |
| `DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME` | 旧 MySQL 变量（ECS 上填 RDS 内网地址） |
| `MYSQL_*` | 显式 MySQL 变量（迁移脚本用） |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB_NAME` | PostgreSQL 连接 |
| `POSTGRES_SSLMODE` | 阿里云 RDS PG 通常 `require` |

### 2.2 API

| 变量 | 说明 |
|---|---|
| `TUSHARE_TOKEN` | Tushare Pro token |
| `DOUBAO_API_KEY` | 火山引擎 Ark API Key |
| `DOUBAO_API_BASE_URL` | 默认 `https://ark.cn-beijing.volces.com` |
| `DOUBAO_MODEL_ID` | 默认模型 / 接入点 ID |
| `DOUBAO_MODEL_ID_FILTER` / `DOUBAO_MODEL_ID_ANALYZE` | 分阶段模型（留空回退默认） |

### 2.3 飞书推送与告警

| 变量 | 说明 | 默认 |
|---|---|---|
| `FEISHU_WEBHOOK_ENABLED` | `1/true/yes` 开启 | 关 |
| `FEISHU_WEBHOOK_URL` | 机器人 Webhook，逗号/分号分隔多群 | — |
| `FEISHU_PUSH_WEB_BASE_URL` | 推送内“详情”链接 | `https://goldnews-analysis.easypus.com` |
| `FEISHU_PUSH_CONCLUSION_MAX_LEN` | 结论截断长度 | 400 |
| `FEISHU_PUSH_SEND_DELAY_MS` | 多群发送间隔 | 400 |
| `ALERT_RAW_STALE_MINUTES` | 采集层停滞告警阈值 | 30 |
| `ALERT_ANALYZE_STALE_MINUTES` | 分析层停滞告警阈值 | 60 |
| `ALERT_SUPPRESS_MINUTES` | 同类告警抑制窗口 | 60 |

### 2.4 其他

| 变量 | 说明 |
|---|---|
| `FETCH_WINDOW_MINUTES` | manual/90s 流水线采集窗口（90s 版 shell 中固定导出 1.5） |
| `MACRO_BASELINE_PATH` | 宏观基线文件显式路径（不设走默认查找） |

> `.env` 与 `~/.financial_news_analysis.env` 含密钥，禁止提交版本库、禁止写入文档。

---

## 3. 标准部署步骤（ECS）

1. 上传/clone 仓库到 `/root/workspace/project/financial-news-analysis`
2. `pip install -r requirements.txt`
3. 配置 `.env`（DB 用 RDS 内网地址）
4. `python init_db.py`（建表 + 补列，幂等可重复跑）
5. 配置阿里云定时任务：每 90 秒执行 `bash run_pipeline_90s_loop.sh`
6. 启动 Web：`gunicorn -w 2 -b 0.0.0.0:8000 "app:app"`（systemd/supervisor 守护）
7. 静态展示：部署 `web_display/` 到 Nginx 站点根，并以 `scripts/sync_loop.sh` 或 cron 常驻同步
8. 安全组：放行 8000（或仅 Nginx 80/443）

验收检查：

- [ ] `python check_db.py` 输出 `DB_OK`
- [ ] 定时任务日志（`logs/pipeline_1min.log`）有正常轮次
- [ ] `/api/news`、`/api/stats` 可访问
- [ ] 静态站 `feed.json` 时间戳在更新
- [ ] 飞书群能收到分析推送与告警测试

---

## 4. 数据库运维

- **初始化/补列**：`python init_db.py`
- **MySQL → PostgreSQL 迁移**：
  1. 配置 `MYSQL_*` 与 `POSTGRES_*` 双库变量
  2. `DB_DIALECT=postgresql python init_db.py`
  3. `python scripts/migrate_mysql_to_postgres.py`（默认清空目标表；`--no-truncate` 追加）
- **CSV 救援导入**：`python scripts/import_csv_to_postgres.py`
- **历史回补**：`python scripts/backfill_12h_windows.py`
- 回滚说明：`words/postgresql_to_mysql_rollback.md`

---

## 5. 日常运维

### 5.1 日志位置

| 内容 | 位置 |
|---|---|
| 90s 流水线 | ECS `logs/pipeline_1min.log` |
| 静态站同步 | `/tmp/sync_news_display.log` |
| 手动流水线报告 | 项目根 `pipeline_report.txt` |
| 抽查分析报告 | 项目根 `analysis_report.txt` |

### 5.2 常用检查命令

```bash
systemctl status financial-news        # Web 服务（若已注册 systemd）
tail -n 200 logs/pipeline_1min.log     # 最近流水线日志
python check_db.py                     # 库连通性
python scripts/check_raw_relevance.py  # schema 排查
pytest tests/ -q                       # 单元测试
```

### 5.3 告警语义

- 【告警】采集层停止 / 分析层停止：对应表超过阈值无新 `create_time`；
- 【API告警】步骤N出现 404/403/429：需要人工检查 `.env` 中模型配置或账户状态；
- 【恢复】通知：数据恢复写入后每类只发一次；
- 告警抑制状态持久化在项目根 `.alert_state.json`，进程重启后仍生效。

### 5.4 并发保护

`run_pipeline_90s_loop.sh` 使用 `flock -n /tmp/pipeline_financial_news.lock`：上一轮未结束时本轮直接跳过，不排队。

---

## 6. 相关文档索引

| 文档 | 内容 |
|---|---|
| `docs/部署Web展示系统.md` | 展示站部署细节 |
| `docs/上传并部署到ECS.md` | 代码上传与首次部署步骤 |
| `docs/上传流水线脚本到ECS.md` | 流水线脚本上服务器步骤 |
| `docs/域名部署协作步骤.md` | 域名解析与 SSL 协作记录 |
| `docs/Nginx单行部署说明.md` | Nginx 最小配置说明 |
| `docs/连接服务器与操作数据库.md` | SSH 连接与数据库操作 |
| `docs/服务器与配置检索结果.md` | 服务器/配置信息检索记录 |
