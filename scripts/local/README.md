# 本机专用启动脚本

此目录用于 `/home/ubuntu/RAG-job/LLMHealthyAssistant` 的 Ubuntu 本机环境。脚本使用工作区 `.tools` 工具链、systemd 服务和本机 MinIO 二进制；安装版本、地址与重装命令见 [本机环境配置](../../本机环境配置.md)。

| 文件 | 作用 |
| --- | --- |
| `start-local.sh` | 启动指定 Compose 基础设施，链接并加载本机 systemd 服务，初始化存储桶、执行业务迁移、构建 Go 后端并启动应用 |
| `stop-local.sh` | 默认停止 Python、Go、Vite；加 `--all` 时还停止本机 MinIO 和 Compose 服务，保留数据 |
| `local-env.sh` | 为当前 shell 设置 `.tools` 中的 Go、Node、uv、MinIO 路径及 uv 缓存目录 |
| `check-local.py` | 实际连接 PostgreSQL、Redis、Milvus、MinIO、gRPC、Go、前端，失败时返回非零；不调用模型 API |
| `init-local-bucket.py` | 从项目 `.env` 读取 MinIO 连接参数，幂等创建存储桶 |
| `run-minio.py` | 从 `.env` 读取凭据并启动 `.tools/bin/minio`，供本机 systemd 服务调用 |

## 本机使用

在项目根目录执行：

```bash
bash scripts/local/start-local.sh
python-ai/.venv/bin/python scripts/local/check-local.py
bash scripts/local/stop-local.sh
bash scripts/local/stop-local.sh --all
```

只设置当前终端工具链：

```bash
source scripts/local/local-env.sh
```

启动与停止需要 sudo 权限。`deploy/local/*.service` 仍包含本机绝对路径和 `User=ubuntu`，迁移到其他机器、用户或目录时必须调整。启动脚本会执行 `systemctl daemon-reload`，使更新后的 MinIO 脚本路径生效。本次分类只修改文件和引用，没有启动、停止或重启服务；已运行的进程保持当前状态。当前未设置开机自动启动。

## 与项目原始方式的区别

原项目主入口为根目录的 [`start.sh`](../../start.sh)、[`stop.sh`](../../stop.sh)、[`restart.sh`](../../restart.sh)、[`check.sh`](../../check.sh)；`scripts/start-all.sh`、`scripts/stop-all.sh` 是原有的另一组启动/停止入口。它们保留在原位置。

| 项目 | 本机专用 `scripts/local/` | 项目原始入口 |
| --- | --- | --- |
| 应用进程管理 | systemd 管理 Python、Go、Vite，配置 `Restart=on-failure` | `nohup` 启动；根目录入口记录 PID，停止脚本使用 PID/进程检查；不提供 systemd 自动重启 |
| 基础设施 | Compose 只启动 PostgreSQL、Redis、Milvus、OTel；MinIO 单独用 systemd | 启动 Compose 中全部服务，包括 Docker MinIO |
| MinIO 来源 | 本机镜像拉取失败后从源码构建的 `.tools/bin/minio` | Compose 定义的 MinIO 镜像 |
| 工具链 | `local-env.sh` 显式把工作区 `.tools` 加入 PATH | 使用当前系统 PATH；原根目录 Python 启动会在没有虚拟环境时尝试 uv |
| 业务表与存储桶 | 启动时 `go run ./cmd/migrate up`，并创建配置中的桶 | 原启动脚本没有对应的本机桶初始化和启动前迁移步骤 |
| 配置定位 | 脚本根据自身位置定位项目 `.env`；systemd 固定本机路径和用户 | shell 根据项目位置启动进程，不依赖本机 `deploy/local` 服务配置 |
| 应用日志 | `.run/*-systemd.log` | 根目录入口为 `.run/python-grpc.log`、`go-server.log`、`web.log`；`scripts/start-all.sh` 使用 `/tmp/lha-*.log` |
| 停止基础设施 | `stop-local.sh --all` 使用 Compose `stop`，本机 MinIO 另行停止 | 原入口使用 Compose `down`；均未指定删除持久卷 |
| 就绪核验 | 启动等待 Compose 和应用；`check-local.py` 逐项连接依赖 | 原启动/检查逻辑以服务端口、HTTP 和进程状态为主 |

两种方式使用相同的项目应用代码和 Compose 配置；本机脚本适配的是运行环境与进程生命周期，没有另写业务服务。不要混用两套启停命令，否则原脚本直接终止进程后，systemd 可能将其重新拉起。本机服务应使用本目录命令管理。

`check-local.py` 的成功仅表示依赖及应用可连接；真实模型回答、论文向量导入和检索效果仍需各自验证。
