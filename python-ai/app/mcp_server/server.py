from __future__ import annotations
import logging
import os
from typing import Any
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from mcp.server.mcpserver import MCPServer
from app.mcp_server import tools as tool_impl
logger = logging.getLogger(__name__)

def _check_bearer(request: Request, env_key: str='PROTOCOL_API_TOKEN') -> Response | None:
    expected = os.getenv(env_key) or os.getenv('A2A_API_TOKEN') or os.getenv('MCP_API_TOKEN') or ''
    if not expected:
        return None
    auth = request.headers.get('authorization') or ''
    if auth == f'Bearer {expected}':
        return None
    return JSONResponse({'error': 'unauthorized', 'message': '需要 Authorization: Bearer <token>'}, status_code=401)

def create_mcp_server() -> MCPServer:
    mcp = MCPServer(name='lha-health-evidence', title='健康证据 MCP', description='只读健康证据能力：双库检索（健康指南库 / 病历案例库）、体检指标目录与参考区间、个人指标趋势、引用校验。不开放数据库直连。', version='0.4.0', instructions='优先调用 search_evidence / get_metric_profile / get_metric_trend；生成结论文本后用 validate_claims 校验；证据不足时明确拒答，不要编造参考区间或诊断结论。')

    @mcp.tool(description='健康证据多通道检索（指标目录 / BM25 / Dense，双库融合）')
    def search_evidence(query: str, channels: list[str] | None=None, knowledge_version: str | None=None, top_k: int=10) -> str:
        return tool_impl.search_evidence(query=query, channels=channels, knowledge_version=knowledge_version, top_k=top_k)

    @mcp.tool(description='体检指标目录档案（指标编码 / 参考区间 / 异常提示）')
    def get_metric_profile(metric_code: str='', name: str='') -> str:
        return tool_impl.get_metric_profile(metric_code=metric_code, name=name)

    @mcp.tool(description='个人指标历史趋势（首末值与 rising/falling/stable 方向）')
    def get_metric_trend(user_id: str, metric_code: str) -> str:
        return tool_impl.get_metric_trend(user_id=user_id, metric_code=metric_code)

    @mcp.tool(description='引用校验：存在性 + 可选专名；可附带 evidence 做严格拒答判断')
    def validate_claims(claims_json: str) -> str:
        return tool_impl.validate_claims(claims_json)

    @mcp.resource('evidence://recent', description='最近解析入库的证据摘要')
    def evidence_recent() -> str:
        return tool_impl.read_evidence_recent()

    @mcp.resource('sources://catalog', description='已批准的可信来源目录')
    def sources_catalog() -> str:
        return tool_impl.read_sources_catalog()

    @mcp.prompt(description='健康咨询模板 — 针对一项健康诉求给出可核验的运动与生活方式建议')
    def health_consult(concern: str) -> str:
        return f'请针对健康诉求「{concern}」给出完整建议，包括：\n1. 指标解读: 相关体检指标的含义与参考区间\n2. 指标趋势: 该指标的历史变化方向与意义\n3. 干预建议: 运动与生活方式建议（具体、可执行）\n4. 随访建议: 需要复查的项目与时间间隔\n\n每条结论必须引用具体来源（指南条目 / 案例编号），证据不足时明确说明。'

    @mcp.custom_route('/healthz', methods=['GET'])
    async def healthz(_request: Request) -> Response:
        return JSONResponse({'ok': True, 'service': 'lha-mcp-a2a'})

    @mcp.custom_route('/a2a/agent-card', methods=['GET'])
    async def agent_card(request: Request) -> Response:
        denied = _check_bearer(request)
        if denied:
            return denied
        from app.a2a.agent_card import get_agent_card
        return JSONResponse(get_agent_card())

    @mcp.custom_route('/.well-known/agent.json', methods=['GET'])
    async def well_known_agent(request: Request) -> Response:
        from app.a2a.agent_card import get_agent_card
        return JSONResponse(get_agent_card())

    @mcp.custom_route('/a2a/tasks', methods=['POST'])
    async def a2a_submit(request: Request) -> Response:
        denied = _check_bearer(request)
        if denied:
            return denied
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse({'error': 'invalid_json'}, status_code=400)
        from app.a2a.agent_card import submit_task
        images = body.get('images') or []
        norm_images = []
        for img in images:
            if isinstance(img, str):
                norm_images.append({'key': '', 'position': 'exam_report', 'presigned_url': img})
            elif isinstance(img, dict):
                norm_images.append({'key': img.get('key', ''), 'position': img.get('position', 'exam_report'), 'presigned_url': img.get('presigned_url') or img.get('url') or ''})
        task_id = submit_task(images=norm_images, query=str(body.get('query') or body.get('message') or body.get('concern') or ''), user_id=str(body.get('user_id') or request.headers.get('x-user-id') or 'a2a-user'))
        return JSONResponse({'task_id': task_id, 'status': 'pending', 'status_url': f'/a2a/tasks/{task_id}', 'result_url': f'/a2a/tasks/{task_id}/result'}, status_code=202)

    @mcp.custom_route('/a2a/tasks', methods=['GET'])
    async def a2a_tasks_help(_request: Request) -> Response:
        return JSONResponse({'usage': 'POST /a2a/tasks with JSON {query|concern|images, user_id?}', 'example': {'query': '帮我看看血脂高该怎么运动', 'concern': 'LDL-C 偏高，想改善血脂'}})

    @mcp.custom_route('/a2a/tasks/{task_id}', methods=['GET'])
    async def a2a_status(request: Request) -> Response:
        denied = _check_bearer(request)
        if denied:
            return denied
        from app.a2a.agent_card import get_task_status
        task_id = request.path_params['task_id']
        data = get_task_status(task_id)
        code = 404 if data.get('status') == 'not_found' else 200
        return JSONResponse(data, status_code=code)

    @mcp.custom_route('/a2a/tasks/{task_id}/result', methods=['GET'])
    async def a2a_result(request: Request) -> Response:
        denied = _check_bearer(request)
        if denied:
            return denied
        from app.a2a.agent_card import get_task_result
        task_id = request.path_params['task_id']
        data = get_task_result(task_id)
        code = 404 if data.get('status') == 'not_found' else 200
        return JSONResponse(data, status_code=code)
    return mcp

def run_server(host: str | None=None, port: int | None=None) -> None:
    host = host or os.getenv('MCP_HOST', '127.0.0.1')
    port = int(port or os.getenv('MCP_PORT', '9002'))
    mcp = create_mcp_server()
    logger.info('🚀 MCP Streamable HTTP + A2A 就绪 http://%s:%d/mcp', host, port)
    logger.info('   Agent Card: http://%s:%d/a2a/agent-card', host, port)
    mcp.run(transport='streamable-http', host=host, port=port, streamable_http_path='/mcp', stateless_http=True)
