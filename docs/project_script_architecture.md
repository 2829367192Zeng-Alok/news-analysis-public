# 金融新闻分析系统脚本架构参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 用途：登记项目全部运行入口与脚本，说明各自职责、运行方式与相互关系。新增/删除/重命名脚本时必须同步更新本文与 `docs/project_context_index.md`。

---

## 1. 生产运行入口（根目录）

| 脚本 | 职责 | 典型运行方式 | 备注 |
|---|---|---|---|
| `run_task.py` | 一轮完整流水线（采集→筛选→分析→推送→健康检查），不限本批哈希；已加 flock 单实例锁 | 阿里云定时命令 / 手动 | 各步独立 try/except |
| `run_pipeline_90s.py` | 90 秒窗口流水线：本批筛选 + 滞留补偿筛选 + 按批分析 | `run_pipeline_90s_loop.sh` 包裹，阿里云每 90 秒触发 | 窗口读 `FETCH_WINDOW_MINUTES`；补偿阈值见 `CATCHUP_*` |
| `pipeline_daemon.py` | 常驻轮询守护（默认 20s 一轮），替代阿里云触发：采集→筛选→补偿→分析→推送→**主动刷新 feed.json** | systemd 托管 / `--once` 运维验证 | **与 90s 触发二选一，勿并行**；锁名 `financial_news_daemon` |
| `run_pipeline_manual.py` | 可配置窗口（`FETCH_WINDOW_MINUTES`，默认 60 分钟）流水线，写 `pipeline_report.txt` | 手动 / 运维 | 适合本地复盘 |
| ~~`run_pipeline_once.py`~~ | （已删除 2026-09-07，原文件损坏；用 manual 代替） | — | — |
| `run_analysis_latest_20.py` | 对库中最新 20 条 `raw_news` 逐条筛选+分析并写库，导出 `analysis_report.txt` | 服务器上补分析/抽查 | 时间口径与主链路一致（北京时间） |
| `run_pipeline_90s_loop.sh` | 90 秒触发的外壳：flock 并发保护 + timeout（默认 240s）+ 日志落 `logs/pipeline_1min.log` | `bash run_pipeline_90s_loop.sh` | 部署在 ECS |
| `sync_news_to_display.py` | 导出 `news_analysis_detail` → `web_display/data/feed.json`（原子写 tmp+replace；核心逻辑 `run_sync()` 供 daemon 复用） | cron / `scripts/sync_loop.sh` / daemon 调用 | `--no-change` 增量跳过 |
| `init_db.py` | 建表 + 补列（含 v2 的 confidence/uncertain）+ 索引 + 清理遗留 `ix_*` + best-effort 创建 `uq_raw_content_hash` 唯一索引 + content 类型修正 | 新环境 / 迁移后各跑一次 | 幂等 |
| `check_db.py` | SQLAlchemy 连通性检查（方言无关，打印 `DB_OK`/`DB_FAIL`） | 部署排障 | — |
| `macro_baseline.py` | 加载宏观基线 YAML/JSON（供 `prompts_new` System Prompt） | 被调用，不直接运行 | — |

> 注：根目录曾有的 `export_recent_news_csv.py`、`run_recent_pipeline_and_export.py` 重复副本已于 2026-09-07 删除，统一以 `scripts/` 版本为准。

---

## 2. `scripts/` 目录（批处理、迁移与调试）

生产部署不含此目录（`scripts/README.md` 已注明不参与部署、不入库跟踪）。

### 2.1 数据迁移与导入

| 脚本 | 用途 |
|---|---|
| `migrate_mysql_to_postgres.py` | 三张核心表从 MySQL 全量迁到 PostgreSQL（默认清空目标表，`--no-truncate` 追加），迁移后重置 PG 序列；打印连接串已脱敏 |
| `import_csv_to_postgres.py` | 把导出的 CSV 导入 PostgreSQL（CSV 救援通道） |
| `backfill_12h_windows.py` | 按 12 小时窗口回补历史数据（复用 `news_fetcher` 内部函数，采集+筛选+分析） |
| `normalize_content_hash.py` | content_hash 历史数据归一（`--dry-run`/`--update`/`--dedupe`）；S2 统一 blake2b 后的数据侧配套 |

### 2.2 导出与评估

| 脚本 | 用途 |
|---|---|
| `export_recent_news_csv.py` | 导出最近 N 分钟 `raw_news` / `selected_news` 为 CSV（文件名含分钟数，如 `*_120m.csv`） |
| `export_latest_selected_20.py` | 导出最新 20 条 `selected_news` 到 `news/selected_news_latest_20.csv` |
| `run_filter_and_export_quick.py` | 快速 `filter_news(limit=8)` + 导出近 30 分钟 CSV |
| `analyze_selected_csv_to_md.py` | 读筛选 CSV，逐条调 `call_doubao_analyze_api` 生成 Markdown（便于人工阅读） |
| `compare_prompts_on_selected_csv.py` | 同批 CSV 上 A/B 对比旧/新分析提示词（脚本内编辑 `NEW_PROMPT_TEMPLATE`） |

### 2.3 Schema 排查

| 脚本 | 用途 |
|---|---|
| `check_raw_relevance.py` | 直连检查 `raw_news.relevance` 列是否存在 |
| `check_relevance_column.py` | 同类 schema 检查辅助 |

### 2.4 调试与联调

| 脚本 | 用途 |
|---|---|
| `debug_doubao.py` | 打印豆包响应 `output` 结构 |
| `debug_filter_response.py` | 样例跑筛选提示词，打印原始文本与解析结果 |
| `debug_news_api.py` | 直调 `pro.news` 查看列名与样例 |
| `test_api.py` | 串联验证 Tushare + 豆包配置 |
| `test_filter_once.py` | 小批量（`limit=2`）验证筛选链路 |
| `test_tushare_news.py` | 多时间窗验证 `pro.news` 权限 |
| `fix_crlf.py` | 一次性工具：文件换行 CRLF→LF |

### 2.5 部署配套

| 文件 | 用途 |
|---|---|
| `nginx-domain-ssl.conf` | 域名 + SSL 的 Nginx 配置模板 |
| `setup_nginx_for_display.sh` | 服务器上配置 Nginx 展示站 |
| `setup_web_display_on_server.sh` | 一键部署静态展示站 |
| `sync_loop.sh` | 5 秒间隔常驻循环执行 `sync_news_to_display.py --no-change`（daemon 模式下可停用） |

---

## 3. `tests/` 目录

| 文件 | 用途 |
|---|---|
| `tests/test_news_fetcher.py` | 单元测试（mock）：`compute_content_hash`、`parse_news_datetime`、来源配置、采集部分逻辑 |
| `tests/run_prompt_compare.py` | 提示词对比的运行包装 |
| `tests/prompts_test.csv` | 提示词对比样例数据 |

运行：

```bash
pytest tests/ -q
```

---

## 4. 脚本间依赖关系

```text
run_pipeline_90s_loop.sh ──> run_pipeline_90s.py ─┐
阿里云定时任务 ───────────> run_task.py ──────────┤
pipeline_daemon.py（常驻，二选一）────────────────┤
                                                   ├─> news_fetcher / news_filter / news_analyzer
手动 ─────────────────────> run_pipeline_manual.py ┘        │
                                                            ▼
                                              doubao_client / models / config

sync_loop.sh / pipeline_daemon ──> sync_news_to_display.run_sync() ──> web_display/data/feed.json ──> 静态站

backfill_12h_windows.py ──> （复用 news_fetcher 内部函数）──> 三表回补
migrate_mysql_to_postgres.py ──> config.db（双 URL）──> PG 三表
```

---

## 5. 新增脚本的登记要求

新增任何脚本时应补充：

1. 文件路径与一句话职责
2. 运行方式（命令行示例）
3. 依赖的模块（尤其是是否依赖 `doubao_client` / `models`）
4. 是否参与生产部署
5. 是否需要进入 `docs/project_context_index.md` 的修改落点表
