# Nginx 单行部署说明（FinalShell 等仅支持单行输入时）

## 方式一：上传脚本后执行一行命令（推荐）

1. **上传脚本**  
   用 FinalShell 左侧 **文件** / **SFTP** 打开服务器目录：  
   ` /root/workspace/project/financial-news-analysis/scripts/`  
   把本机项目里的 **`scripts/setup_nginx_for_display.sh`** 拖进去或右键上传。

2. **在 FinalShell 终端里只输入下面这一行并回车**（需已安装 Nginx：`apt install -y nginx`）：
   ```bash
   sudo bash /root/workspace/project/financial-news-analysis/scripts/setup_nginx_for_display.sh
   ```
   若当前已是 root，可去掉 `sudo`：
   ```bash
   bash /root/workspace/project/financial-news-analysis/scripts/setup_nginx_for_display.sh
   ```

---

## 方式二：不传文件，只粘贴一条“长命令”

若暂时不方便上传文件，可在 FinalShell 终端**一次性粘贴下面这一整行**（整行复制、一次粘贴、回车）。  
先确保已安装 Nginx：`apt update && apt install -y nginx`。

```bash
echo 'IyEvYmluL2Jhc2gNCiMg54GPP3dlYl9kaXNwbGF5IOmWsOW2h+eWhua2kz9OZ2lueCDnu5TmrJHlgaPpj43lnK3mtLDopLDmm5jigqzlgp3uh6zpkKI/cm9vdCDpjrQ/c3VkbyDpjrXRhu6UkemKhj8Kc2V0IC1lDQpDT05GX05BTUU9ImZpbmFuY2lhbC1uZXdzLWRpc3BsYXkiDQpST09UX0RJUj0iL3Jvb3Qvd29ya3NwYWNlL3Byb2plY3QvZmluYW5jaWFsLW5ld3MtYW5hbHlzaXMvd2ViX2Rpc3BsYXkiDQpDT05GX1BBVEg9Ii9ldGMvbmdpbngvc2l0ZXMtYXZhaWxhYmxlLyR7Q09ORl9OQU1FfSINCg0KZWNobyAi6Y2Q5qyP5Y+GIE5naW54IOmWsOW2h+eWhumNkj8ke0NPTkZfUEFUSH0gLi4uIg0KY2F0ID4gIiRDT05GX1BBVEgiIDw8ICdOR0lOWEVPRicNCnNlcnZlciB7DQogICAgbGlzdGVuIDgwIGRlZmF1bHRfc2VydmVyOw0KICAgIGxpc3RlbiBbOjpdOjgwIGRlZmF1bHRfc2VydmVyOw0KICAgIHNlcnZlcl9uYW1lIF87DQogICAgcm9vdCAvcm9vdC93b3Jrc3BhY2UvcHJvamVjdC9maW5hbmNpYWwtbmV3cy1hbmFseXNpcy93ZWJfZGlzcGxheTsNCiAgICBpbmRleCBpbmRleC5odG1sOw0KICAgIGxvY2F0aW9uIC8gew0KICAgICAgICB0cnlfZmlsZXMgJHVyaSAkdXJpLyAvaW5kZXguaHRtbDsNCiAgICB9DQogICAgbG9jYXRpb24gL2RhdGEvIHsNCiAgICAgICAgYWRkX2hlYWRlciBDYWNoZS1Db250cm9sICJuby1jYWNoZSI7DQogICAgfQ0KfQ0KTkdJTlhFT0YNCg0KZWNobyAi6Y2a7oic5pWk57uU5qyR5YGj6aqe5YmB7pum6ZCi44Sp57Kv55KB44KH54+v6ZCQPy4uIg0KbG4gLXNmICIkQ09ORl9QQVRIIiAvZXRjL25naW54L3NpdGVzLWVuYWJsZWQvDQpybSAtZiAvZXRjL25naW54L3NpdGVzLWVuYWJsZWQvZGVmYXVsdCAyPi9kZXYvbnVsbCB8fCB0cnVlDQoNCmVjaG8gIuWmq+KCrOmPjD9OZ2lueCDplrDltofnloYuLi4iDQpuZ2lueCAtdA0KZWNobyAi6Zay5baI5rWHIE5naW54Li4uIg0Kc3lzdGVtY3RsIHJlbG9hZCBuZ2lueA0KZWNobyAi54C55bG+5Z6a6YqG5YKd7oes57qt7oa757ma54C55aSK5Y+P57yB5Yur5Yeh6Y+A5o2Q7pSRIDgwIOe7lO6ImuW9m+mUm+WygOWKp+mNmuW6pO6GlumXgj9odHRwOi8vPEVDU+mNj+6Egue2iUlQPiINCg==' | base64 -d | sed 's/\r$//' | bash
```

（该命令会解码并执行与 `setup_nginx_for_display.sh` 等效的脚本，无需先上传文件。若执行报错，请改用方式一上传脚本后执行。）

---

## 安装 Nginx（若尚未安装）

Ubuntu 下只需执行（可分行执行两行，或合并为一行）：

```bash
apt update && apt install -y nginx
```

若提示权限不足则加 `sudo`：

```bash
sudo apt update && sudo apt install -y nginx
```

---

## 完成后

- 在阿里云 ECS 安全组入方向放行 **80** 端口。
- 浏览器访问：`http://47.110.3.177`（或你的 ECS 公网 IP）。
