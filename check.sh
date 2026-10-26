#!/bin/bash
# ============================================================
# 全栈健康检查（只读，无副作用）
# 用法: bash check.sh
# 检查: 基础设施容器 / 数据库连通 / 三端服务端口与端点 / 日志位置提示
# ============================================================

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
PROJ="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$PROJ/.run"

pass() { echo -e "  ${GREEN}🟢${NC} $1"; }
fail() { echo -e "  ${RED}🔴${NC} $1"; }
warn() { echo -e "  ${YELLOW}🟡${NC} $1"; }

echo "🔍 个人健康顾问助手 — 健康检查  ($(date '+%F %T'))"
echo ""

# ── 1. 基础设施容器 ──
echo "── 基础设施（docker compose）──"
for svc in lha-postgres lha-redis lha-minio lha-milvus; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$svc"; then
        state=$(docker ps --filter "name=$svc" --format '{{.Status}}')
        pass "$svc  ($state)"
    else
        fail "$svc 未运行"
    fi
done
docker ps --format '{{.Names}}' 2>/dev/null | grep -qx lha-otel-collector \
    && pass "lha-otel-collector" || warn "lha-otel-collector 未运行（可选）"

# ── 2. 数据库连通性（宿主机视角，与应用实际访问路径一致）──
echo ""
echo "── 数据库连通性 ──"
if docker exec lha-postgres pg_isready -U lha -d lha >/dev/null 2>&1; then
    pass "PostgreSQL 可连接"
else
    fail "PostgreSQL 连接失败"
fi
# Redis 必须从宿主机可达（应用走 localhost:6379；docker exec 只能验证容器内部，
# 端口发布失效时它仍会误报健康 —— 2026-09-23 踩过）
if python3 -c "
import socket, sys
s = socket.socket(); s.settimeout(2)
try: s.connect(('localhost', 6379))
except Exception: sys.exit(1)
finally: s.close()
" 2>/dev/null; then
    pass "Redis 可连接 (localhost:6379)"
else
    fail "Redis 宿主机不可达（应用缓存全部降级；docker compose up -d --force-recreate redis 可修复端口发布）"
fi

# Milvus 集合元数据（嵌入式 etcd 若未持久化，容器重建即清空 —— 2026-09-23 踩过）
if [ -d "$PROJ/python-ai" ]; then
    MILVUS_COLS=$(cd "$PROJ/python-ai" && timeout 20 uv run python -c "
from pymilvus import utility, connections
connections.connect(host='localhost', port='19530')
cols = [c for c in utility.list_collections() if not c.startswith('_')]
print(','.join(sorted(cols)))
" 2>/dev/null | tail -1)
    if [ -n "$MILVUS_COLS" ]; then
        pass "Milvus 集合: $MILVUS_COLS"
    else
        fail "Milvus 集合为空（索引元数据丢失？执行 python -m app.retrieval.index_builder --rebuild 重建）"
    fi
fi

# ── 3. Python AI gRPC (:50057) ──
echo ""
echo "── 应用服务 ──"
if lsof -ti :50057 >/dev/null 2>&1; then
    pass "Python gRPC (:50057)  PID $(lsof -ti :50057 | head -1 | tr '\n' ' ')"
else
    fail "Python gRPC (:50057) 未运行"
fi

# ── 4. Go 后端 (:8080) ──
if curl -sf --max-time 3 http://localhost:8080/healthz >/dev/null 2>&1; then
    pass "Go 后端 (:8080) /healthz 正常  PID $(lsof -ti :8080 | head -1)"
else
    fail "Go 后端 (:8080) 未响应"
fi

# ── 5. 前端 (:5173) ──
if curl -sf --max-time 3 http://localhost:5173/ >/dev/null 2>&1; then
    pass "前端 (:5173) Vite 正常  PID $(lsof -ti :5173 | head -1)"
else
    fail "前端 (:5173) 未响应"
fi

# ── 6. 端到端冒烟（真实 chat 链路，仅提示不自动调用）──
echo ""
echo "── 冒烟测试命令（可选手动执行）──"
echo "  curl -s -X POST http://localhost:8080/api/v1/chat \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"query\":\"减脂期三餐怎么安排\"}' | head -c 300"
echo ""
echo "── 服务日志 ──"
for f in python-grpc go-server web; do
    [ -f "$RUN_DIR/$f.log" ] && echo "  $RUN_DIR/$f.log  ($(du -h "$RUN_DIR/$f.log" | cut -f1))"
done
echo ""
echo "提示: bash start.sh 启动 | bash stop.sh 停止 | bash restart.sh 重启"
