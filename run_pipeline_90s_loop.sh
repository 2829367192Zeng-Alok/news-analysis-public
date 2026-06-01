#!/bin/bash
# 单次执行：阿里云每 90 秒触发一次本脚本，跑一轮 90 秒窗口流水线后退出。日志写入 logs/pipeline_1min.log。
# 实际执行：python3 run_pipeline_90s.py（含健康检查与飞书告警，分析完成后推送飞书 Webhook）。
# 用法：cd /root/workspace/project/financial-news-analysis && bash run_pipeline_90s_loop.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/pipeline_1min.log"
REPORT_FILE="${SCRIPT_DIR}/pipeline_report.txt"
TIMEOUT_SEC=10000

# 90 秒采集窗口
export FETCH_WINDOW_MINUTES=1.5

START_TS=$(date +%s)
START_STR=$(date '+%Y-%m-%d %H:%M:%S')
{
  echo ""
  echo "========== 开始 $START_STR =========="
  timeout "$TIMEOUT_SEC" python3 run_pipeline_90s.py 2>&1 || true
  END_TS=$(date +%s)
  ELAPSED=$((END_TS - START_TS))
  END_STR=$(date '+%Y-%m-%d %H:%M:%S')
  echo "========== 结束 $END_STR  wallclock=${ELAPSED}s =========="
  if [ -f "$REPORT_FILE" ]; then
    echo "--- 当次报告 ---"
    cat "$REPORT_FILE"
  fi
  echo ""
} >> "$LOG_FILE" 2>&1
