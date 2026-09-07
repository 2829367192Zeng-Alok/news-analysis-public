# 金融新闻分析系统 项目理解总索引

> 版本：v1.1
> 更新时间：2026-09-07（v1.1：代码修复波 W1–W3 完成，技术债清单 §5 已同步 ✅/⚠️/未修复状态；实施清单见 `docs/fix_plan_2026-09-07.md`）
> 用途：新对话、新成员或后续开发开始前的项目总入口。本文是文档体系的唯一索引；其他专项文档由它串联。
>
> 阅读本文后，应知道项目做什么、核心数据如何流转、代码和文档在哪里，以及不同任务需要继续阅读哪些材料。

---

## 1. 新对话推荐投放方式

### 最小必要材料

如果新对话只能投入少量文件，优先提供：

1. `docs/project_context_index.md`（本文）
2. `README.md`
3. `docs/pipeline_reference.md`
4. `docs/project_database_schema_reference.md`
5. `docs/llm_architecture_reference.md`

### 按任务追加的材料

| 任务类型 | 继续阅读 |
|---|---|
| **代码质量 / 修复 / 重构** | `docs/code_review_report_2026-09-07.md`（43 项分级问题）+ `docs/fix_plan_2026-09-07.md`（修复方案 W0–W4 分波次实施清单） |
| Web / 前端 / 展示 | `docs/web_display_reference.md` + `templates/` + `static/` + `web_display/` |
| 部署 / 服务器 / 定时任务 | `docs/deployment_reference.md` + `docs/deployment/` 专题 + `run_pipeline_90s_loop.sh` |
| 飞书推送 / 告警 | `docs/feishu_notification_reference.md` + `feishu_webhook/` |
| 脚本梳理 / 数据迁移 / 回补 | `docs/project_script_architecture.md` + `scripts/` |
| 提示词 / 模型调整 | `docs/llm_architecture_reference.md` + `prompts.py` + `prompts_new.py` + `macro_baseline.py` |
| 数据库 / 字段 / 迁移 | `docs/project_database_schema_reference.md` + `models.py` + `init_db.py` |
| 历史背景追溯 | `docs/金融新闻分析系统_d1f1a06f.plan.md`（注意：是早期计划，非当前实现） |

### 不建议作为首批材料

- `docs/金融新闻分析系统_d1f1a06f.plan.md`：早期实施计划，架构描述与当前代码有出入（如定时频率、脚本形态），仅作历史参考。
- 根目录 `analysis_report.txt`、`pipeline_report.txt`：运行产物，非文档。
- `news/` 下 CSV：导出样本。

---

## 2. 项目一句话说明

金融新闻分析系统是一个部署在阿里云 ECS 上的**黄金市场新闻自动化分析系统**：

```text
Tushare 采集（华尔街见闻/新浪财经）
  → content_hash 去重入库 raw_news
  → 豆包 AI 筛选（相关性判断）→ selected_news
  → 豆包 AI 详细分析（五维传导 + 短中长期）→ news_analysis_detail
  → Flask API 动态站 / Nginx 静态展示站 / 飞书群推送
```

- **采集–筛选–分析** 由定时任务高频驱动（90 秒窗口为主）；
- 全程以 `content_hash` 关联三张表实现幂等；
- 飞书双链路：业务推送（分析结果）+ 运维告警（停摆/API 异常）。

---

## 3. 顶层目录地图

| 目录/文件 | 作用 |
|---|---|
| `config.py` | 统一配置加载（.env → 用户目录 → 环境变量优先级见文件），DB/Tushare/豆包/飞书 dataclass |
| `models.py` | ORM 三张核心表 + engine + scoped_session |
| `utils.py` | 北京时间 naive、MD5 content_hash、新闻时间解析 |
| `news_sources.py` | 来源配置（wallstreetcn/sina）+ 非 Tushare 源扩展协议 |
| `news_fetcher.py` | Tushare pro.news 采集、多层去重、写 raw_news |
| `news_filter.py` | 豆包筛选、写 selected_news、回写 raw_news.relevance |
| `news_analyzer.py` | 豆包详细分析、写 news_analysis_detail |
| `doubao_client.py` | Ark Responses API 封装（OpenAI SDK 版）、异常分类、重试、JSON 解析 |
| `prompts.py` | 当前生效的筛选/分析提示词 |
| `prompts_new.py` | v2 候选提示词（含宏观基线 System Prompt） |
| `macro_baseline.py` | 宏观基线 YAML/JSON 加载 |
| `run_task.py` | 一轮全链路入口（通用） |
| `run_pipeline_90s.py` | 90 秒窗口流水线（生产主用） |
| `run_pipeline_90s_loop.sh` | 90 秒触发外壳（flock + timeout + 日志） |
| `run_pipeline_manual.py` | 可配置窗口手动流水线，写 pipeline_report.txt |
| `run_pipeline_once.py` | ⚠️ 历史脚本，存在损坏片段，勿直接运行 |
| `run_analysis_latest_20.py` | 最新 20 条补分析/抽查 |
| `sync_news_to_display.py` | 导出 feed.json 供静态站 |
| `app.py` | Flask 动态站（API + 页面） |
| `templates/` + `static/` | Flask 站前端（深色主题） |
| `web_display/` | 静态展示站（Tabler，读 feed.json） |
| `feishu_webhook/` | 推送 + 告警 + Webhook 客户端 |
| `pipeline_notify_format.py` | 推送文案 |
| `scripts/` | 迁移/导出/评估/调试/部署脚本（不参与生产） |
| `tests/` | fetcher 单测 + 提示词对比工具 |
| `news/` | 导出 CSV 样本 |
| `words/` | PG→MySQL 回滚说明 |
| `config/` | `macro_baseline.example.yaml` |

---

## 4. 核心流程与阅读路径

### 4.1 主链路（必读）

```text
Tushare → raw_news → selected_news → news_analysis_detail → 展示/推送
```

主要代码：

- `news_fetcher.py` / `news_filter.py` / `news_analyzer.py`
- `run_task.py` / `run_pipeline_90s.py`

必读文档：

- `docs/pipeline_reference.md`（阶段职责、幂等、容错、排查）

### 4.2 采集

- `news_sources.py`：来源只读 `TUSHARE_SOURCES`；扩展非 Tushare 源走 `BaseNewsFetcher` 协议（预留，未使用）
- `news_fetcher.py`：北京时间窗口；同源去重→跨源去重→库内 hash 比对→时间窗过滤
- 注意：`utils.compute_content_hash` 是 **MD5**（title+"::"+content）；`news_fetcher.compute_content_hash` 是 **blake2b**——**两套实现并存且不一致**，涉及判重一致性时必须先阅读本文档此条

### 4.3 筛选与分析

- 筛选：`relevance IS NULL` 领任务，回写 relevance，相关才写 selected_news；同错误连续 2 次熔断
- 分析：反查 detail 缺失 hash，每条单独 commit；分析阶段 max_retries=0
- 提示词 A/B：`scripts/compare_prompts_on_selected_csv.py`、`tests/run_prompt_compare.py`

### 4.4 数据库

- 三张表 + content_hash 索引；`Reference` 列名为历史遗留大写，勿改
- `init_db.py` 幂等补列；MySQL content → MEDIUMTEXT
- 阅读：`docs/project_database_schema_reference.md`

### 4.5 LLM

- 一切豆包调用走 `doubao_client.py`；429 指数退避（4–64s），404/403 直接抛
- v2 基线机制：`macro_baseline.py` + `prompts_new.SYSTEM_PROMPT_TEMPLATE`（当前生产仍用 `prompts.py`）
- 阅读：`docs/llm_architecture_reference.md`

### 4.6 Web 展示（双形态）

| 形态 | 入口 | 数据 |
|---|---|---|
| Flask 动态站 | `app.py`，gunicorn :8000 | 直连库，`/api/news`、`/api/news/<id>`、`/api/stats`，before/after 游标翻页 |
| 静态站 | `web_display/index.html`，Nginx 托管 | `sync_news_to_display.py --no-change` 导出 feed.json |

- 阅读：`docs/web_display_reference.md`
- 部署：`scripts/setup_web_display_on_server.sh`、`scripts/nginx-domain-ssl.conf`、`docs/deployment/`

### 4.7 飞书双链路

- 推送：`feishu_webhook/service.py` + `pipeline_notify_format.py`（分析完成后逐条推群）
- 告警：`feishu_webhook/alert_service.py`（raw/analyze 停摆 + API 异常 + 恢复通知，抑制状态落 `.alert_state.json`）
- 阅读：`docs/feishu_notification_reference.md`

### 4.8 调度与部署

- 生产触发：阿里云每 90 秒 → `run_pipeline_90s_loop.sh`（flock 防并发，timeout 85s，日志 `logs/pipeline_1min.log`）
- ECS 连 RDS 内网地址；Web 用 gunicorn；静态站常驻 sync_loop
- 阅读：`docs/deployment_reference.md`（汇总）；逐步操作记录在 `docs/deployment/`

### 4.9 脚本与迁移

- 迁移：`scripts/migrate_mysql_to_postgres.py`（默认清空目标表）
- 回补：`scripts/backfill_12h_windows.py`（12 小时窗口）
- CSV 救援：`scripts/import_csv_to_postgres.py`
- 回滚：`words/postgresql_to_mysql_rollback.md`
- 阅读：`docs/project_script_architecture.md`（全部脚本权威登记）

---

## 5. 已知技术债与不一致（修改前必读）

> 修复状态（2026-09-07 修复波 W1–W3 完成，见 `docs/fix_plan_2026-09-07.md`）：下面前 10 项已修复（✅）。**仍有 3 项未修复**：#11（`Reference` 命名，暂保留）、#13（v2 提示词未接入生产）、#14（relevance 语义复用）。完整 43 项清单与修复映射见 **`docs/code_review_report_2026-09-07.md`**。

1. ✅ **C1（S2）双套 content_hash 已统一为 blake2b**：`utils.py` 为唯一实现，`news_fetcher.py` 改为导入；旧 MD5 保留为 `compute_content_hash_legacy_md5` 仅供迁移对比。历史库内 MD5 行需执行 `scripts/normalize_content_hash.py --update`（先 `--dry-run`）归一（**尚未在生产库执行**）。
2. ✅ **C2（S1）`run_pipeline_once.py` 已删除**（2026-09-07），功能由 `run_pipeline_manual.py` 覆盖。
3. ✅ **C3（S3）`check_db.py` 已重写**为方言无关的 SQLAlchemy `SELECT 1` 连通性检查，MySQL/PostgreSQL 通用。
4. ✅ **C4（S4）测试套件已修复**：断言改为 `tushare_src == "sina"`（`source_id` 仍为 `"新浪财经"`），pytest 现 13 passed。
5. ✅ **C5（S5）Flask 站 XSS 已修复**：`static/js/main.js` 新增 `escapeHtml`，所有模型输出字段入库前转义。
6. ✅ **C6（S6）90s 流水线已限制分析范围**：`analyze_news` 新增 `only_content_hashes` 参数；loop.sh `TIMEOUT_SEC` 由 85 提到 240，与单条分析超时对齐；并发由 flock 兜底。
7. ✅ **C7（L1）时间口径已统一**：`run_analysis_latest_20.py` 改用 `now_beijing_naive()`。
8. ✅ **C8（L3）冗余索引已清理**：`models.py` 移除列级 `index=True`；`init_db.py` 幂等 DROP 历史遗留 `ix_*` 索引。
9. ⚠️ **C9（L4）`content_hash` 唯一约束未加**（破坏性 DB 变更，需先跑 `normalize_content_hash.py --dedupe` 清理历史重复，待用户批准）；并发侧已加固：`run_task.py` 加 flock、90s 循环本有 flock。
10. ✅ **C10（R5）依赖已补齐**：`requirements.txt` 加 `gunicorn`；新增 `requirements-dev.txt`（pytest/ruff）；`.alert_state.json` 已入 `.gitignore`。
11. **`Reference` 列名**：历史遗留首字母大写，模型输出、ORM、DB 三方一致，勿单方面改名（暂不迁移，保持 TODO）。
12. ✅ **根目录与 scripts/ 重复脚本已删除**：仅保留 `scripts/` 版本（`export_recent_news_csv.py` / `run_recent_pipeline_and_export.py`）。
13. **`prompts_new.py`/`macro_baseline.py` 未接入生产链路**：当前 `news_analyzer.py` 仍用 `prompts.py`；v2 机制（基线注入 + confidence/uncertain 字段）已就绪但未切换，且 v2 新增字段在表中无对应列。切换属 W4.1 可选工作流，需另行批准。
14. **`raw_news.relevance` 语义复用**：既是“筛选器是否处理过”的状态位，又是“是否相关”的业务值（NULL=未处理）。设计约束，暂不改。

---

## 6. 修改落点速查

| 改什么 | 在哪改 |
|---|---|
| 新闻来源 | `news_sources.py`（`TUSHARE_SOURCES`） |
| 筛选/分析提示词 | `prompts.py`（生效版）/ `prompts_new.py`（v2） |
| 模型/API Key | `.env`（`DOUBAO_*`、`TUSHARE_TOKEN`） |
| 分析字段/表结构 | `models.py` → `init_db.py` → `news_analyzer.py` → `app.py` → `sync_news_to_display.py` → 前端两处 |
| 页面样式/交互 | Flask 站：`static/css/style.css`、`static/js/main.js`；静态站：`web_display/index.html` |
| 推送文案 | `pipeline_notify_format.py` |
| 告警阈值 | `.env`（`ALERT_*`） |
| 采集窗口 | python 读 `FETCH_WINDOW_MINUTES`（默认 1.5=90s；loop.sh 同步导出） |
| 补偿筛选 | `.env`（`CATCHUP_STALE_MINUTES`=30、`CATCHUP_FILTER_LIMIT`=15） |
| 展示域名/链接 | `.env`（`FEISHU_PUSH_WEB_BASE_URL`） |
| Nginx/SSL | `scripts/nginx-domain-ssl.conf` |

---

## 7. 环境与运行速查

```bash
# 环境准备
pip install -r requirements.txt
cp .env.example .env                 # 填 DB/TUSHARE_TOKEN/DOUBAO_API_KEY

# 初始化（幂等）
python init_db.py
python check_db.py                   # 期望 DB_OK

# 一轮流水线（手动）
python run_pipeline_manual.py                     # 60 分钟窗口
FETCH_WINDOW_MINUTES=10 python run_pipeline_manual.py
python run_task.py                                # 不限本批 hash 的全量轮

# 生产形态
bash run_pipeline_90s_loop.sh                     # 配阿里云 90s 定时
gunicorn -w 2 -b 0.0.0.0:8000 "app:app"
bash scripts/sync_loop.sh                         # 静态站常驻同步

# 测试
pytest tests/ -q
```

---

## 8. 文档分层

### L0：入口

- `docs/project_context_index.md`（本文）
- `README.md`

### L1：稳定参考（2026-09-07 全部新写/更新，与当前代码对齐）

- `docs/pipeline_reference.md`
- `docs/project_database_schema_reference.md`
- `docs/llm_architecture_reference.md`
- `docs/web_display_reference.md`
- `docs/deployment_reference.md`
- `docs/project_script_architecture.md`
- `docs/feishu_notification_reference.md`

### L2：历史操作记录（内容可能与现状有偏差，部署排障时仅作参考）

- `docs/deployment/部署Web展示系统.md`
- `docs/deployment/上传并部署到ECS.md`
- `docs/deployment/上传流水线脚本到ECS.md`
- `docs/deployment/域名部署协作步骤.md`
- `docs/deployment/Nginx单行部署说明.md`
- `docs/deployment/连接服务器与操作数据库.md`
- `docs/deployment/服务器与配置检索结果.md`
- `docs/代码架构说明.md`（已被 L1 系列取代，保留作迁移痕迹）

### L3：计划与产物

- `docs/code_review_report_2026-09-07.md`（代码全景审查报告：43 项分级问题 + 修复优先级；修复后需回填“已修复”小节）
- `docs/fix_plan_2026-09-07.md`（修复实施方案：W0–W4 波次、验证与回滚清单）
- `docs/金融新闻分析系统_d1f1a06f.plan.md`（早期实施计划）
- `analysis_report.txt` / `pipeline_report.txt` / `news/*.csv`

---

## 9. 新对话启动提示词

> 这是 financial-news-analysis 项目。请先阅读 `docs/project_context_index.md`，再按当前任务阅读对应专项文档。不要把历史计划、`run_pipeline_once.py` 或部署专题旧文档当作当前实现；以当前代码、当前配置和 L1 稳定参考文档为准。注意第 5 节列出的已知技术债（尤其双 content_hash 实现问题）。完成修改后，同步更新受影响的专项文档与本索引。

---

## 10. 后续维护要求

发生以下变化时必须更新本文档与对应专项文档：

- 新增/删除模块、脚本、入口
- 三张表结构变化或新增表
- 提示词结构或模型切换
- 新增页面/路由/展示形态
- 飞书链路或告警语义变化
- 部署拓扑、定时任务、环境变量变化

每次更新至少补充：新文件路径、作用、所属层级、新对话阅读方式、是否替代旧文档、迁移兼容注意。

## 11. 判断优先级

文档与代码不一致时按以下顺序取信：

1. 当前代码
2. 当前 `.env` / 配置
3. `init_db.py` 与迁移脚本
4. L1 稳定参考文档
5. L2 历史记录与早期计划

发现不一致不要默默选择一方：先在响应中说明，再改代码或改文档，最后回填本索引。
