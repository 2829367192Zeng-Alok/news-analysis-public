#!/bin/bash
# 将 web_display 配置为 Nginx 站点（仅当服务器上没有其他 Web 站点时使用）。
# 请用 root 或 sudo 执行。注意：不会删除/覆盖服务器上已有的 default_server；
# 若已有其他站点，请改用 scripts/nginx-domain-ssl.conf 或手工合并配置。
set -e
CONF_NAME="financial-news-display"
ROOT_DIR="/root/workspace/project/financial-news-analysis/web_display"
CONF_PATH="/etc/nginx/sites-available/${CONF_NAME}"

if [ ! -d "$ROOT_DIR" ]; then
  echo "错误: 未找到站点根目录 $ROOT_DIR，请先上传 web_display/。"
  exit 1
fi

echo "写入 Nginx 配置到 ${CONF_PATH} ..."
cat > "$CONF_PATH" << 'NGINXEOF'
server {
    listen 80;
    listen [::]:80;
    server_name _;
    root /root/workspace/project/financial-news-analysis/web_display;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
    location /data/ {
        add_header Cache-Control "no-cache";
    }
}
NGINXEOF

echo "启用站点（不删除其他站点；若此前已有 financial-news-display 符号链接则刷新）..."
ln -sf "$CONF_PATH" /etc/nginx/sites-enabled/

echo "检查 Nginx 配置..."
nginx -t
echo "重载 Nginx..."
systemctl reload nginx
echo "完成。请确保安全组已放行 80 端口，然后访问 http://<ECS公网IP>"
