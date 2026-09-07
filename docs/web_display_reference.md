# 金融新闻分析系统 Web 展示参考

> 版本：v1.0  
> 更新时间：2026-09-07  
> 适用代码：`app.py`、`templates/`、`static/`、`sync_news_to_display.py`、`web_display/`

项目存在**两套并存的展示形态**，数据源相同（`news_analysis_detail` 表），但服务方式不同：

| 形态 | 入口 | 服务方式 | 部署目录 |
|---|---|---|---|
| Flask 动态站 | `app.py` | 实时查询数据库 | `/root/workspace/project/financial-news-analysis` |
| 静态展示站 | `web_display/index.html` | 读取 `feed.json` | 服务器 Nginx 静态目录 |

---

## 1. Flask 动态站

### 1.1 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 渲染 `templates/index.html` |
| `/api/news` | GET | 分析结果列表（默认 50 条，最大 200），支持 `before` / `after` ISO 时间游标翻页 |
| `/api/news/<id>` | GET | 单条新闻完整分析（含全部五维字段、原文 content） |
| `/api/stats` | GET | 总条数与最新 `news_datetime` |

### 1.2 列表接口返回字段

`/api/news` 每条记录包含：

- `id`、`title`、`source`、`news_datetime`
- `relevance`、`direction`、`impact`
- `shorttime`、`midtime`、`longtime`
- `insight`、`conclusion`

详情接口 `/api/news/<id>` 额外返回：

- `content`（原文）
- 五维方向/强度（`interest_*`、`dollar_*`、`warrisk_*`、`liquidity_*`、`emotion_*`）
- 五维文字分析（`interest`、`dollar`、`warrisk`、`liquidity`、`emotion`）
- `keyword`、`Reference` 列表

### 1.3 会话与连接管理

- `app.py` 使用 `scoped_session`；
- `teardown_appcontext` 中调用 `remove_db_session()` 归还连接；
- 请求内通过 `_db_session()` 上下文管理器保证异常时 rollback。

### 1.4 前端

- `templates/index.html`：单页布局（左列表 + 右详情）；
- `static/js/main.js`：
  - `loadStats()` / `loadNewsList()` / `loadDetail(id)`；
  - 15 秒自动刷新列表与统计；
  - 点击列表项加载详情；
  - 方向徽章（利好 / 利空 / 中性 + 强度）；
  - 关键词以 pill 标签展示。
- `static/css/style.css`：深色主题、响应式（≤900px 单列）。

### 1.5 启动方式

```bash
# 开发
python app.py

# 生产
gunicorn -w 2 -b 0.0.0.0:8000 "app:app"
```

---

## 2. 静态展示站（web_display）

### 2.1 数据来源

`sync_news_to_display.py` 从数据库导出：

- `web_display/data/feed.json`：包含 `stats` + `items`（列表字段）+ `details`（全字段，按 id 索引）
- `web_display/.sync_state.json`：记录 `total_news` 与 `max_id`，用于 `--no-change` 增量跳过

### 2.2 用法

```bash
python sync_news_to_display.py              # 总是覆盖写入
python sync_news_to_display.py --no-change  # 仅数据变化时写入
python sync_news_to_display.py --limit 100  # 导出条数（默认 100）
```

### 2.3 服务器常驻同步

`scripts/sync_loop.sh` 以 10 秒间隔循环执行 `--no-change` 同步（服务器侧部署）。

### 2.4 前端

`web_display/index.html`（约 14KB）基于 Tabler CSS：

- 列表 + 详情双栏，移动端列表可收起；
- 详情展示五维分析、关键词、原文、时间维度结论；
- 纯静态，无后端依赖，适合 Nginx 直接托管。

### 2.5 附加文件

- `web_display/credit.zip`：早期遗留的版权/署名资源包，代码与页面均无引用，已于 2026-09-07 清理删除（如需恢复可从历史提交取回）。

---

## 3. 两套展示的一致性

两套展示的字段口径必须与 `news_analysis_detail` 保持一致。新增分析字段时的同步顺序：

1. `models.py` 加列
2. `init_db.py` 补列
3. `news_analyzer.py` 写入新字段
4. `app.py` API 返回新字段
5. `sync_news_to_display.py` 导出新字段
6. `static/js/main.js` 与 `web_display/index.html` 展示新字段
7. 更新本文与 `docs/project_database_schema_reference.md`

---

## 4. 部署相关

- Nginx 配置参考：`scripts/nginx-domain-ssl.conf`、`scripts/setup_nginx_for_display.sh`、`docs/Nginx单行部署说明.md`
- 一键部署脚本：`scripts/setup_web_display_on_server.sh`
- 域名与 SSL 步骤：`docs/域名部署协作步骤.md`
- 当前线上展示域名（飞书推送中引用）：`FEISHU_PUSH_WEB_BASE_URL`（默认 `https://goldnews-analysis.easypus.com`）

---

## 5. 常见问题

| 现象 | 排查方向 |
|---|---|
| 页面无数据 | `run_pipeline_90s.py` 是否在跑；`/api/stats` 是否有值 |
| 静态页不更新 | `sync_news_to_display.py` 循环是否存活；`.sync_state.json` 是否卡住 |
| 详情 404 | 该 id 是否已被清理；游标翻页时间格式是否为 ISO |
| 翻页返回空 | `before`/`after` 需 ISO 或 `YYYY-MM-DD HH:MM:SS` 格式 |
