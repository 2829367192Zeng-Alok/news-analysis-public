# 上传最新流水线脚本到 ECS 并删除损坏文件

ECS 项目路径：`/root/workspace/project/financial-news-analysis`  
将下面命令里的 `aliyun` 替换为您的 SSH 主机名或 `root@<ECS公网IP>`。

---

## 一、本机执行：上传最新文件

在 **本机 PowerShell** 中进入项目目录后执行：

```powershell
cd C:\Users\28293\Desktop\金融\代码\cursor1\financial-news-analysis

# 上传流水线脚本（90 秒版、手动 1 小时版、循环触发脚本）
scp run_pipeline_90s.py run_pipeline_manual.py run_pipeline_90s_loop.sh aliyun:/root/workspace/project/financial-news-analysis/

# 上传说明与修复后的 news_fetcher
scp ALIYUN_90S_触发说明.md aliyun:/root/workspace/project/financial-news-analysis/
scp news_fetcher.py aliyun:/root/workspace/project/financial-news-analysis/
```

---

## 二、在 ECS 上执行：删除损坏文件并确认

SSH 登录 ECS 后执行：

```bash
cd /root/workspace/project/financial-news-analysis

# 删除已损坏的旧流水线脚本
rm -f run_pipeline_once.py

# 确认新脚本存在
ls -la run_pipeline_90s.py run_pipeline_manual.py run_pipeline_90s_loop.sh
```

---

## 三、可选：给循环脚本执行权限

若要在 ECS 上使用每 90 秒循环：

```bash
chmod +x /root/workspace/project/financial-news-analysis/run_pipeline_90s_loop.sh
```

当前 **手动脚本** 已改为 **1 小时** 窗口（`FETCH_WINDOW_MINUTES = 60`），在 ECS 上运行一次示例：

```bash
cd /root/workspace/project/financial-news-analysis && python3 run_pipeline_manual.py
```
