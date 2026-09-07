# 金融新闻分析系统数据库结构参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 适用代码：`models.py`、`init_db.py`、`scripts/migrate_mysql_to_postgres.py`

本文记录项目当前的数据库模型、字段语义、关联方式、初始化策略和改库注意事项。后续凡涉及字段新增、表结构变化、去重规则调整或迁移脚本更新，都应先更新本文。

---

## 1. 数据库角色

本项目使用数据库作为三类能力的共同落点：

1. **原始采集存储**：保存从 Tushare 拉取的新闻原文。
2. **中间筛选与分析结果**：保存 AI 相关性筛选与结构化分析结果。
3. **运行与同步辅助**：通过脚本和 Web 直接读取分析结果做展示或导出。

核心设计原则：

- 以 `content_hash` 作为跨表关联与去重主键思路；
- 所有写入都应幂等，避免重复采集或重复分析；
- 统一按北京时间的 naive datetime 存储；
- `raw_news.relevance` 允许为 `NULL`，表示尚未筛选；
- `news_analysis_detail` 字段命名保留了部分历史遗留首字母大写列名（如 `Reference`），不要擅自改列名。

---

## 2. ORM 与连接入口

### 2.1 关键文件

- `models.py`：定义 ORM、`engine`、`SessionLocal`、`get_db_session()`
- `config.py`：拼接数据库连接串，支持 MySQL / PostgreSQL 双栈
- `init_db.py`：初始化表结构并补列
- `scripts/migrate_mysql_to_postgres.py`：MySQL → PostgreSQL 全量迁移

### 2.2 连接行为

- 默认通过 `settings.db.sqlalchemy_url` 建立连接
- `DB_DIALECT=mysql|postgresql`
- 若显式设置 `DATABASE_URL`，优先级最高
- MySQL 下会尝试设置会话时区为 `+08:00`

---

## 3. 核心业务表

### 3.1 `raw_news`

原始新闻表，保存采集阶段的入库结果。

主要字段：

- `id`：自增主键
- `title`：标题
- `content`：正文
- `news_datetime`：新闻发布时间
- `source`：来源标识，如 `华尔街见闻`、`新浪财经`
- `create_time`：入库时间
- `content_hash`：标题 + 正文的内容哈希
- `relevance`：筛选阶段写回的相关性标记，`NULL/True/False`

设计说明：

- `content_hash` 用于同源、跨源和库内去重；
- `relevance` 是筛选阶段的状态字段，不是分析阶段结果；
- 采集成功并不意味着后续一定进入 `selected_news`。

### 3.2 `selected_news`

筛选后新闻表，保存 AI 判定为相关的新闻。

主要字段：

- `id`
- `title`
- `content`
- `news_datetime`
- `source`
- `create_time`
- `relevance`
- `direction`：短期方向，`1 / 0 / -1`
- `impact`：短期影响强度
- `content_hash`

设计说明：

- 只保存筛选结果为相关的新闻；
- 通过 `content_hash` 与 `raw_news` 关联；
- `selected_news` 既是筛选结果，也是分析阶段的输入池。

### 3.3 `news_analysis_detail`

详细分析表，保存 AI 结构化分析结果，是 Web 展示和飞书推送的主要数据源。

主要字段：

- 基础字段：`id`、`title`、`content`、`news_datetime`、`source`、`create_time`
- 筛选字段：`relevance`、`direction`、`impact`
- 五维分析字段：
  - `interest_direction`、`interest_impact`
  - `dollar_direction`、`dollar_impact`
  - `warrisk_direction`、`warrisk_impact`
  - `liquidity_direction`、`liquidity_impact`
  - `emotion_direction`、`emotion_impact`
- 结构化字段：
  - `keyword`（JSON）
  - `Reference`（JSON，历史遗留列名）
- 文本分析字段：
  - `interest`
  - `dollar`
  - `warrisk`
  - `liquidity`
  - `emotion`
  - `shorttime`
  - `midtime`
  - `longtime`
  - `insight`
  - `conclusion`
- `content_hash`

设计说明：

- 该表是一条新闻的最终分析落点；
- Web API、静态页导出、飞书推送都优先读取这张表；
- `keyword` 和 `Reference` 以 JSON 存储数组；
- 分析提示词输出字段必须与这里保持一致。

---

## 4. 字段语义约定

### 4.1 方向值

方向字段统一采用：

- `1`：利多黄金 / 正向
- `-1`：利空黄金 / 负向
- `0`：中性或无法判断

### 4.2 影响值

影响强度字段统一采用整数等级，通常是：

- `1`：较弱
- `2`：偏弱
- `3`：中等
- `4`：较强
- `5`：极强

### 4.3 时间字段

- `news_datetime`：新闻原始发布时间
- `create_time`：系统写入时间

两者不要混用。展示和统计应明确区分“新闻发生时间”与“入库时间”。

---

## 5. 索引与去重

当前模型在每个业务表上只声明一个 `content_hash` 索引：

- `idx_raw_content_hash`
- `idx_selected_content_hash`
- `idx_detail_content_hash`

（2026-09-07 起移除列级 `index=True` 产生的重复 `ix_*` 索引；`init_db.py` 会幂等清理历史遗留的 `ix_*`。）

用途：

- 快速判断某条新闻是否已经采集/筛选/分析；
- 支持脚本只处理增量；
- 避免高频定时任务重复写入。

注意：当前逻辑依赖“索引 + 代码层查询”，并不等同于完整数据库唯一约束。若未来要改成强唯一约束，应先执行 `scripts/normalize_content_hash.py --dedupe` 清理历史重复（破坏性操作，需批准）再在 `init_db.py` 增加唯一索引。

---

## 6. 初始化与迁移

### 6.1 `init_db.py`

执行内容：

1. `Base.metadata.create_all(engine)` 创建缺失表；
2. 逐表补 `content_hash` 与相关索引；
3. 为 `raw_news` 补 `relevance`；
4. 为 `news_analysis_detail` 补全分析字段；
5. 修正 `content` 字段类型（MySQL 下为 `MEDIUMTEXT`，PostgreSQL 下为 `TEXT`）。

### 6.2 `scripts/migrate_mysql_to_postgres.py`

作用：

- 将 `raw_news`、`selected_news`、`news_analysis_detail` 三张核心表从 MySQL 全量迁移到 PostgreSQL；
- 支持是否清空目标表的迁移策略；
- 迁移后会处理 PostgreSQL 序列值。

---

## 7. 读取路径建议

### 7.1 新对话如果要理解数据结构

优先看：

1. 本文
2. `models.py`
3. `init_db.py`
4. `scripts/migrate_mysql_to_postgres.py`
5. `docs/pipeline_reference.md`

### 7.2 新增字段或改表时

必须同步检查：

- `news_filter.py`
- `news_analyzer.py`
- `app.py`
- `sync_news_to_display.py`
- `feishu_webhook/service.py`
- `pipeline_notify_format.py`
- `static/js/main.js`
- `docs/project_context_index.md`

---

## 8. 当前数据库关系图

```text
raw_news
  └─ content_hash ──┐
                    │
selected_news       │
  └─ content_hash ───┼──> news_analysis_detail
                    │
                    └──> Web / 静态页 / 飞书推送
```

---

## 9. 变更注意事项

1. 不要随意改 `Reference` 这种遗留列名。
2. 不要在业务代码里绕过 `content_hash` 直接判断重复。
3. 不要把 `create_time` 当作新闻发布时间。
4. 若改用新的去重规则，必须同步修改采集、筛选、分析和迁移文档。
5. 若引入新表，需更新本文和项目总索引。
