import os
import sys
import time
import logging
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env'))
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    import grpc as _grpc
    from concurrent import futures as _futures
    from app.server.research.v1 import research_pb2_grpc as _rpc
    from app.server.grpc_server import ResearchServicer
    from app.server.memory_server import MemoryServicer
    from app.agents.checkpointer import get_checkpointer
    from app.agents import orchestrator as orch
    try:
        from app.memory.repository import init_memory_tables
        init_memory_tables()
        logger.info('   记忆表已就绪（含情景记忆）')
    except Exception as e:
        logger.warning('   记忆表初始化跳过: %s', e)
    saver = get_checkpointer()
    if saver:
        orch.orchestrator = orch.build_orchestrator(checkpointer=saver)
        logger.info('   编排图已重新编译（PG Checkpointer）')
    else:
        logger.info('   编排图使用内存 Checkpointer（中断后无法恢复）')
    port = int(os.getenv('GRPC_SERVER_PORT', '50057'))
    from app.observability.runtime import start, ObservedExecutor, ObservationInterceptor
    start()
    server = _grpc.server(ObservedExecutor(max_workers=10), interceptors=[ObservationInterceptor()])
    _rpc.add_ResearchServiceServicer_to_server(ResearchServicer(), server)
    _rpc.add_MemoryServiceServicer_to_server(MemoryServicer(), server)
    bound = server.add_insecure_port(f'localhost:{port}')
    server.start()
    logger.info('🚀 Python AI gRPC 服务就绪 port=%d bound=%d', port, bound)
    logger.info('   端点: SubmitTask / StreamTask / ResumeTask / CancelTask')
    logger.info('   MemoryService: ListMemory / CreateMemory / UpdateMemory / DeleteMemory / DeleteAllMemory / ConfirmMemory / ListMemoryAudit')
    if os.getenv('PROTOCOL_EMBEDDED', '').lower() in ('1', 'true', 'yes'):
        import threading

        def _run_protocol():
            try:
                from app.mcp_server.server import run_server
                run_server()
            except Exception as e:
                logger.error('MCP/A2A 嵌入启动失败: %s', e, exc_info=True)
        threading.Thread(target=_run_protocol, name='mcp-a2a', daemon=True).start()
        logger.info('   MCP/A2A 已请求嵌入启动（MCP_PORT=%s）', os.getenv('MCP_PORT', '9002'))
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info('服务已停止')
        from app.agents.checkpointer import close_checkpointer
        close_checkpointer()
        server.stop(grace=5)
if __name__ == '__main__':
    main()
