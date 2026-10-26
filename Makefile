.PHONY: up down up-obs dev-go dev-py dev-worker dev-mcp web migrate test eval tunnel nuke

COMPOSE_FILE := deploy/docker-compose.yml

# ── 基础设施 ────────────────────────────────────────────
up:
	docker compose -f $(COMPOSE_FILE) up -d
	@echo "✅ 基础设施已启动 | make down 停止 | make up-obs 带 Jaeger"

down:
	docker compose -f $(COMPOSE_FILE) down

up-obs:
	docker compose -f $(COMPOSE_FILE) --profile obs up -d
	@echo "✅ 基础设施 + Jaeger 已启动 | http://localhost:16686"

# ── 开发服务 ────────────────────────────────────────────
dev-go:
	cd go-backend && go run ./cmd/server

dev-py:
	cd python-ai && uv run python -m app.server

dev-mcp:
	cd python-ai && uv run python -m app.mcp_server
	@echo "MCP/A2A → http://127.0.0.1:9002/mcp | Agent Card /a2a/agent-card"

dev-worker:
	cd python-ai && uv run celery -A workers.app worker -l info

web:
	cd web && pnpm dev

# ── 数据 ────────────────────────────────────────────────
migrate:
	cd go-backend && go run ./cmd/migrate up

# ── 契约（proto 变更后重新生成两端代码）─────────────────
# 依赖: python grpcio-tools（protoc 本体）+ ~/go/bin/protoc-gen-go{,-grpc}
proto:
	cd python-ai && uv run python -m grpc_tools.protoc \
		-I ../contracts/proto \
		--python_out=app/server --grpc_python_out=app/server \
		research/v1/research.proto
	cd python-ai && sed -i 's/from research\.v1 import research_pb2/from app.server.research.v1 import research_pb2/' \
		app/server/research/v1/research_pb2_grpc.py
	cd python-ai && PATH="$$HOME/go/bin:$$PATH" uv run python -m grpc_tools.protoc \
		-I ../contracts/proto \
		--go_out=../go-backend/internal/aiclient --go_opt=paths=source_relative \
		--go-grpc_out=../go-backend/internal/aiclient --go-grpc_opt=paths=source_relative \
		research/v1/research.proto
	@echo "✅ proto 两端代码已重新生成"

# ── 测试与评测 ──────────────────────────────────────────
test:
	cd go-backend && go test ./...
	cd python-ai && uv run pytest
	@echo "🧪 双端测试完成"

# 健康域评测门禁：行为切片（9 类）+ 检索质量 + 生成质量，通过率 <0.8 即红
eval:
	cd python-ai && uv run python -m app.eval.run --gate

# ── 样例数据（健康域：指标目录 + 健康指南 + 病历案例）──────
ingest-sample:
	cd python-ai && uv run python -m app.factory.cli ingest --sample

# ── 对外演示 ────────────────────────────────────────────
tunnel:
	cloudflared tunnel run lha-demo

# ── 完全还原 ────────────────────────────────────────────
nuke:
	docker compose -f $(COMPOSE_FILE) down -v
	rm -rf go-backend/tmp python-ai/.venv web/node_modules
	rm -rf data/
	@echo "🧹 完全还原，宿主机干干净净"
