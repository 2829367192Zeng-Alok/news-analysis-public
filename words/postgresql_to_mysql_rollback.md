## PostgreSQL -> MySQL 回滚方案

### 1. 停止任务与服务
- 停止循环任务（如 `run_pipeline_90s_loop.sh` / systemd timer / crontab）。
- 停止 Web 服务（`gunicorn` 或 `python app.py`）。

### 2. 切回 MySQL 配置
在 `.env` 中设置：
- `DB_DIALECT=mysql`
- `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` 指向可用 MySQL。

可保留 `POSTGRES_*` 配置，但不作为当前运行库。

### 3. 初始化 MySQL 表结构（如需）
执行：

```bash
python init_db.py
```

### 4. 冒烟验证
执行：

```bash
python run_pipeline_90s.py
```

确认日志里三步（采集 / 筛选 / 分析）均正常结束。

### 5. 恢复定时任务
恢复你的 90 秒循环任务或 systemd 定时器。

### 6. 回滚后检查清单
- 访问 API：`/api/news`、`/api/stats`
- 抽查三张表（`raw_news`、`selected_news`、`news_analysis_detail`）写入是否持续增长
- 连续观察 15~30 分钟运行日志，确认无连接/写入异常
