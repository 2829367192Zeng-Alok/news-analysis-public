# 阿里云每 90 秒触发流水线说明

## 一、单次执行（90 秒窗口）

在 ECS 上执行一次 90 秒窗口流水线：

```bash
cd /root/workspace/project/financial-news-analysis && python3 run_pipeline_90s.py
```

## 二、每 90 秒自动执行

**方式 1：循环脚本（推荐）**

```bash
cd /root/workspace/project/financial-news-analysis
chmod +x run_pipeline_90s_loop.sh
nohup ./run_pipeline_90s_loop.sh > pipeline_90s_loop.log 2>&1 &
```

- 查看日志：`tail -f pipeline_90s_loop.log`
- 停止：`pkill -f run_pipeline_90s_loop`

**方式 2：直接用一条命令**

```bash
cd /root/workspace/project/financial-news-analysis && while true; do python3 run_pipeline_90s.py; sleep 90; done
```

后台运行可加 `nohup ... &`。

**说明**：cron 最小粒度为 1 分钟，无法实现“每 90 秒”；因此每 90 秒执行需用上述循环或 systemd timer（需自行配置秒级触发）。
