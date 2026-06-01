#!/bin/bash
# 在 ECS 上执行：创建 web_display 目录结构、运行同步脚本、检查结果。
# 使用前请先将本机 web_display 与 sync_news_to_display.py 上传到服务器项目目录。
# 用法：在项目根目录下执行 bash scripts/setup_web_display_on_server.sh

set -e
# 若在项目根目录执行（如 bash scripts/setup_web_display_on_server.sh），则自动使用当前目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$SCRIPT_DIR")}"
if [ -f "$PROJECT_ROOT/config.py" ] && [ -f "$PROJECT_ROOT/models.py" ]; then
  :  # 当前推断的根目录正确
else
  PROJECT_ROOT="${PROJECT_ROOT:-/root/workspace/project/financial-news-analysis}"
fi
cd "$PROJECT_ROOT"

echo "[1/4] 检查项目目录..."
if [ ! -f "config.py" ] || [ ! -f "models.py" ]; then
  echo "错误: 未在 $PROJECT_ROOT 找到 config.py / models.py，请确认路径并先上传主项目代码。"
  exit 1
fi

echo "[2/4] 创建 web_display 目录..."
mkdir -p web_display/data
if [ ! -f "web_display/index.html" ]; then
  echo "错误: 未找到 web_display/index.html，请先将本地 web_display 目录上传到服务器。"
  exit 1
fi
if [ ! -f "sync_news_to_display.py" ]; then
  echo "错误: 未找到 sync_news_to_display.py，请先上传到项目根目录。"
  exit 1
fi

echo "[3/4] 运行同步脚本（内网连接云数据库，写入 web_display/data/feed.json）..."
python3 sync_news_to_display.py
echo "同步完成。"

echo "[4/4] 检查生成文件..."
if [ -f "web_display/data/feed.json" ]; then
  echo "已生成 web_display/data/feed.json"
  wc -l web_display/data/feed.json
else
  echo "警告: feed.json 未生成，请检查数据库连接与 config/.env 配置。"
  exit 1
fi

echo ""
echo "--- 后续可选步骤 ---"
echo "1. 用 Nginx 将站点根目录指向: $PROJECT_ROOT/web_display"
echo "2. 安全组放行 80 端口，通过 http://<ECS公网IP> 访问"
echo "3. 定时更新: crontab -e 添加"
echo "   * * * * * cd $PROJECT_ROOT && python3 sync_news_to_display.py --no-change >> /tmp/sync_news_display.log 2>&1"
