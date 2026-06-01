#!/bin/bash
# 将 web_display 配置为 Nginx 站点根目录。请用 root 或 sudo 执行。
set -e
CONF_NAME="financial-news-display"
ROOT_DIR="/root/workspace/project/financial-news-analysis/web_display"
CONF_PATH="/etc/nginx/sites-available/${CONF_NAME}"

echo "写入 Nginx 配置到 ${CONF_PATH} ..."
cat > "$CONF_PATH" << 'NGINXEOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
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

echo "启用站点并禁用默认站点..."
ln -sf "$CONF_PATH" /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

echo "检查 Nginx 配置..."
nginx -t
echo "重载 Nginx..."
systemctl reload nginx
echo "完成。请确保安全组已放行 80 端口，然后访问 http://<ECS公网IP>"
