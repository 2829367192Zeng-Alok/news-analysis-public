# 生产更新与运维手册（2026-09-07 版）

> 适用架构：本地开发 → push GitHub → 生产 ECS pull → 运行。
> 本手册覆盖本次（v2 提示词落库、幂等写入、常驻守护、实时展示）上线的**完整操作清单**。
> 原则：**代码经 git 同步；数据库变更必须手动执行**，二者时序见 §2。

---

## 1. 本次变更加速器（先读）

| 模块 | 变更 | 生效条件 |
|---|---|---|
| `prompts_new` v2 提示词 | 新增 `USE_PROMPTS_V2` 开关 + `confidence`/`uncertain` 两列 | 开关默认关；开闸前必须先建列（§3 步骤 3） |
| 幂等写入 | `news_fetcher` 遇唯一约束冲突降级逐条提交 | 依赖 `uq_raw_content_hash` 唯一索引（§3 步骤 3） |
| 冗余索引清理 | `init_db.py` 自动 DROP 历史遗留 `ix_*` | pull 后跑一次 init_db 即生效 |
| `raw_news.content_hash` 唯一索引 | `init_db.py` best-effort 创建 `uq_raw_content_hash` | 库内无重复时自动建成；有重复会提示先归一（§2） |
| 常驻守护 `pipeline_daemon.py` | 20s 轮询替代阿里云 90s 触发（二选一） | systemd 托管（§4） |
| 实时展示 | Flask `/api/stream`（SSE）+ 前端自动回退轮询；静态站 5s 轮询 | gunicorn 线程配置见 §5 注意事项 |

---

## 2. 数据库前置步骤（在 ECS 上执行，本地无法直连 RDS）

> 生产 PG 库只对 ECS 内网开放（安全组/白名单）。以下命令一律在
> `/root/workspace/project/financial-news-analysis` 下执行。

```bash
cd /root/workspace/project/financial-news-analysis

# 0) 拉取代码
git pull origin main

# 1) （首次）content_hash 归一扫描 —— 只读，安全
python scripts/normalize_content_hash.py --dry-run

# 1a) 若 dry-run 报告"32位旧hash"为 0：跳过归一，直接进入步骤 3
# 1b) 若 > 0：择维护窗口（建议暂停流水线/守护进程）执行：
#     pg_dump 备份三表后：
python scripts/normalize_content_hash.py --update --dedupe

# 2) Schema 同步（幂等，可重复执行）：
#    - 清理遗留 ix_* 冗余索引
#    - 创建 uq_raw_content_hash（库内仍有重复时此处会提示先做 1b）
#    - 为 v2 补 confidence / uncertain 两列
python init_db.py

# 3) 验证
python check_db.py            # 期望 DB_OK
pytest tests/ -q              # 18 passed（生产机需装 requirements-dev.txt 可跳过）
```

> **回滚**：归一/去重前务必备份（`pg_dump -t raw_news -t selected_news -t news_analysis_detail`）。
> 唯一索引回滚：`DROP INDEX uq_raw_content_hash;`

---

## 3. v2 提示词开关（决策点 3，默认关闭）

```bash
# 开闸前自检清单：
# [ ] init_db.py 已跑过且日志含"confidence/uncertain"补列（或已存在）
# [ ] config/macro_baseline.yaml 已就位且有人负责定期更新（基线为空时 v2 收益打折）
# [ ] tests/run_prompt_compare.py 的 A/B 结论可接受（成本上升方向已知）

# 在 .env 中设置后重启流水线/守护进程：
USE_PROMPTS_V2=1

# 回滚：注释掉该行或设为空，重启即可；新列可空，不影响 v1 行为。
```

---

## 4. 常驻守护进程部署（替代阿里云 90s 定时触发）

**二选一，不要同时开**（两套调度并行会放大筛选/分析 API 消耗）：

```ini
# /etc/systemd/system/financial-news-daemon.service
[Unit]
Description=Financial news pipeline daemon
After=network.target

[Service]
WorkingDirectory=/root/workspace/project/financial-news-analysis
EnvironmentFile=/root/workspace/project/financial-news-analysis/.env
ExecStart=/usr/local/bin/python3 pipeline_daemon.py
Restart=always
RestartSec=10
User=root

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now financial-news-daemon
journalctl -u financial-news-daemon -f     # 观察首轮
```

- `--once` 模式用于运维验证：`python pipeline_daemon.py --once`
- 若保留阿里云 90s 触发（旧方案）：确认 `run_pipeline_90s_loop.sh` 正常即可，**不要**再启动 daemon。
- 迁移到 daemon 时：先停阿里云定时任务，再 `systemctl start`，观察日志 10 分钟。

---

## 5. Web 与实时展示注意事项

- Flask 新增 `GET /api/stream`（SSE，服务端 5s 轮询库，有新分析立即推送）。
  前端已实现：SSE 可用则推送式刷新；不可用自动回退 5s 轮询（指数退避至 60s）。
- **gunicorn 必须用线程模式**，否则每个 SSE 长连接占死一个 sync worker：

```bash
gunicorn -w 2 --threads 8 -b 0.0.0.0:8000 app:app
```

- 静态站 `web_display/index.html` 已改为 5s 轮询；`scripts/sync_loop.sh` 同步间隔改为 5s。
  daemon 模式下有新分析会主动调 `sync_news_to_display.run_sync()`，sync_loop 可停用（二选一）。

---

## 6. 上线后验证清单

- [ ] `python check_db.py` → DB_OK
- [ ] daemon/90s 日志出现正常轮次（采集→筛选→分析 tokens 统计）
- [ ] `init_db.py` 输出：冗余 `ix_*` 已删、`uq_raw_content_hash` 已建或给出归一提示
- [ ] `/api/stream` 在浏览器 DevTools EventSource 中看到 keepalive/update 帧
- [ ] 有新分析时静态站 5s 内更新、飞书群收到推送
- [ ] （若开 v2）抽查 `news_analysis_detail.confidence/uncertain` 非空

## 7. 故障速查

| 症状 | 排查 |
|---|---|
| 分析步骤全部失败 | 是否开了 `USE_PROMPTS_V2` 但未跑 `init_db.py`（缺 confidence/uncertain 列）|
| 采集批量写入报唯一约束冲突日志 | 正常降级行为（幂等写入）；频繁出现说明上游有重复源，检查 `normalize_content_hash` |
| `uq_raw_content_hash` 创建失败 | 库内有重复 hash，跑 `--update --dedupe` 后重跑 init_db |
| SSE 一直 fallback 轮询 | gunicorn 是否用 sync worker（见 §5）；Nginx 反代需 `proxy_buffering off` |
