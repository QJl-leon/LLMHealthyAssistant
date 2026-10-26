#!/bin/bash
# ============================================================
# 停止全部服务
# 用法: bash scripts/stop-all.sh [--all]
#   --all  同时停止 Docker 基础设施
# ============================================================
set -e

PROJ="$(cd "$(dirname "$0")/.." && pwd)"

echo "🛑 停止全栈服务..."

# ── Python gRPC (:50057) ──
if lsof -ti :50057 >/dev/null 2>&1; then
    lsof -ti :50057 | xargs kill 2>/dev/null
    echo "   ✅ Python gRPC 已停止"
else
    echo "   ⏭️  Python gRPC 未运行"
fi

# ── Go 后端 (:8080) ──
if pgrep -f "lha-go" >/dev/null 2>&1; then
    pkill -f "lha-go" 2>/dev/null
    echo "   ✅ Go 后端 已停止"
else
    echo "   ⏭️  Go 后端 未运行"
fi

# ── Vite 前端 (:5173) ──
if pgrep -f "vite" >/dev/null 2>&1; then
    pkill -f "vite" 2>/dev/null
    echo "   ✅ Vite 前端 已停止"
else
    echo "   ⏭️  Vite 前端 未运行"
fi

# ── 基础设施（Docker） ──
if [ "$1" = "--all" ]; then
    docker compose -f "$PROJ/deploy/docker-compose.yml" down 2>/dev/null
    echo "   ✅ 基础设施 已停止"
else
    echo "   💡 基础设施保持运行 (加 --all 参数一起停)"
fi

echo "✅ 完成"
