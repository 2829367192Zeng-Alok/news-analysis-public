# 金融新闻分析系统

新闻采集（Tushare）→ AI 筛选（豆包）→ AI 详细分析（豆包）→ 云数据库存储，Web 展示。部署于阿里云 ECS，通过内网连接云数据库 RDS。

## 本地 / ECS 配置

### 1. 配置文件与密钥（默认地址）

- **环境变量**：优先从环境变量读取，无需在代码中写密钥。
- **默认配置文件**（可选）：  
  - 项目目录下的 `.env`  
  - 用户目录下的 `~/.financial_news_analysis.env`  
  复制 `.env.example` 为上述任一文件并填写真实值。安装依赖后会自动通过 `python-dotenv` 加载。

### 2. 云数据库内网连接（ECS 必做）

在 **ECS 上** 运行时应使用 RDS **内网地址**，以降低延迟并避免公网流量：

1. 登录 [阿里云 RDS 控制台](https://rdsnext.console.aliyun.com/)
2. 选择实例 → **数据库连接** → 复制 **内网地址**（与 ECS 同地域、同 VPC 时可用）
3. 在 ECS 上设置环境变量或写入配置文件，例如：
   ```bash
   export DB_HOST=rm-xxxxx.mysql.rds.aliyuncs.com   # 替换为你的内网地址
   export DB_PORT=3306
   export DB_USER=你的数据库用户
   export DB_PASSWORD=你的数据库密码
   export DB_NAME=news_analysis
   ```
   或在 `~/.financial_news_analysis.env` / 项目目录 `.env` 中配置上述变量。

### 3. SSH 连接 ECS（开发/部署用）

本机通过 SSH 连接阿里云 ECS 时，请在本机维护 SSH 配置（默认路径 `~/.ssh/config`），例如：

```text
Host aliyun
    HostName <你的 ECS 公网 IP>
    User root
    Port 22
    IdentityFile C:/Users/28293/.ssh/id_ed25519
```

将 `HostName` 替换为 ECS 公网 IP。连接命令：

```bash
ssh aliyun
```

在 ECS 上项目路径为：`/root/workspace/project/financial-news-analysis`（可按需调整）。

## 部署步骤（ECS）

| 步骤 | 说明 |
|------|------|
| 1 | 在 ECS 上创建目录，如 `mkdir -p /root/workspace/project`，并上传或 git clone 本仓库到 `financial-news-analysis` |
| 2 | `cd financial-news-analysis && pip install -r requirements.txt` |
| 3 | 在 ECS 上配置 `.env` 或 `~/.financial_news_analysis.env`，**DB_HOST 填 RDS 内网地址** |
| 4 | 初始化数据库表：`python -c "from models import Base, engine; Base.metadata.create_all(engine)"` |
| 5 | 配置阿里云定时任务（如每 10 秒执行）：`python run_task.py` |
| 6 | 启动 Web：`gunicorn -w 2 -b 0.0.0.0:8000 "app:app"` 或 `python app.py` |
| 7 | （可选）Nginx 反向代理、开放安全组端口 8000 |

## 部署检查清单

- [ ] ECS 已安装 Python 3.8+、pip
- [ ] `requirements.txt` 已安装
- [ ] 已配置 TUSHARE_TOKEN、DOUBAO_API_KEY
- [ ] **DB_HOST 使用 RDS 内网地址**，且 ECS 与 RDS 同地域/同 VPC
- [ ] 数据库已建库 `news_analysis`，且执行过表结构初始化
- [ ] 定时任务可正常执行 `python run_task.py`（查看日志无报错）
- [ ] Web 服务可访问 `/api/news`、`/api/stats`

## 项目结构

- `config.py` - 配置（数据库、Tushare、豆包），支持 .env 与内网 DB
- `models.py` - 表结构 raw_news / selected_news / news_analysis_detail
- `news_fetcher.py` - Tushare 采集、去重、写入 raw_news
- `news_filter.py` - 豆包筛选，写入 selected_news
- `news_analyzer.py` - 豆包详细分析，写入 news_analysis_detail
- `run_task.py` - 定时任务入口（采集→筛选→分析），带日志与分步异常处理
- `app.py` - Flask API 与前端
- `doubao_client.py` - 豆包 API 封装（含重试）
- `web_display/` - 静态展示页（Tabler 模板，读 `data/feed.json`）
- `sync_news_to_display.py` - 将 news_analysis_detail 导出到 `web_display/data/feed.json`，供静态页展示；可配合 cron 定时更新

## 注意事项

- 配置文件与 `.env` 含敏感信息，不要提交到版本库。
- 定时任务频率较高（如 10 秒）时，注意 Tushare/豆包 API 调用限制与配额。
