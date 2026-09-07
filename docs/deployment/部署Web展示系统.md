# Web 展示系统部署说明（第六步）

本说明用于：在服务器上部署**静态前端展示页**（基于 [Tabler](https://tabler.io/) 开源模板），并对公网开放；通过**同步脚本**将 `news_analysis_detail` 表数据导出到展示页使用的 JSON，实现“检查新数据并上传到展示系统”。

## 一、方案简述

- **展示系统**：纯静态页面（`web_display/index.html`），从同目录下 `data/feed.json` 读取数据，无需 Flask/Python 运行时。
- **数据来源**：`sync_news_to_display.py` 连接与主项目相同的数据库，读取 `news_analysis_detail`，生成 `web_display/data/feed.json`。
- **部署方式**：将 `web_display/` 目录放到 Nginx 站点根目录，由 Nginx 对公网提供 HTTP(S)；在服务器上用 cron 定期执行同步脚本。

## 二、您需要提前准备的内容

1. **服务器**：已能 SSH 登录（如阿里云 ECS），且与 RDS 同地域/同 VPC（以便用内网连接数据库）。
2. **数据库**：与主项目一致，在 ECS 上已配置好 `.env` 或 `~/.financial_news_analysis.env`（`DB_HOST` 为 RDS 内网地址，`DB_USER`/`DB_PASSWORD`/`DB_NAME` 正确）。
3. **项目代码**：ECS 上已有完整项目目录（例如 `/root/workspace/project/financial-news-analysis`），且已安装 `requirements.txt`（同步脚本依赖 `config`、`models`，与主项目相同）。

若以上任一未就绪，请先完成后再做下面的步骤。

## 三、在服务器上的操作步骤

### 1. 确认项目与数据库可用

```bash
cd /root/workspace/project/financial-news-analysis
# 如有虚拟环境：source venv/bin/activate
python3 -c "
from config import settings
import pymysql
c = settings.db
conn = pymysql.connect(host=c.host, port=c.port, user=c.user, password=c.password, database=c.name, connect_timeout=10)
conn.ping()
print('数据库连接成功')
conn.close()
"
```

### 2. 首次运行同步脚本，生成 feed.json

```bash
cd /root/workspace/project/financial-news-analysis
python3 sync_news_to_display.py
```

执行成功后，应看到类似：`已写入 .../web_display/data/feed.json`，且 `web_display/data/feed.json` 文件存在。

### 3. 安装 Nginx（若未安装）

```bash
# CentOS / Aliyun Linux
sudo yum install -y nginx
# 或 Ubuntu / Debian
# sudo apt update && sudo apt install -y nginx
```

### 4. 将展示目录配置为 Nginx 站点根目录

选择一种方式即可。

**方式 A：独立站点（推荐，便于单独绑域名或端口）**

创建站点配置（路径按你习惯，例如）：

```bash
sudo vim /etc/nginx/conf.d/financial-news-display.conf
```

内容示例（请把 `你的域名或服务器公网IP` 改成实际值，或直接用 `_` 表示默认服务器）：

```nginx
server {
    listen 80;
    server_name 你的域名或服务器公网IP;   # 例如 47.110.3.177 或 news.example.com
    root /root/workspace/project/financial-news-analysis/web_display;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
    location /data/ {
        add_header Cache-Control "no-cache";
    }
}
```

若使用 **HTTPS**，需在服务器上配置证书后再增加 `listen 443 ssl` 及 `ssl_certificate` / `ssl_certificate_key`（或使用 Let’s Encrypt 等），此处不展开。

**方式 B：与现有站点同机、不同 path**

若你已有 Nginx 站点，可在对应 `server` 里增加：

```nginx
location /financial-news/ {
    alias /root/workspace/project/financial-news-analysis/web_display/;
    try_files $uri $uri/ /financial-news/index.html;
}
```

此时访问地址为：`http://你的域名/financial-news/`。

保存后检查配置并重载：

```bash
sudo nginx -t && sudo nginx -s reload
```

### 5. 开放公网访问（安全组 / 防火墙）

- **阿里云 ECS**：在 ECS 实例的安全组中，入方向放行 **80**（及 443，若用 HTTPS）。
- 若服务器本机有 **firewalld**：`sudo firewall-cmd --permanent --add-service=http && sudo firewall-cmd --reload`。

完成后在浏览器访问：`http://你的ECS公网IP`（或你配置的域名）。应能看到“金融新闻分析”页面；若 `data/feed.json` 已有数据，会显示列表与详情。

### 6. 配置定时任务：定期检查新数据并更新展示

使用 cron 每分钟执行一次同步脚本（仅在数据变化时写文件，可用 `--no-change` 减少磁盘写入）：

```bash
crontab -e
```

增加一行（路径按你实际项目路径修改）：

```cron
* * * * * cd /root/workspace/project/financial-news-analysis && /usr/bin/python3 sync_news_to_display.py --no-change >> /tmp/sync_news_display.log 2>&1
```

若使用虚拟环境，改为：

```cron
* * * * * cd /root/workspace/project/financial-news-analysis && source venv/bin/activate && python3 sync_news_to_display.py --no-change >> /tmp/sync_news_display.log 2>&1
```

这样会每分钟检查一次 `news_analysis_detail`；有新数据时才会更新 `web_display/data/feed.json`，前端刷新或等约 20 秒自动轮询即可看到新内容。

## 四、同步脚本说明

| 命令 | 说明 |
|------|------|
| `python3 sync_news_to_display.py` | 每次都从数据库导出并覆盖 `web_display/data/feed.json` |
| `python3 sync_news_to_display.py --no-change` | 仅当总条数或最大 id 变化时才写入，适合 cron |
| `python3 sync_news_to_display.py --limit 200` | 导出最近 200 条（默认 100） |

状态文件 `web_display/.sync_state.json` 用于记录上次的条数与最大 id，供 `--no-change` 判断是否有新数据；可忽略或加入 `.gitignore`。

## 五、需要您提供或确认的信息

- **服务器项目路径**：若不用 `/root/workspace/project/financial-news-analysis`，请在 Nginx 与 cron 中改成实际路径。
- **域名 / 端口**：若使用域名或非 80 端口，需在 Nginx 中相应修改 `server_name` / `listen`，并确认安全组放行对应端口。
- **Python 解释器**：cron 中建议写绝对路径 `/usr/bin/python3`，或先 `which python3` 确认。
- **权限**：Nginx 需能读 `web_display/` 下所有文件（含 `data/feed.json`）；若 Nginx 以 `nginx` 用户运行，而项目在 `root` 下，需保证目录可被读（例如 `chmod 755` 各层目录）。

按上述步骤完成后，第六步的 Web 展示系统即可：在服务器部署、对公网开放，并通过脚本检查 `news_analysis_detail` 新数据并“上传”到展示系统（写入 feed.json）。
