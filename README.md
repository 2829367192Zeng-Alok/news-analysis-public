# 金融新闻分析系统

新闻采集（Tushare）→ AI 筛选（豆包）→ AI 详细分析（豆包）→ 云数据库存储 → Web 展示 + 飞书推送。部署于阿里云 ECS，通过内网连接云数据库 RDS。

> **新对话 / 新成员请先阅读 [docs/project_context_index.md](./docs/project_context_index.md)** —— 它是项目文档总索引，串联全部模块文档，并说明不同任务应继续读哪些材料、哪些是历史文档。

## 系统概览

一条新闻的完整生命周期：

```text
Tushare（华尔街见闻 / 新浪财经）
  → 采集 + 多层 content_hash 去重 → raw_news
  → 豆包 AI 筛选（相关性/方向/强度）→ selected_news
  → 豆包 AI 详细分析（五维传导路径 + 短中长期结论）→ news_analysis_detail
  → Flask 动态站 / Nginx 静态展示站 / 飞书群推送
```

- 调度采用服务器内常驻轮询 `python pipeline_daemon.py`（systemd 托管，20s/轮；**阿里云 90s 定时任务已弃用**，见 `docs/production_update_ops_2026-09-07.md` §4）；
- 三张表以 `content_hash` 关联，流水线可安全重跑；
- 飞书双链路：分析结果推送 + 停摆/API 异常告警（含恢复通知与告警抑制）。

## 模块速览

| 模块 | 代码 | 文档 |
|---|---|---|
| 配置 | `config.py` | `docs/deployment_reference.md` §2 环境变量 |
| 数据层 | `models.py`、`init_db.py` | `docs/project_database_schema_reference.md` |
| 采集 | `news_sources.py`、`news_fetcher.py` | `docs/pipeline_reference.md` §2 |
| 筛选 | `news_filter.py`、`prompts.py` | `docs/pipeline_reference.md` §3 |
| 分析 | `news_analyzer.py`、`macro_baseline.py` | `docs/pipeline_reference.md` §4 |
| LLM 中台 | `doubao_client.py` | `docs/llm_architecture_reference.md` |
| Web 动态站 | `app.py`、`templates/`、`static/` | `docs/web_display_reference.md` |
| 静态展示站 | `web_display/`、`sync_news_to_display.py` | `docs/web_display_reference.md` §2 |
| 飞书推送/告警 | `feishu_webhook/`、`pipeline_notify_format.py` | `docs/feishu_notification_reference.md` |
| 定时任务 | `run_task.py`、`run_pipeline_90s.py(+loop.sh)` | `docs/pipeline_reference.md` §6 |
| 脚本全集 | `scripts/`、`tests/` | `docs/project_script_architecture.md` |

## 快速开始（本地）

```bash
pip install -r requirements.txt
cp .env.example .env        # 填 DB / TUSHARE_TOKEN / DOUBAO_API_KEY（及可选 FEISHU_*）
python init_db.py           # 建表 + 补列（幂等）
python check_db.py          # 期望输出 DB_OK
python run_pipeline_manual.py           # 手动跑一轮（默认 60 分钟窗口）
python app.py                           # 起动态站 http://localhost:8000
python sync_news_to_display.py          # 导出静态站 feed.json
pytest tests/ -q                        # 单元测试
```

## 部署（ECS）

完整拓扑、环境变量清单、验收清单与运维手册见 **[docs/deployment_reference.md](./docs/deployment_reference.md)**。核心步骤：

| 步骤 | 说明 |
|---|---|
| 1 | 上传仓库到 ECS `/root/workspace/project/financial-news-analysis` |
| 2 | `pip install -r requirements.txt`，配置 `.env`（**DB_HOST 用 RDS 内网地址**） |
| 3 | `python init_db.py` 初始化表结构 |
| 4 | 调度：systemd 托管 `python pipeline_daemon.py`（20s 常驻轮询，已弃用阿里云定时任务；步骤见 `docs/production_update_ops_2026-09-07.md` §4） |
| 5 | Web：`gunicorn -w 2 --threads 8 -b 0.0.0.0:8000 app:app`（SSE 需线程模式；建议 systemd 守护） |
| 6 | 静态站：部署 `web_display/` 到 Nginx，常驻 `scripts/sync_loop.sh` 同步 |

### 数据库切换（MySQL → PostgreSQL）

```bash
# 1) 配置 MYSQL_* 与 POSTGRES_* 双库变量
# 2) 初始化 PG 表结构
DB_DIALECT=postgresql python init_db.py
# 3) 全量迁移（默认清空目标表，--no-truncate 为追加）
python scripts/migrate_mysql_to_postgres.py
```

回滚说明见 `words/postgresql_to_mysql_rollback.md`。

## 已知注意事项（详见总索引 §5 与 `docs/code_review_report_2026-09-07.md`）

- `run_pipeline_once.py` 已于 2026-09-07 删除（原文件损坏）；单轮手动执行用 `run_pipeline_manual.py`；
- `utils.compute_content_hash` 与 `news_fetcher.compute_content_hash` 已统一为 blake2b（`utils.py` 唯一实现）；历史 MD5 数据需 `scripts/normalize_content_hash.py --update` 归一（先 `--dry-run`）；
- `check_db.py` 已修复（方言无关）；部署验收可据此判断库连通性；
- `news_analysis_detail.Reference` 为历史遗留列名，勿擅自改名；
- `.env` 与 `~/.financial_news_analysis.env` 含密钥，禁止提交或写入文档。

## 文档体系

```text
docs/
├── project_context_index.md            # 文档总纲（唯一入口，先读）
├── code_review_report_2026-09-07.md    # 代码问题全景审查（43 项分级 + 修复优先级）
├── pipeline_reference.md               # 数据流水线 L1
├── project_database_schema_reference.md# 数据库结构 L1
├── llm_architecture_reference.md       # LLM 调用架构 L1
├── web_display_reference.md            # Web 双形态展示 L1
├── deployment_reference.md             # 部署与运维 L1
├── project_script_architecture.md      # 脚本权威登记 L1
├── feishu_notification_reference.md    # 飞书推送与告警 L1
├── 代码架构说明.md                      # 历史版架构说明（已被 L1 取代）
├── 金融新闻分析系统_d1f1a06f.plan.md    # 早期实施计划（仅历史参考）
└── deployment/                          # 历史逐步部署操作记录
```

修改代码后，请按 `docs/project_context_index.md` §10 的要求同步更新对应文档与总索引。
