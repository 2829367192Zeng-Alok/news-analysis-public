#!/bin/bash
# 默认循环同步静态展示数据。建议由 systemd / cron 管理，而不是手工常驻。
set -euo pipefail
cd /root/workspace/project/financial-news-analysis || exit 1
PYTHON_BIN="${PYTHON_BIN:-python3}"
while true; do
  "$PYTHON_BIN" sync_news_to_display.py --no-change >> /tmp/sync_news_display.log 2>&1
  sleep 10
done
