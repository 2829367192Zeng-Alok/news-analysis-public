#!/bin/bash
# 单次执行：阿里云每 90 秒触发一次本脚本，跑一轮 90 秒窗口流水线后退出。
# 实际执行：python3 run_pipeline_90s.py（含健康检查与飞书告警）。
# 用法：cd /root/workspace/project/financial-news-analysis && bash run_pipeline_90s_loop.sh

# ── 并发保护：若上一轮尚未完成则直接退出，不排队等待 ──────────────────────
LOCK_FILE="/tmp/pipeline_financial_news.lock"
exec 200>"$LOCK_FILE"
flock -n 200 || {
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SKIP] 上一轮仍在执行，本次跳过"
    exit 0
}

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/pipeline_1min.log"
REPORT_FILE="${SCRIPT_DIR}/pipeline_report.txt"
# 240s：与 news_analyzer 单条分析超时(240s)对齐，保证在途调用可完整返回；
# 触发间隔仍为 90s，重叠轮次由 flock 直接跳过，不会堆积。
TIMEOUT_SEC="${TIMEOUT_SEC:-240}"

# 采集窗口（分钟）：python 侧 run_pipeline_90s.py 会读取该环境变量，默认 1.5
export FETCH_WINDOW_MINUTES="${FETCH_WINDOW_MINUTES:-1.5}"

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
