#!/bin/bash
cd /root/workspace/project/financial-news-analysis || exit 1
while true; do
  /usr/local/bin/python3 sync_news_to_display.py --no-change >> /tmp/sync_news_display.log 2>&1
  sleep 10
done
