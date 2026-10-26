#!/bin/bash
# ============================================================
# 一键启动全栈（幂等：已运行的组件自动跳过）
# 用法: bash start.sh          启动全部（基础设施 + 三端服务）
#       bash start.sh --infra  只启动基础设施（docker compose）
#
# 启动顺序: 基础设施 → Python gRPC(:50057) → Go(:8080) → 前端(:5173)
# 对应停止: bash stop.sh | 重启: bash restart.sh | 状态: bash check.sh
# ============================================================
set -e

PROJ="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$PROJ/.run"; mkdir -p "$RUN_DIR"

wait_port() {  # $1=端口 $2=最长等待秒数
    local port=$1 secs=${2:-30}
    for _ in $(seq 1 "$secs"); do
        lsof -ti :"$port" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

echo "🩺 个人健康顾问助手 — 全栈启动"
echo "   项目: $PROJ"
echo ""

# ── 1. 基础设施（docker compose，幂等）──
echo "── 1/4 基础设施 ──"
docker compose -f "$PROJ/deploy/docker-compose.yml" up -d
echo "   ✅ 基础设施已就绪"
[ "$1" = "--infra" ] && exit 0

# ── 2. Python AI gRPC (:50057) ──
echo "── 2/4 Python AI gRPC (:50057) ──"
if wait_port 50057 1; then
    echo "   ⏭️  已在运行 (PID $(lsof -ti :50057 | head -1))"
else
    cd "$PROJ/python-ai"
    PY=".venv/bin/python"; [ -x "$PY" ] || PY="uv run python"
    # exec 确保 subshell 直接替换为 python 进程——否则 $! 记录的是中间
    # shell 的 PID，kill pid 文件杀不死真正的 python（2026-09-24 踩过：
    # 三次"重启"留下三个孤儿进程，SO_REUSEPORT 多进程分食 50057，配置新旧混杂）
    PYTHONPATH="$PROJ/python-ai" nohup $PY -m app.server \
        > "$RUN_DIR/python-grpc.log" 2>&1 &
    echo $! > "$RUN_DIR/python-grpc.pid"
    # 校正：$! 可能是中间 shell，取真实 python PID
    REAL_PID=$(pgrep -f "python.* -m app.server" | head -1)
    [ -n "$REAL_PID" ] && echo "$REAL_PID" > "$RUN_DIR/python-grpc.pid"
    if wait_port 50057 60; then
        echo "   ✅ 已启动 (PID $(cat "$RUN_DIR/python-grpc.pid"))"
    else
        echo "   ❌ 启动失败，日志: $RUN_DIR/python-grpc.log"; exit 1
    fi
fi

# ── 3. Go 业务后端 (:8080) ──
echo "── 3/4 Go 后端 (:8080) ──"
if curl -sf --max-time 2 http://localhost:8080/healthz >/dev/null 2>&1; then
    echo "   ⏭️  已在运行 (PID $(lsof -ti :8080 | head -1))"
else
    cd "$PROJ/go-backend"
    echo "   编译中..."
    go build -o "$RUN_DIR/lha-go" ./cmd/server
    nohup "$RUN_DIR/lha-go" > "$RUN_DIR/go-server.log" 2>&1 &
    echo $! > "$RUN_DIR/go-server.pid"
    for _ in $(seq 1 30); do
        curl -sf --max-time 2 http://localhost:8080/healthz >/dev/null 2>&1 && break
        sleep 1
    done
    if curl -sf --max-time 2 http://localhost:8080/healthz >/dev/null 2>&1; then
        echo "   ✅ 已启动 (PID $(cat "$RUN_DIR/go-server.pid"))"
    else
        echo "   ❌ 启动失败，日志: $RUN_DIR/go-server.log"; exit 1
    fi
fi

# ── 4. 前端 Vite (:5173) ──
echo "── 4/4 前端 (:5173) ──"
if wait_port 5173 1; then
    echo "   ⏭️  已在运行 (PID $(lsof -ti :5173 | head -1))"
else
    cd "$PROJ/web"
    nohup npx vite --host > "$RUN_DIR/web.log" 2>&1 &
    echo $! > "$RUN_DIR/web.pid"
    if wait_port 5173 30; then
        echo "   ✅ 已启动 (PID $(cat "$RUN_DIR/web.pid"))"
    else
        echo "   ⚠️ 启动可能失败，日志: $RUN_DIR/web.log"
    fi
fi

echo ""
echo "=============================================="
echo "🎉 启动完成"
echo "   前端:      http://localhost:5173"
echo "   Go API:    http://localhost:8080/healthz"
echo "   gRPC:      localhost:50057"
echo "   状态检查:  bash check.sh"
echo "   停止服务:  bash stop.sh [--all 连同基础设施]"
echo "=============================================="
