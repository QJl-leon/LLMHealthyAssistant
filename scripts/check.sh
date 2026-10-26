#!/bin/bash
# ============================================================
# 全栈健康检查
# 用法: bash scripts/check.sh
# ============================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

pass()  { echo -e "  ${GREEN}🟢${NC} $1"; }
fail()  { echo -e "  ${RED}🔴${NC} $1"; }
warn()  { echo -e "  ${YELLOW}🟡${NC} $1"; }

echo "🔍 个人健康顾问助手 — 健康检查"
echo ""

# ── 1. Docker 基础设施 ──
echo "── 基础设施 ──"
for svc in lha-postgres lha-redis lha-minio lha-milvus; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$svc"; then
        pass "$svc"
    else
        fail "$svc 未运行"
    fi
done

# ── 2. PostgreSQL 连通性 ──
echo ""
echo "── 数据库连通性 ──"
DB_URL="${DATABASE_URL:-postgresql://lha:lha_dev@localhost:5432/lha?sslmode=disable}"
if command -v psql >/dev/null 2>&1; then
    if psql "$DB_URL" -c "SELECT 1" >/dev/null 2>&1; then
        pass "PostgreSQL 可连接"
    else
        fail "PostgreSQL 连接失败"
    fi
else
    # 用 Python 测
    if python3 -c "
import psycopg2
psycopg2.connect('$DB_URL')
print('ok')
" 2>/dev/null | grep -q ok; then
        pass "PostgreSQL 可连接"
    else
        fail "PostgreSQL 连接失败"
    fi
fi

# ── 3. Python gRPC (:50057) ──
echo ""
echo "── 应用服务 ──"
if lsof -ti :50057 >/dev/null 2>&1; then
    pass "Python gRPC (:50057)"
else
    fail "Python gRPC (:50057) 未运行"
fi

# ── 4. Go 后端 (:8080) ──
if curl -sf --max-time 3 http://localhost:8080/healthz >/dev/null 2>&1; then
    pass "Go 后端 (:8080)"
else
    fail "Go 后端 (:8080) 未响应"
fi

# ── 5. 前端 (:5173) ──
if curl -sf --max-time 3 http://localhost:5173/ >/dev/null 2>&1; then
    pass "前端 (:5173)"
else
    fail "前端 (:5173) 未响应"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
