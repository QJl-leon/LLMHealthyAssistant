#!/bin/bash
# ============================================================
# 重启全栈服务（stop → start）
# 用法: bash restart.sh          重启三端服务（基础设施保留）
#       bash restart.sh --all    基础设施也重启
# ============================================================
set -e
PROJ="$(cd "$(dirname "$0")" && pwd)"

bash "$PROJ/stop.sh" "$@"
echo ""
bash "$PROJ/start.sh"
