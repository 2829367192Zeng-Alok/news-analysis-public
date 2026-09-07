# 将 web_display 上传到 ECS 并部署

当前环境**无法直接通过 SSH 连接您的阿里云 ECS**，需要您在本机完成上传后，在服务器上执行命令。云服务器与云数据库已用密钥在默认地址配置好，以下步骤在项目根目录为 `/root/workspace/project/financial-news-analysis` 的前提下编写。

---

## 一、本机需要上传的内容

确保本地项目中有且已更新：

- 项目根目录下的 **`sync_news_to_display.py`**
- 目录 **`web_display/`**（内含 `index.html`、`data/.gitkeep`）
- （可选）**`scripts/setup_web_display_on_server.sh`**，便于在服务器一键执行

---

## 二、从本机上传到 ECS

在 **本机** 打开 PowerShell 或 CMD，进入本地项目目录后执行（将 `aliyun` 替换为您的 SSH 主机名或 `root@<ECS公网IP>`）：

```powershell
cd C:\Users\28293\Desktop\金融\代码\cursor1\financial-news-analysis

# 上传整个 web_display 目录
scp -r web_display aliyun:/root/workspace/project/financial-news-analysis/

# 上传同步脚本
scp sync_news_to_display.py aliyun:/root/workspace/project/financial-news-analysis/

# 可选：上传部署脚本
scp scripts/setup_web_display_on_server.sh aliyun:/root/workspace/project/financial-news-analysis/scripts/
```

若使用 **rsync**（需在 WSL 或 Git Bash 下）：

```bash
rsync -avz --progress web_display/ aliyun:/root/workspace/project/financial-news-analysis/web_display/
rsync -avz sync_news_to_display.py aliyun:/root/workspace/project/financial-news-analysis/
```

---

## 三、在 ECS 上执行的操作

SSH 登录 ECS 后执行：

```bash
cd /root/workspace/project/financial-news-analysis

# 若上传了 setup 脚本，可直接运行（会创建目录、执行同步、检查结果）
chmod +x scripts/setup_web_display_on_server.sh
bash scripts/setup_web_display_on_server.sh
```

或**不依赖脚本、逐条执行**：

```bash
cd /root/workspace/project/financial-news-analysis
mkdir -p web_display/data
# 确认 web_display/index.html 与 sync_news_to_display.py 已存在（已通过 scp 上传）
python3 sync_news_to_display.py
```

同步脚本会通过**内网连接云数据库**（使用默认地址的配置文件），将 `news_analysis_detail` 导出到 `web_display/data/feed.json`。

---

## 四、对公网开放（可选）

若需通过浏览器访问该静态页：

1. **安装并配置 Nginx**（若未安装）  
   - 将站点根目录设为：`/root/workspace/project/financial-news-analysis/web_display`  
   - 详见 `docs/部署Web展示系统.md`

2. **安全组**  
   - 入方向放行 80（及 443，若用 HTTPS）

3. **定时更新数据**（cron）  
   ```bash
   crontab -e
   # 添加一行，每分钟检查新数据并更新 feed.json
   * * * * * cd /root/workspace/project/financial-news-analysis && python3 sync_news_to_display.py --no-change >> /tmp/sync_news_display.log 2>&1
   ```

---

## 五、我无法代您执行的操作

以下需您在本地或 ECS 上自行完成：

| 操作 | 说明 |
|------|------|
| SSH 连接 ECS | 本环境无法发起 SSH 到您的服务器 |
| 执行 scp/rsync 上传 | 需在本机终端执行，或使用 FinalShell 等工具拖拽上传 |
| 在 ECS 上执行 bash/python 命令 | 需您 SSH 登录后执行 |
| 配置 Nginx、安全组、cron | 需在 ECS 或阿里云控制台操作 |

代码与脚本已在本地项目中准备好，按上述步骤上传并在服务器执行即可完成部署。
