#!/bin/bash
# ============================================================
# 一键启动全栈服务
# 用法: bash scripts/start-all.sh
#
# 启动顺序:
#   1. 基础设施 (docker compose)
#   2. Python AI gRPC (:50057)
#   3. Go 业务后端 (:8080)
#   4. Vite 前端 (:5173)
#
# 停止: bash scripts/stop-all.sh
# 测试: bash scripts/test-e2e.sh
# ============================================================
set -e

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
echo "🔬 个人健康顾问助手 — 全栈启动"
echo "   项目路径: $PROJ"
echo ""

# ── 1. 基础设施 ──
echo "=== 1/4 基础设施 ==="
if docker compose -f "$PROJ/deploy/docker-compose.yml" ps 2>/dev/null | grep -q "Up"; then
    echo "   ✅ 已运行"
else
    docker compose -f "$PROJ/deploy/docker-compose.yml" up -d
    echo "   ✅ 已启动"
fi

# ── 2. Python AI gRPC ──
echo "=== 2/4 Python AI gRPC (:50057) ==="
if lsof -i :50057 -sTCP:LISTEN -P 2>/dev/null | grep -q LISTEN; then
    echo "   ✅ 已运行"
else
    cd "$PROJ/python-ai"
    PYTHONPATH="$PROJ/python-ai" nohup .venv/bin/python -m app.server > /tmp/lha-python.log 2>&1 &
    sleep 3
    if lsof -i :50057 -sTCP:LISTEN -P 2>/dev/null | grep -q LISTEN; then
        echo "   ✅ 已启动 (PID $!)"
    else
        echo "   ❌ 启动失败，查看 /tmp/lha-python.log"
        exit 1
    fi
fi

# ── 3. Go 业务后端 ──
echo "=== 3/4 Go 后端 (:8080) ==="
if lsof -i :8080 -sTCP:LISTEN -P 2>/dev/null | grep -q LISTEN; then
    echo "   ✅ 已运行"
else
    cd "$PROJ/go-backend"
    go build -o /tmp/lha-go ./cmd/server 2>/dev/null
    nohup /tmp/lha-go > /tmp/lha-go.log 2>&1 &
    sleep 3
    if curl -s --max-time 2 http://localhost:8080/healthz | grep -q '"ok"'; then
        echo "   ✅ 已启动 (PID $!)"
    else
        echo "   ❌ 启动失败，查看 /tmp/lha-go.log"
        exit 1
    fi
fi

# ── 4. Vite 前端 ──
echo "=== 4/4 前端 (:5173) ==="
if lsof -i :5173 -sTCP:LISTEN -P 2>/dev/null | grep -q LISTEN; then
    echo "   ✅ 已运行"
else
    cd "$PROJ/web"
    nohup npx vite --host > /tmp/lha-vite.log 2>&1 &
    sleep 3
    if curl -s --max-time 3 http://localhost:5173/ 2>/dev/null | grep -q "root"; then
        echo "   ✅ 已启动 (PID $!)"
    else
        echo "   ⚠️ 启动可能失败，查看 /tmp/lha-vite.log"
    fi
fi

echo ""
echo "=============================================="
echo "🎉 全栈启动完成！"
echo ""
echo "   前端页面:  http://localhost:5173"
echo "   API 文档:  http://localhost:8080/healthz"
echo "   Python AI: localhost:50057"
echo ""
echo "   运行测试:  bash scripts/test-e2e.sh"
echo "   停止服务:  bash scripts/stop-all.sh"
echo "=============================================="
