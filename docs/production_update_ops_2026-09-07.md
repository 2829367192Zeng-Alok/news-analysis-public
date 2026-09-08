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
| 常驻守护 `pipeline_daemon.py` | 20s 轮询（**已确定的生产调度方案**，阿里云 90s 触发已弃用） | systemd 托管（§4） |
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

## 4. 常驻守护进程部署（✅ 已确定为生产调度方案，阿里云 90s 触发已弃用）

> 2026-09-07 决策：调度采用**服务器内常驻轮询**（`pipeline_daemon.py`，20s/轮），
> **不再使用阿里云定时任务**。两套调度绝不可同时运行（会双倍消耗筛选/分析 API）。

单元模板已入库：`deploy/financial-news-daemon.service`（无需 EnvironmentFile——
`config.py` 启动时自动加载工作目录 `.env`，服务与手动运行配置来源一致）。

```bash
cd /root/workspace/project/financial-news-analysis

# 0) 前置：确认阿里云定时任务已停用/删除（控制台或 API），避免双调度

# 1) 部署 systemd 单元
cp deploy/financial-news-daemon.service /etc/systemd/system/financial-news-daemon.service
systemctl daemon-reload

# 2) （可选但推荐）先单轮验证，再常驻
python3 pipeline_daemon.py --once

# 3) 启动并自启
systemctl enable --now financial-news-daemon

# 4) 观察
systemctl status financial-news-daemon
journalctl -u financial-news-daemon -f          # 期望看到"轮次开始/结束"与 token 统计
```

运维要点：

- 改配置（`.env`）后：`systemctl restart financial-news-daemon`；
- 临时停调度（如数据库维护窗口）：`systemctl stop financial-news-daemon`，维护完 `start`；
- 调整轮询间隔：`.env` 设 `POLL_INTERVAL_SECONDS`（默认 20）后重启；
- `--once` 模式用于人工验证，不加单实例锁；
- 日志在 journald（`journalctl -u financial-news-daemon`）；
- 回退到阿里云方案（仅当 daemon 方案被放弃时）：`systemctl disable --now financial-news-daemon`
  后重新启用阿里云定时任务执行 `bash run_pipeline_90s_loop.sh`。

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
  当前生产采用 daemon 模式，`sync_loop.sh` 无需运行。

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

---

## 8. 生产部署执行记录（2026-09-07）

> 以下为 ECS 上实际执行结果，作为部署基线存档。

| 步骤 | 结果 |
|---|---|
| `git pull` | 快进至 `9e8578a` |
| 归一 dry-run | **发现旧 MD5 hash：raw_news 52095 行 / selected_news 11266 行 / news_analysis_detail 16769 行**——证实 S2（双套 hash）在生产真实发生过（backfill 与在线流水线混用所致），并非理论风险 |
| `--update --dedupe` | 已备份后完成归一与去重 |
| `init_db.py` | 冗余 `ix_*` 已删、`uq_raw_content_hash` 已创建、`confidence`/`uncertain` 已补列 |
| `check_db.py` | DB_OK |
| `pipeline_daemon.py --once` | 采集/筛选/补偿/分析/feed 刷新全链路跑通 |
| systemd 服务 | `financial-news-daemon` active (running) 且 enabled |

执行中暴露并处理的问题：

1. **DetachedInstanceError（已回流仓库修复）**：`analyze_news` 返回的 ORM 对象在 `session.close()` 后访问属性报错（`sessionmaker` 默认 `expire_on_commit=True`，commit 即过期全部属性）。修复：每条 commit 后 `session.refresh(detail)` + `session.expunge(detail)`，返回对象可安全在会话外使用。对应提交见仓库；**ECS 上的手工补丁与本修复一致，pull 后可直接丢弃本地改动**（`git checkout -- news_analyzer.py && git pull`）。
2. **飞书推送 403 Forbidden（待处理）**：非代码崩溃，daemon 正常运行。已增强 `webhook_client`（非 2xx 时抛出含飞书响应体的完整错误）并新增 `scripts/check_feishu_webhook.py` 逐 URL 诊断。排查顺序：① 跑检查脚本看具体错误码；② 自定义机器人 403 → 群里机器人是否被移除/停用、Webhook 是否被重置（重置后旧 URL 立即失效）、是否开启签名校验；③ Flow 触发器 403 → Flow 是否停用/重新发布（URL 会变）。
3. **ECS 服务器本地未跟踪文件**：`web_display/cert_tmp/`（TLS 材料）与 `web_display/credit.zip`——已加入 `.gitignore`，**严禁提交**（仓库含公开远端），保留在服务器本地即可。
