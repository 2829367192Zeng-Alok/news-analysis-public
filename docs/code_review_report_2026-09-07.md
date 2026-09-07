# 金融新闻分析系统 代码问题全景审查报告

> 版本：v1.0  
> 审查日期：2026-09-07  
> 审查范围：项目全部 `.py`（23 个根目录 + `scripts/` 17 个 + `tests/` 2 个 + `feishu_webhook/` 4 个）、前端（`templates/`、`static/`、`web_display/`）、shell 部署脚本（4 个）、Nginx 配置、`.gitignore`/`.gitattributes`、`requirements.txt`、`.env.example`、`config/`。
> 验证手段：逐文件精读 + `py_compile` + `pytest` 实跑 + ORM 元数据检查 + 属性存在性检查。标注 **[已验证]** 的问题均经工具复现，非静态推测。

---

## 0. 问题总览

| 等级 | 数量 | 含义 |
|---|---:|---|
| S（严重） | 7 | 错误数据、流程不可用、安全风险 |
| L（逻辑/数据） | 10 | 计算口径、幂等、统计类缺陷 |
| R（健壮性/工程） | 13 | 并发、原子性、容错、依赖 |
| O（运维/部署） | 6 | 部署脚本、调度、配置 |
| Q（质量/整洁） | 7 | 重复、命名、测试覆盖、整洁度 |

---

## 1. S 级：严重问题

### S1. `run_pipeline_once.py` 整个文件语法损坏，不可运行 **[已验证]**

`py_compile` 报错：

```text
File "run_pipeline_once.py", line 216
    """??????? token ????"""
SyntaxError: unterminated triple-quoted string literal (detected at line 372)
```

具体症状：

- 全部中文注释/字符串变成 `?`（典型的编码损坏，非代码问题而是文件被错误编码保存）；
- 多处字符串缺右引号（如 `report_lines.append("????????????????)`）；
- 整个模块体重复出现两次（两份 `main()`、两份 `if __name__ == "__main__"`）。

影响：该文件无法 import 也无法执行；文档 `docs/代码架构说明.md` 已提示"存在重复/损坏片段"，但文件仍留在根目录，对后续维护者构成误导。**处置建议：直接删除**（`run_pipeline_manual.py` 完全覆盖其功能且更完善）。

### S2. 两套 `compute_content_hash` 实现并存（MD5 vs blake2b），回补数据判重必然失配

- `utils.py`：MD5（32 hex）：

```python
def compute_content_hash(title: str, content: str) -> str:
    """基于标题和正文计算内容哈希，用于跨来源去重。"""
    m = hashlib.md5()
    key = (title or "") + "::" + (content or "")
    m.update(key.encode("utf-8"))
    return m.hexdigest()
```

- `news_fetcher.py`：blake2b（64 hex）：

```python
def compute_content_hash(title: str, content: str) -> str:
    import hashlib
    raw = f"{title}\n{content}".encode("utf-8", errors="replace")
    return hashlib.blake2b(raw, digest_size=32).hexdigest()
```

影响链：生产采集写入的 `content_hash` 全部是 blake2b 值；而 `scripts/backfill_12h_windows.py` 从 `utils` 导入 MD5 版本计算哈希并入库：

```python
from utils import compute_content_hash, now_beijing_naive
...
hashes = [compute_content_hash(t[0], t[1]) for t in all_normalized]
```

后果：回补写入的行使用 MD5 哈希；同一新闻随后被在线流水线（blake2b）拉取时哈希不匹配 → **同一新闻在 `raw_news` 中出现两条不同 hash 的重复记录**，并各自进入筛选/分析，产生重复分析、重复推送、token 浪费。混用前任何代码都不允许同时引用两个实现。

### S3. `check_db.py` 引用不存在的配置属性，永远输出 `DB_FAIL` **[已验证]**

```python
conn = pymysql.connect(
    host=c.host, port=c.port, user=c.user, password=c.password,
    database=c.name, connect_timeout=10
)
```

`DatabaseConfig` 的实际字段是 `mysql_host / mysql_port / mysql_user / mysql_password / mysql_name`（已用 `hasattr` 验证 `c.host` 不存在）。该脚本捕获所有异常后打印 `DB_FAIL`，因此**部署检查清单中"期望 DB_OK"永远无法达成**，还可能误导排障方向（让人以为数据库连不通，实际是脚本自身崩了）。另外该脚本只支持 MySQL，PG 环境下同样失效。

### S4. 单元测试套件是红的：`test_sources_config` 断言错误 **[已验证]**

`pytest tests/ -q` 实跑结果：`1 failed, 4 passed`。

```python
filtered = get_sources_by_ids([SOURCE_ID_SINA])
assert len(filtered) == 1
assert filtered[0].tushare_src == "新浪财经"   # 实际值是 "sina"
```

`SOURCE_ID_SINA = "新浪财经"` 是 `source_id`，`tushare_src` 是 `"sina"`。断言把两个字段混为一谈。附带问题：

- 测试里 `datetime.utcnow()` 触发 DeprecationWarning（Python 3.12）；
- 断言 `compute_content_hash` 长度 32 只覆盖了 MD5 实现，blake2b 实现（生产实际使用）零测试覆盖。

### S5. Flask 站存在存储型 XSS：模型输出未转义直接进 `innerHTML`

`static/js/main.js` 第 117–145 行把 `shorttime / midtime / longtime / interest / dollar / warrisk / liquidity / emotion` 字段原样拼进字符串后 `p.innerHTML = b.content;`：

```javascript
blocks.push({
  title: "时间维度结论",
  content: [
    data.shorttime ? `短期：${data.shorttime}` : null,
    // ...
  ].filter(Boolean).join("<br>") || "无",
});
...
p.innerHTML = b.content;
```

攻击链：外部新闻正文（不可信输入）→ LLM 分析输出 → `news_analysis_detail` → `/api/news/<id>` → `innerHTML`。只要诱导一条新闻让模型输出包含 `<img src=x onerror=...>` 之类的内容，就能在展示页执行脚本。对比之下，`web_display/index.html` 的静态站对每个字段都做了 `escapeHtml()`——**同一数据两个前端，一个安全一个不安全**。处置：`main.js` 增加与静态站一致的 `escapeHtml`，仅在自行拼接的 `<br>` 处保留标签。

### S6. 90 秒生产流水线的 analyze 环节与 85 秒 shell 超时互相冲突

三个事实叠加：

1. `run_pipeline_90s_loop.sh` 用 `timeout 85` 包裹整个 python 进程；
2. `news_analyzer.call_doubao_analyze_api` 单次调用 `timeout=240`、`max_retries=0`；
3. `run_pipeline_90s.py` 的步骤 3 调用 `analyze_news(limit=50)` 时**没有** `only_content_hashes` 限制（该参数在 analyze 中根本不存在），会捞取所有缺 detail 的 `selected_news`（含历史积压）。

后果：一旦积压超过 ~2 条慢分析，本轮 85 秒被 SIGTERM，正在途中的模型调用响应丢失（token 已消耗但结果未入库），下一轮重新排队重跑同一批 → **慢场景下重复计费 + 吞吐量被锁死在每轮 1–2 条**。短期止血：analyze 也按本批 hash 限量；长期：把 analyze 单条超时降到 < 60s 或把 90s 触发改成常驻轮询。

### S7. `app.py` 直接运行时开启 debug 模式

```python
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
```

`python app.py`（README 交替推荐的启动方式之一）会启用 Werkzeug 调试器并监听 `0.0.0.0`——一旦在生产 ECS 上用这种方式起服务，调试器 PIN 被绕过即等价 RCE。应改为从环境变量读取 debug 开关，默认 False。

---

## 2. L 级：数据与逻辑问题

### L1. `run_analysis_latest_20.py` 的 `create_time` 用 UTC，与主链路北京时间口径冲突

该脚本两处 `create_time=datetime.now(timezone.utc).replace(tzinfo=None)`；主链路统一 `now_beijing_naive()`。后果：这批记录的 `create_time` 比真实时间**早 8 小时**；`PipelineHealthChecker` 用 `MAX(create_time)` 判断"分析层停摆"，混合口径下会产生误报/漏报窗口。

### L2. 90 秒循环对"筛选失败窗口"没有任何补偿机制

`run_pipeline_90s.py` 的筛选只处理本批新采集 hash（`only_content_hashes=set(new_raw_hashes)`）。若某窗口筛选因 429/不可用失败，该批 `raw_news` 永远停留在 `relevance IS NULL`；下一个窗口只会拉新数据。只有手动跑 `run_task.py`（无 hash 过滤）才会补筛。生产形态下**故障窗口的数据会静默滞留**，与告警（只监控"是否完全没有新数据"）不匹配——部分失败不会触发任何告警。

### L3. 三张表 `content_hash` 上存在双份冗余索引 **[已验证]**

ORM 元数据检查输出：

```text
raw_news              -> ['idx_raw_content_hash', 'ix_raw_news_content_hash']
selected_news         -> ['idx_selected_content_hash', 'ix_selected_news_content_hash']
news_analysis_detail  -> ['idx_detail_content_hash', 'ix_news_analysis_detail_content_hash']
```

`Column(index=True)` 与 `__table_args__` 里的显式 `Index` 同时声明。写入放大一倍，无任何收益。`init_db.py` 还会主动再建一遍 `idx_*`，把冗余固化到库里。

### L4. `content_hash` 无数据库唯一约束 + 采集"查后插"非原子

去重靠"先 SELECT 已有 hash，再 INSERT"，且只靠应用层去重。`run_pipeline_90s_loop.sh` 有 flock，但 `run_task.py`、手动脚本、`backfill` 都没有——并行触发时同一新闻可重复入库。至少应给 `raw_news.content_hash` 加唯一索引（配合幂等 INSERT ON CONFLICT/IGNORE）。

### L5. 两个评估脚本的 token 统计键名错误，统计恒为 0

`doubao_client._extract_usage_from_response` 返回的键是 `input_tokens / output_tokens / total_tokens`；而 `scripts/compare_prompts_on_selected_csv.py` 与 `scripts/analyze_selected_csv_to_md.py` 求和用的是：

```python
p = sum(int(u.get("prompt_tokens", 0)) for u in usages)
c = sum(int(u.get("completion_tokens", 0)) for u in usages)
```

两份脚本的"Token 对比汇总"输出永远是 0，A/B 评估的成本结论失真。

### L6. `export_recent_news_csv.py` 输出文件名与参数不符

文件名硬编码 `raw_news_recent_30m.csv` / `selected_news_recent_30m.csv`，而 `--minutes` 可传任意值——用 `--minutes 120` 跑出的仍是"30m"文件名，历史样本（`news/raw_news_recent_30m.csv`）会被无警告覆盖，评估输入可能货不对板。

### L7. `prompts.py` 注释与实际字段数不符

`ANALYZE_PROMPT_TEMPLATE` 注释写"包含 32 个字段"，实际 JSON 输出 25 个字段（3 筛选 + 10 维度 + 2 数组 + 5 文本 + 3 时效 + insight + conclusion）。早期计划书口径残留，会误导后续按"32 字段"扩展的人。

### L8. `filter_news(limit=...)` 在批量超限时静默截断

90 秒窗口给 `limit=100`，正常够用；但回补（`backfill` 用 `max(100, len+20)`）之外的路径若一批超过 limit，多余条目本轮被丢弃且无任何提示（依赖下轮 `run_task` 补）。属"静默截断"模式，建议至少打一条 warning。

### L9. analyze 与 filter 的批处理参数不对称

`filter_news` 有 `only_content_hashes`；`analyze_news` 没有。导致上游无法表达"只分析本批"，是 S6 的直接成因之一。补齐该参数可同时解决 S6 和 L2 的一半。

### L10. "方向/强度 → 文案"逻辑三处重复实现

`pipeline_notify_format.py`（利多黄金/利空黄金）、`static/js/main.js`（利好/利空）、`web_display/index.html`（利好/利空 · 强度）三处各自映射，且措辞不一致（"利多" vs "利好"）。将来调语义（比如 0 的文案）极易漏改。

---

## 3. R 级：健壮性与工程问题

1. **R1 `_sum_usage` 四处复制粘贴**：`run_task.py`、`run_pipeline_90s.py`、`run_pipeline_manual.py`、`scripts/backfill_12h_windows.py` 各一份完全相同的实现。应收敛进 `utils.py` 或 `doubao_client.py`。
2. **R2 根目录与 `scripts/` 重复脚本**：`export_recent_news_csv.py` 两份 MD5 完全一致 **[已验证]**；`run_recent_pipeline_and_export.py` 同样两份。`scripts/README.md` 说 scripts 不入版本库，实际却与根目录形成双维护点。
3. **R3 `sync_news_to_display.py` 写 `feed.json` 非原子**：`json.dump` 直接写目标文件；`sync_loop.sh`（10 秒循环）与 crontab 并发、或页面恰好在写入时 fetch，会读到截断 JSON（静态站已有 catch，但会导致一次空刷）。应写临时文件 + `os.replace`。
4. **R4 `.alert_state.json` 未加入 `.gitignore`**：`.sync_state.json` 加了，告警抑制状态文件没加，一旦 git 化会连同告警历史时间戳一起入库。
5. **R5 `requirements.txt` 缺生产/测试依赖**：无 `gunicorn`（部署文档主推的启动方式）、无 `pytest`（tests 目录存在）。新机器按 requirements 装完仍跑不起文档中的标准流程。
6. **R6 `scripts/debug_doubao.py` URL 拼接与 `.env.example` 冲突**：`url = base + "/api/v3/responses"`，而 `.env.example` 指导填的 `DOUBAO_API_BASE_URL` 已含 `/api/v3`，拼出 `/api/v3/api/v3/responses` 必然 404（主客户端 `doubao_client` 有 `endswith("/api/v3")` 防御，这个脚本没有）。
7. **R7 前端静态资源全靠 jsdelivr CDN**：`web_display/index.html` 与 Tabler CSS/JS 均为 CDN 引用，境内网络抖动即整站无样式/无交互，与"面向国内访问"的部署场景不符。
8. **R8 停摆告警的判据单一**：`PipelineHealthChecker` 只看 `MAX(create_time)`，不看行数/错误日志；新闻源本身停更（如节假日）时会误报"采集层停止"。可接受但应有豁免窗口或静默时段配置。
9. **R9 `run_pipeline_manual.py` 与 `once` 版行为漂移**：once 版会自动打开报告文件（os.startfile/xdg-open），manual 版只写不打开；两份报告文案格式相同但模板代码各自维护。
10. **R10 schema 变更无迁移体系**：全靠 `init_db.py` 幂等补列；无 Alembic、无 `db_migrations/` 目录、无变更历史。列删除/改名/类型变更场景 init_db 无能为力，生产变更只能手写 SQL。
11. **R11 迁移脚本把带密码的连接串打印到控制台**：`migrate_mysql_to_postgres.py` `print(f"源库: {source_url}")`，`sqlalchemy_url` 以 `hide_password=False` 渲染——**密码直接落日志/终端**。运维脚本尤其应 `hide_password=True` 后打印。
12. **R12 前端轮询无退避/失败处理薄弱**：`main.js` 固定 15s `setInterval`，接口失败仅 console.error；页面长时间挂机在接口故障时反复空转。
13. **R13 `scripts/` 无 `__init__.py`**：`from scripts.export_recent_news_csv import main` 依赖 namespace package 才能工作，`python scripts/xxx.py` 与 `python -m scripts.xxx` 两种调用方式的 sys.path 行为不一致，脚本里大量 `sys.path.insert(0, ".")`/`parents[1]` 混用（同一问题三种写法并存）。

---

## 4. O 级：运维与部署问题

1. **O1 文档与 `check_db.py` 互相矛盾**：README/部署文档把 `python check_db.py → DB_OK` 列为验收步骤，但该脚本必败（S3）——按文档执行部署的人会卡在假故障上。
2. **O2 `run_task.py` 无并发保护**：90 秒版有 flock；`run_task.py` 作为文档推荐的定时入口却没有任何锁，cron 重叠即双跑（叠加 L4 的非原子去重 = 重复数据）。
3. **O3 `scripts/sync_loop.sh` 硬编码解释器** `/usr/local/bin/python3`，换机器/虚拟机即失效；同目录其他脚本用 `python3`。
4. **O4 `setup_nginx_for_display.sh` 直接顶替 `default_server` 并 `rm -f sites-enabled/default`**：一次性脚本副作用过大，重跑会静默改掉整台服务器的默认站点。
5. **O5 `run_pipeline_90s.py` 的采集窗口硬编码**：`FETCH_WINDOW_MINUTES = 1.5` 为模块常量，`run_pipeline_90s_loop.sh` 里 `export FETCH_WINDOW_MINUTES=1.5` 完全是无效动作（脚本不读环境变量）——配置意图与实现脱节。
6. **O6 展示域名硬编码在代码默认值里**：`FeishuWebhookConfig.web_base_url` 默认 `https://goldnews-analysis.easypus.com`；换域名时若忘了设 env，推送里的"详情"链接静默指向旧站。

---

## 5. Q 级：代码质量与整洁度

1. **Q1** `run_pipeline_once.py` 应删除（见 S1）；保留损坏文件本身就是问题。
2. **Q2** `prompts.py` / `prompts_new.py` "新旧共存"无切换机制：生产链路仍 import `prompts.py`，v2（基线注入 + confidence/uncertain 字段）写完即闲置；`tests/run_prompt_compare.py` 是唯一消费者。v2 的 `confidence/uncertain` 字段在 `news_analysis_detail` 表中**没有对应列**，即便切换 v2 也会静默丢字段——需要 schema 变更联动，目前无计划文档。
3. **Q3** `web_display/credit.zip` 是与代码无关的二进制 blob，且无任何文档解释用途。
4. **Q4** 无 lint/格式化/类型检查配置（无 ruff/flake8/mypy/pyproject），无 CI；S4 这类断言错误正是无 CI 的直接后果。
5. **Q5** 测试覆盖极薄：仅 `utils` 两个函数 + 来源配置 + fetcher 两个内部函数；`news_filter`（熔断、relevance 回写）、`news_analyzer`（字段规范化）、`app.py`（API）、`alert_service`（抑制/恢复）全部零覆盖。
6. **Q6** `models.py` 三个模型重复声明 `index=True` + 显式 Index（L3）；`Reference` 遗留命名只有 TODO 注释，没有迁移计划文档。
7. **Q7** `app.py` `_parse_dt` 只认三种无时区格式，带毫秒/`Z` 后缀的 ISO（JS `toISOString()` 默认输出带 `Z`）会解析失败返回 None → `/api/news?before=...` 翻页静默退化为"全量最新 N 条"。前端若用 `new Date().toISOString()` 传参会踩坑。

---

## 6. 修复优先级建议

| 优先级 | 事项 | 对应 |
|---|---|---|
| **P0（本周）** | 删除 `run_pipeline_once.py`；修 `check_db.py` 属性名；修测试断言让套件变绿；统一 content_hash（选 blake2b，`utils` 改为 re-export，backfill 改 import） | S1 S3 S4 S2 |
| **P1（两周内）** | `main.js` 补 `escapeHtml` 修 XSS；`analyze_news` 增加 `only_content_hashes` 并把 90s analyze 限制在本批/降单条超时；`run_analysis_latest_20` 时间口径改北京时间；去掉重复索引；`migrate` 脚本隐藏密码 | S5 S6 L1 L3 R11 |
| **P2（一个月）** | `run_task.py` 加 flock；`raw_news.content_hash` 唯一约束 + 幂等写；feed.json 原子写；token 统计键名修复；`.gitignore` 补 `.alert_state.json`；requirements 补 gunicorn/pytest；90s 窗口改读环境变量 | L2 L4 L5 R3 R4 R5 O2 O5 |
| **P3（持续）** | 筛选失败窗口的补偿策略 + 部分失败告警；v2 提示词切换方案（含 confidence/uncertain 落库）；补单测 + CI；前端 CDN 本地化；方向文案收敛为单一映射 | L2 Q2 Q5 R7 L10 |

---

## 7. 与文档的关系

本报告结论已同步进 `docs/project_context_index.md` §5（已知技术债）。修复完成后应：

1. 在本报告末尾追加"已修复"小节并注明日期；
2. 更新 `docs/project_database_schema_reference.md`（若动索引/约束）；
3. 更新 `docs/deployment_reference.md`（若 check_db/依赖变化）；
4. 更新 `docs/project_script_architecture.md`（若删除脚本）。
