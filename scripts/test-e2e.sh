#!/bin/bash
# ============================================================
# 端到端测试脚本
# 用法: bash scripts/test-e2e.sh
#
# 测试内容:
#   1. healthz 健康检查
#   2. 创建研究任务
#   3. SSE 事件流（LangGraph 7 节点编排）
#   4. 前端页面可访问
#   5. 前端 Vite Proxy → Go 后端
# ============================================================
set -e

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

green() { echo -e "\033[32m$1\033[0m"; }
red()   { echo -e "\033[31m$1\033[0m"; }

check() {
    local name="$1"
    local cmd="$2"
    echo -n "  $name ... "
    if eval "$cmd" > /dev/null 2>&1; then
        green "✅"
        PASS=$((PASS + 1))
    else
        red "❌"
        FAIL=$((FAIL + 1))
    fi
}

echo "🧪 个人健康顾问助手 — 端到端测试"
echo ""

# ── 1. 基础设施 ──
echo "=== 基础设施 ==="
check "PostgreSQL :5432"  "lsof -i :5432 -sTCP:LISTEN -P | grep -q LISTEN"
check "Redis :6379"       "lsof -i :6379 -sTCP:LISTEN -P | grep -q LISTEN"
check "Milvus :19530"     "lsof -i :19530 -sTCP:LISTEN -P | grep -q LISTEN"
check "MinIO :9000"       "lsof -i :9000 -sTCP:LISTEN -P | grep -q LISTEN"

# ── 2. 服务进程 ──
echo ""
echo "=== 服务进程 ==="
check "Python gRPC :50057"  "lsof -i :50057 -sTCP:LISTEN -P | grep -q LISTEN"
check "Go 后端 :8080"       "curl -s --max-time 2 http://localhost:8080/healthz | grep -q '\"ok\"'"

# ── 3. Go REST API ──
echo ""
echo "=== Go REST API ==="
check "POST /api/v1/tasks" "
    TASK=\$(curl -s --max-time 5 -X POST http://localhost:8080/api/v1/tasks \
      -H 'Content-Type: application/json' \
      -d '{\"client_task_id\":\"e2e-test\",\"image_keys\":[]}')
    echo \"\$TASK\" | grep -q '\"code\":0'
"

# ── 4. SSE 事件流 ──
echo ""
echo "=== SSE 事件流（LangGraph 7 节点编排）==="

TASK=$(curl -s --max-time 5 -X POST http://localhost:8080/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{"client_task_id":"sse-check","image_keys":[]}')
TID=$(echo "$TASK" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['task_id'])")

SSE_OUTPUT=$(curl -s -N --max-time 8 "http://localhost:8080/api/v1/tasks/$TID/events" 2>/dev/null || true)

# 检查 6 个预期事件
check "StageChange: intake→observing"   "echo '$SSE_OUTPUT' | grep -q 'intake.*observing'"
check "StageChange: observing→retrieving" "echo '$SSE_OUTPUT' | grep -q 'observing.*retrieving'"
check "记忆注入完成"                      "echo '$SSE_OUTPUT' | grep -q '用户档案记忆'"
check "检索完成"                          "echo '$SSE_OUTPUT' | grep -q '检索完成'"
check "报告草稿完成"                      "echo '$SSE_OUTPUT' | grep -q '报告草稿完成'"
check "Result: published"                "echo '$SSE_OUTPUT' | grep -q 'published'"

# ── 5. 前端 ──
echo ""
echo "=== 前端 ==="
check "Vite :5173 可访问"    "curl -s --max-time 3 http://localhost:5173/ | grep -q 'root'"
check "Vite Proxy → Go API" "
    T2=\$(curl -s --max-time 5 -X POST http://localhost:5173/api/v1/tasks \
      -H 'Content-Type: application/json' \
      -d '{\"client_task_id\":\"vite-proxy\",\"image_keys\":[]}')
    echo \"\$T2\" | grep -q '\"code\":0'
"

# ── 6. 体检报告 → 指标解析 → 双库检索 ──
echo ""
echo "=== 体检报告 → 指标解析 → 双库检索 ==="
check "指标解析: metric_catalog 已装载" "
    PYTHONPATH=$PROJ/python-ai $PROJ/python-ai/.venv/bin/python -c \"
import sys,os; os.chdir('$PROJ/python-ai'); sys.path.insert(0,'.')
from app.factory.repository import list_metric_catalog
assert len(list_metric_catalog())>0
\" 2>/dev/null
"
check "双库分区: guideline + case" "
    PYTHONPATH=$PROJ/python-ai $PROJ/python-ai/.venv/bin/python -c \"
import sys,os; os.chdir('$PROJ/python-ai'); sys.path.insert(0,'.')
from app.retrieval.query_planner import QueryPlanner
p=QueryPlanner().plan([{'metric_name':'低密度脂蛋白','metric_code':'LDL_C','category':'血脂','flag':'high'}])
assert {'guideline','case'} <= set(p.source_types_used)
\" 2>/dev/null
"
check "运动建议走论文库（带引用依据）" "
    PYTHONPATH=$PROJ/python-ai $PROJ/python-ai/.venv/bin/python -c \"
import sys,os; os.chdir('$PROJ/python-ai'); sys.path.insert(0,'.')
from app.retrieval.query_planner import QueryPlanner
p=QueryPlanner().plan([], query='我想开始运动，应该怎么安排')
ex=[x for x in p.plans if x.category=='exercise']
assert ex and all('guideline' in x.source_types for x in ex)
\" 2>/dev/null
"

# ── 7. 引用校验 ──
echo ""
echo "=== 引用校验 ==="
check "正确引用通过" "
    PYTHONPATH=$PROJ/python-ai $PROJ/python-ai/.venv/bin/python -c \"
import sys,os; os.chdir('$PROJ/python-ai'); sys.path.insert(0,'.')
from app.evidence.validator import validate_claims_against_evidence
claims=[{'claim_id':'c1','type':'fact','text':'低密度脂蛋白胆固醇偏高需运动干预','evidence_ids':['ev_1']}]
ev=[{'evidence_id':'ev_1','quote':'低密度脂蛋白胆固醇 4.2 mmol/L 偏高'}]
assert validate_claims_against_evidence(claims, ev)==[]
\" 2>/dev/null
"
check "伪造引用被拦截" "
    PYTHONPATH=$PROJ/python-ai $PROJ/python-ai/.venv/bin/python -c \"
import sys,os; os.chdir('$PROJ/python-ai'); sys.path.insert(0,'.')
from app.evidence.validator import validate_claims_against_evidence
claims=[{'claim_id':'c1','type':'fact','text':'低密度脂蛋白胆固醇偏高需运动干预','evidence_ids':['ev_fake_001']}]
ev=[{'evidence_id':'ev_1','quote':'低密度脂蛋白胆固醇 4.2 mmol/L 偏高'}]
errors=validate_claims_against_evidence(claims, ev)
assert errors and errors[0]['error_code']=='CITATION_MISMATCH'
\" 2>/dev/null
"

# ── 总结 ──
echo ""
echo "=============================================="
echo "  通过: $PASS / $((PASS + FAIL))"
if [ "$FAIL" -eq 0 ]; then
    green "  🎉 全部测试通过！"
else
    red "  ❌ $FAIL 项测试失败"
    exit 1
fi
echo "=============================================="
