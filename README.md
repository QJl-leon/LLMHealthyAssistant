# LLMHealthyAssistant · 个人健康顾问助手

基于大语言模型和检索增强生成（RAG）的健康信息助手。支持上传体检图片或 PDF、提取健康指标、结合知识库生成带证据的解读，并通过对话持续查看报告和健康档案。

项目采用 React 前端、Go 业务后端和 Python AI 服务的分层结构，业务后端通过 gRPC 调用 AI 服务，通过 SSE 向前端推送任务进展与生成结果。

## 主要功能

- **报告解析**：图片 OCR、视觉模型和 PDF 解析通道，支持体检指标结构化提取。
- **知识检索**：文档分块、向量检索、多路召回、RRF 融合、查询扩展及 Reranker 精排。
- **任务编排**：基于 LangGraph 协调视觉、检索、报告、对话和记忆代理，支持人工确认与任务恢复。
- **证据与质量控制**：证据来源整理、冲突检测、报告校验，以及检索和生成评测。
- **业务能力**：账号认证、上传归属校验、报告与健康档案管理、记忆生命周期管理。
- **扩展与观测**：MCP / A2A 接口、OpenTelemetry、Prometheus 及性能诊断工具。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19、TypeScript、Vite |
| 业务后端 | Go、Gin、gRPC、JWT |
| AI 服务 | Python、LangGraph、Celery、MCP |
| 数据与存储 | PostgreSQL 16、Milvus 2.5、Redis 7、MinIO |
| 部署与观测 | Docker Compose、Nginx、OpenTelemetry、Jaeger |

## 目录结构

```text
LLMHealthyAssistant/
├── contracts/          # Protobuf 契约与代码生成配置
├── go-backend/         # HTTP API、认证、业务服务与数据库迁移
├── python-ai/          # AI 编排、解析、检索、记忆、评测与测试
├── web/                # React 前端
├── deploy/             # 基础设施、配置模板、部署和性能工具
├── scripts/            # 本地运行与实验辅助脚本
├── lecture/            # RAG 自学实验资料
├── Makefile            # 开发、测试与数据初始化入口
├── start.sh            # 启动基础设施和应用
├── stop.sh             # 停止服务
└── deploy/env.example  # 环境配置模板，不包含真实云密钥
```

## 环境要求

- Go 1.25 或以上（以 `go-backend/go.mod` 为准）。
- Python 3.11～3.13，以及 uv。
- Node.js 22.12 或以上，以及 npm；Makefile 的前端命令使用 pnpm。
- Docker Engine 与 Docker Compose 插件。
- Bash；一键启动脚本还使用 `curl`、`lsof` 和 `pgrep`。

以下命令均从项目根目录开始执行。基础设施需要预留足够内存，Milvus 的当前容器内存上限为 6 GiB。

## 快速开始

### 1. 准备环境配置

```bash
cp deploy/env.example .env
```

编辑 `.env`，填写实际使用的模型服务凭据：

| 配置 | 用途 |
| --- | --- |
| `DEEPSEEK_API_KEY`、`LLM_MODEL` | 对话与报告生成 |
| `DASHSCOPE_API_KEY`、`VLM_MODEL` | 视觉理解及默认 OCR 通道 |
| `SILICONFLOW_API_KEY`、`EMBEDDING_MODEL`、`EMBEDDING_DIM` | 向量化及默认精排服务 |
| `RERANKER_PROVIDER`、`RERANKER_MODEL` | 精排服务选择 |
| `DATABASE_URL`、`REDIS_URL`、`MILVUS_HOST` | 数据库、缓存与向量库连接 |
| `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` | 对象存储 |
| `JWT_SECRET`、`AUTH_REQUIRED` | 登录认证 |

其他 OCR 或精排提供商按所选通道配置；完整字段见 [环境配置模板](deploy/env.example) 和 [精排服务说明](python-ai/RERANKER_SETUP.md)。更换 Embedding 模型或维度后，需要重建对应索引。

模板中的数据库和 MinIO 密码用于本地开发，并与 Compose 默认值对应。对外部署时应同步修改基础设施与应用凭据，设置随机 `JWT_SECRET` 并启用 `AUTH_REQUIRED=true`。模型请求及索引向量化可能产生服务商费用。

### 2. 安装依赖

```bash
(cd python-ai && uv sync --frozen --extra dev)
(cd web && npm ci)
(cd go-backend && go mod download)
```

仓库保留依赖锁文件，便于复现安装。

### 3. 启动基础设施并初始化数据

```bash
make up
docker compose -f deploy/docker-compose.yml ps
```

等待 PostgreSQL、Milvus、Redis 和 MinIO 就绪，再执行：

```bash
make migrate
(cd python-ai && uv run --env-file ../.env python -m app.factory.cli init)
(cd python-ai && uv run --env-file ../.env python -m app.factory.cli seed)
(cd python-ai && uv run --env-file ../.env python -m app.factory.cli version publish kv_demo_001)
(cd python-ai && uv run --env-file ../.env python -m app.retrieval.index_builder --rebuild --version kv_demo_001)
```

上述步骤针对首次运行，初始化内置指标、指南和案例语料并建立检索索引。`--rebuild` 会重建索引，请在已有数据的环境中按需执行。论文压缩包、真实体检报告及已有数据库内容不随仓库分发。

### 4. 启动应用

```bash
bash start.sh
bash check.sh
```

也可以分别在三个终端运行，便于调试：

```bash
make dev-py
make dev-go
(cd web && npm run dev)
```

| 服务 | 默认地址 |
| --- | --- |
| 前端 | http://localhost:5173 |
| Go 健康检查 | http://localhost:8080/healthz |
| Python gRPC | localhost:50057 |
| MinIO 控制台 | http://localhost:9001 |
| Jaeger（执行 `make up-obs` 后） | http://localhost:16686 |

前端开发服务器通过 Vite 将 `/api`、`/uploads` 和 `/healthz` 代理到 Go 后端。健康检查响应不能替代真实模型调用与检索效果验证。

停止应用使用 `bash stop.sh`；连同基础设施一起停止使用 `bash stop.sh --all`。`make down` 仅停止 Compose 基础设施，默认保留持久卷。

## 开发与验证

```bash
# Go 与 Python 测试
make test

# 前端检查与构建
(cd web && npm run lint && npm run build)

# 健康域评测门禁，需要相应数据和模型配置
make eval

# 修改 Protobuf 契约后重新生成代码
make proto

# 可选：独立启动 MCP / A2A 接口
make dev-mcp

# 可选：启动后台任务 worker
make dev-worker
```

`make proto` 需要安装 `protoc-gen-go`、`protoc-gen-go-grpc`，并准备 Python 开发依赖。部分测试与评测依赖数据库、向量库或外部模型 API；具体要求见对应测试和评测脚本。

进一步阅读：[RAG 实验手册](lecture/RAG自学实验手册.md)、[本地运行脚本](scripts/local/README.md)、[生产部署说明](deploy/production/README.md)、[性能测试说明](deploy/performance/README.md)。本机 systemd 脚本包含特定目录与用户设置，迁移机器时需调整服务文件。

## 环境配置与 Git 管理

- 真实配置保存在本地 `.env` 中；提交配置变更时，只更新脱敏后的 `deploy/env.example`。
- `.gitignore` 排除各目录下的环境文件、证书私钥、本机部署配置、`.run/`、上传数据、日志、虚拟环境、依赖目录及构建产物。
- 源码中的公开配置、依赖锁文件、合成测试夹具和脱敏配置示例继续纳入版本控制。
- 提交前可用 `git status --short` 检查文件列表，用 `git check-ignore -v .env` 确认配置文件被忽略。
- `.gitignore` 不会自动移除已被 Git 跟踪的文件。如果以后误提交凭据，应立即更换凭据，并单独处理已有提交历史。

本项目用于健康信息辅助与技术实验，生成内容不能代替专业医疗诊断。
