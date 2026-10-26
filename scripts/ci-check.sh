#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# CI Gating 脚本（P2-5）
#
# 在 CI / pre-commit 阶段运行的快速检查。
# 覆盖 Go、Python、TypeScript 三方的基本约束。
#
# 用法:
#   bash scripts/ci-check.sh          # 全部检查
#   bash scripts/ci-check.sh --go     # 仅 Go
#   bash scripts/ci-check.sh --py     # 仅 Python
#   bash scripts/ci-check.sh --web    # 仅前端
#
# 门禁规则:
#   - Go:    go build ./... + go vet ./... 必须通过
#   - Python: 全部 .py 文件能通过 ast.parse()
#   - Web:   npx tsc --noEmit，无类型错误
#
# 修改记录:
#   2026-08-07  P2-5: 初始版本
# ──────────────────────────────────────────────────────────

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

red()   { echo -e "\033[31m$1\033[0m"; }
green() { echo -e "\033[32m$1\033[0m"; }

check_go() {
    echo "── Go build + vet ──"
    cd "$ROOT/go-backend"

    if go build ./... 2>&1; then
        green "  ✅ go build passed"
        ((PASS+=1))
    else
        red "  ❌ go build failed"
        ((FAIL+=1))
        return 1
    fi

    if go vet ./... 2>&1; then
        green "  ✅ go vet passed"
        ((PASS+=1))
    else
        red "  ❌ go vet failed"
        ((FAIL+=1))
        return 1
    fi
}

check_python() {
    echo "── Python 语法检查 ──"
    cd "$ROOT/python-ai"

    # 使用 venv 中的 python
    PYTHON=".venv/bin/python"
    if [ ! -x "$PYTHON" ]; then
        PYTHON="python3"
    fi

    errors=$($PYTHON -c "
import ast, glob, sys
errs = []
for f in glob.glob('app/**/*.py', recursive=True):
    try:
        with open(f) as fp:
            ast.parse(fp.read())
    except SyntaxError as e:
        errs.append(f'{f}: {e}')
if errs:
    for e in errs:
        print(f'  ❌ {e}')
    sys.exit(1)
print(f'  ✅ {sum(1 for _ in glob.glob(\"app/**/*.py\", recursive=True))} files OK')
" 2>&1)

    if [ $? -eq 0 ]; then
        echo "$errors"
        green "  ✅ python syntax passed"
        ((PASS+=1))
    else
        echo "$errors"
        red "  ❌ python syntax failed"
        ((FAIL+=1))
        return 1
    fi
}

check_web() {
    echo "── TypeScript 类型检查 ──"
    cd "$ROOT/web"

    # 检查 node_modules 是否存在，没有则 install
    if [ ! -d "node_modules" ]; then
        echo "  ⏳ npm install..."
        npm install --silent 2>&1 || true
    fi

    if npx tsc --noEmit 2>&1; then
        green "  ✅ tsc --noEmit passed"
        ((PASS+=1))
    else
        red "  ❌ tsc --noEmit failed"
        ((FAIL+=1))
        return 1
    fi
}

# ── 参数解析 ──
RUN_GO=true
RUN_PY=true
RUN_WEB=true

for arg in "$@"; do
    case "$arg" in
        --go)  RUN_PY=false; RUN_WEB=false ;;
        --py)  RUN_GO=false; RUN_WEB=false ;;
        --web) RUN_GO=false; RUN_PY=false ;;
    esac
done

# ── 运行 ──
echo "═══════════════════════════════════════════"
echo "  CI Gating Check"
echo "═══════════════════════════════════════════"
echo ""

$RUN_GO  && check_go  || true
$RUN_PY  && check_python || true
$RUN_WEB && check_web || true

echo ""
echo "───────────────────────────────────────────"
if [ $FAIL -eq 0 ]; then
    green "  ✅ 全部 $PASS 项检查通过"
    exit 0
else
    red "  ❌ $PASS passed, $FAIL failed"
    exit 1
fi
