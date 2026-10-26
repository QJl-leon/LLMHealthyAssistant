# 本机生产部署

访问地址：https://www.smproject.site

- Nginx 提供 `/var/www/lha` 静态前端，并代理 API、上传和 SSE 到 `127.0.0.1:8080`。
- 运行配置：`/etc/nginx/sites-available/lha`；仓库副本：`www.smproject.site.conf`。
- 证书：`/etc/letsencrypt/live/www.smproject.site/`，由 `certbot.timer` 自动续期。
- 证书采用 HTTP-01 验证：公网 TCP 80 必须保持可达；普通 HTTP 请求跳转 HTTPS，验证路径除外。公网 TCP 443 提供网站。
- 续期后 `/etc/letsencrypt/renewal-hooks/deploy/lha-reload-nginx` 校验并重载 Nginx。
- Go、Python、MinIO 已加入 `multi-user.target`；数据库、Redis、Milvus、OTel 使用 Docker 自动重启，端口只发布到回环地址。原有持久卷保留。
- Vite 开发服务已停止。生产环境不使用 `scripts/start-all.sh` 启动开发前端。
- `.env` 已启用 `AUTH_REQUIRED=true` 并配置 JWT 密钥；业务 API 需要登录。不要提交或输出 `.env`。

## 检查

```bash
LHA_FRONTEND_URL=https://www.smproject.site python-ai/.venv/bin/python scripts/local/check-local.py
sudo nginx -t
sudo certbot renew --dry-run --run-deploy-hooks --no-random-sleep-on-renew
```

依赖检查不调用付费模型 API，也不表示已经验证模型回答质量。

## 更新前端

在项目根目录执行：

```bash
source scripts/local/local-env.sh
npm --prefix web run build
sudo cp -a web/dist/. /var/www/lha/
```

## 应用日志

```bash
sudo journalctl -u nginx
sudo tail -n 100 .run/go-systemd.log
sudo tail -n 100 .run/python-systemd.log
```
