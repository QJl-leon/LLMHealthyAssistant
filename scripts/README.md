# 脚本分类

| 目录 / 文件 | 适用范围 |
| --- | --- |
| [`papers500/`](papers500/README.md) | 500 篇论文的解析、PDFium 补解析、核验、报告、六策略分块与向量导入 |
| [`local/`](local/README.md) | 当前 Ubuntu 本机的启动、停止、工具链、依赖检查和 MinIO 配套脚本；说明与项目原始入口的区别 |
| `start-all.sh`、`stop-all.sh` | 项目原有通用启动/停止入口 |
| `check.sh`、`ci-check.sh`、`test-e2e.sh` | 项目原有检查、CI 与端到端验证 |

项目根目录的 `start.sh`、`stop.sh`、`restart.sh`、`check.sh` 也属于原有通用入口。本机请按 `local/README.md` 使用 systemd 启停方式。
