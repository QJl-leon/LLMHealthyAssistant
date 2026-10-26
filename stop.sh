#!/bin/bash
# ============================================================
# 停止全栈服务
# 用法: bash stop.sh          停止 Python / Go / 前端（保留基础设施）
#       bash stop.sh --all    连同 Docker 基础设施一起停止
#
# 策略: 优先按 pid 文件停（精确），回退按端口停（兜底）；
#       不用 pkill -f 模糊匹配，避免误杀无关进程。
# ============================================================
set -e

PROJ="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$PROJ/.run"

stop_one() {  # $1=名称 $2=pid文件 $3=端口
    local name=$1 pidfile=$2 port=$3
    local pids=""
    local pid=""
    [ -f "$pidfile" ] && pid=$(cat "$pidfile" 2>/dev/null || true)
    # pid 文件失效（进程已死/被替换）→ 按端口兜底；端口上可能挂多个进程
    # （gRPC SO_REUSEPORT 允许多进程同绑 50057，2026-09-24 踩过孤儿进程坑），全部列出
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && pids="$pids $pid"
    # 去重
    pids=$(echo $pids | tr ' ' '\n' | sort -u | grep -v '^$' || true)
    if [ -z "$pids" ]; then
        echo "   ⏭️  $name 未运行"
        rm -f "$pidfile"; return 0
    fi
    for p in $pids; do kill "$p" 2>/dev/null || true; done
    # 最多等 5s 优雅退出，超时强杀
    for _ in $(seq 1 5); do
        local alive=""
        for p in $pids; do kill -0 "$p" 2>/dev/null && alive="$alive $p"; done
        [ -z "$alive" ] && break; sleep 1
    done
    for p in $pids; do kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null || true; done
    echo "   ✅ $name 已停止 (PID:$pids)"
    rm -f "$pidfile"
}

echo "🛑 停止全栈服务..."

stop_one "Python gRPC" "$RUN_DIR/python-grpc.pid" 50057
stop_one "Go 后端"     "$RUN_DIR/go-server.pid"   8080
stop_one "前端 Vite"   "$RUN_DIR/web.pid"         5173

# ── 基础设施 ──
if [ "$1" = "--all" ]; then
    docker compose -f "$PROJ/deploy/docker-compose.yml" down
    echo "   ✅ 基础设施已停止"
else
    echo "   💡 基础设施保持运行（加 --all 一起停）"
fi

echo "✅ 完成"
