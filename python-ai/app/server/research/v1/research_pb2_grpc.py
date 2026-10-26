import grpc
import warnings
from app.server.research.v1 import research_pb2 as research_dot_v1_dot_research__pb2
GRPC_GENERATED_VERSION = '1.83.0'
GRPC_VERSION = grpc.__version__
_version_not_supported = False
try:
    from grpc._utilities import first_version_is_lower
    _version_not_supported = first_version_is_lower(GRPC_VERSION, GRPC_GENERATED_VERSION)
except ImportError:
    _version_not_supported = True
if _version_not_supported:
    raise RuntimeError(f'The grpc package installed is at version {GRPC_VERSION},' + ' but the generated code in research/v1/research_pb2_grpc.py depends on' + f' grpcio>={GRPC_GENERATED_VERSION}.' + f' Please upgrade your grpc module to grpcio>={GRPC_GENERATED_VERSION}' + f' or downgrade your generated code using grpcio-tools<={GRPC_VERSION}.')

class ResearchServiceStub:

    def __init__(self, channel):
        self.SubmitTask = channel.unary_unary('/research.v1.ResearchService/SubmitTask', request_serializer=research_dot_v1_dot_research__pb2.SubmitTaskRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.SubmitTaskResponse.FromString, _registered_method=True)
        self.StreamTask = channel.unary_stream('/research.v1.ResearchService/StreamTask', request_serializer=research_dot_v1_dot_research__pb2.StreamTaskRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.TaskEvent.FromString, _registered_method=True)
        self.ResumeTask = channel.unary_unary('/research.v1.ResearchService/ResumeTask', request_serializer=research_dot_v1_dot_research__pb2.ResumeTaskRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.ResumeTaskResponse.FromString, _registered_method=True)
        self.CancelTask = channel.unary_unary('/research.v1.ResearchService/CancelTask', request_serializer=research_dot_v1_dot_research__pb2.CancelTaskRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.CancelTaskResponse.FromString, _registered_method=True)
        self.GetTaskCost = channel.unary_unary('/research.v1.ResearchService/GetTaskCost', request_serializer=research_dot_v1_dot_research__pb2.GetTaskCostRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.GetTaskCostResponse.FromString, _registered_method=True)
        self.Chat = channel.unary_unary('/research.v1.ResearchService/Chat', request_serializer=research_dot_v1_dot_research__pb2.ChatRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.ChatResponse.FromString, _registered_method=True)

class ResearchServiceServicer:

    def SubmitTask(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def StreamTask(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ResumeTask(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CancelTask(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def GetTaskCost(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def Chat(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

def add_ResearchServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {'SubmitTask': grpc.unary_unary_rpc_method_handler(servicer.SubmitTask, request_deserializer=research_dot_v1_dot_research__pb2.SubmitTaskRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.SubmitTaskResponse.SerializeToString), 'StreamTask': grpc.unary_stream_rpc_method_handler(servicer.StreamTask, request_deserializer=research_dot_v1_dot_research__pb2.StreamTaskRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.TaskEvent.SerializeToString), 'ResumeTask': grpc.unary_unary_rpc_method_handler(servicer.ResumeTask, request_deserializer=research_dot_v1_dot_research__pb2.ResumeTaskRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.ResumeTaskResponse.SerializeToString), 'CancelTask': grpc.unary_unary_rpc_method_handler(servicer.CancelTask, request_deserializer=research_dot_v1_dot_research__pb2.CancelTaskRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.CancelTaskResponse.SerializeToString), 'GetTaskCost': grpc.unary_unary_rpc_method_handler(servicer.GetTaskCost, request_deserializer=research_dot_v1_dot_research__pb2.GetTaskCostRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.GetTaskCostResponse.SerializeToString), 'Chat': grpc.unary_unary_rpc_method_handler(servicer.Chat, request_deserializer=research_dot_v1_dot_research__pb2.ChatRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.ChatResponse.SerializeToString)}
    generic_handler = grpc.method_handlers_generic_handler('research.v1.ResearchService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('research.v1.ResearchService', rpc_method_handlers)

class ResearchService:

    @staticmethod
    def SubmitTask(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.ResearchService/SubmitTask', research_dot_v1_dot_research__pb2.SubmitTaskRequest.SerializeToString, research_dot_v1_dot_research__pb2.SubmitTaskResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def StreamTask(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_stream(request, target, '/research.v1.ResearchService/StreamTask', research_dot_v1_dot_research__pb2.StreamTaskRequest.SerializeToString, research_dot_v1_dot_research__pb2.TaskEvent.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def ResumeTask(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.ResearchService/ResumeTask', research_dot_v1_dot_research__pb2.ResumeTaskRequest.SerializeToString, research_dot_v1_dot_research__pb2.ResumeTaskResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def CancelTask(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.ResearchService/CancelTask', research_dot_v1_dot_research__pb2.CancelTaskRequest.SerializeToString, research_dot_v1_dot_research__pb2.CancelTaskResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def GetTaskCost(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.ResearchService/GetTaskCost', research_dot_v1_dot_research__pb2.GetTaskCostRequest.SerializeToString, research_dot_v1_dot_research__pb2.GetTaskCostResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def Chat(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.ResearchService/Chat', research_dot_v1_dot_research__pb2.ChatRequest.SerializeToString, research_dot_v1_dot_research__pb2.ChatResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

class MemoryServiceStub:

    def __init__(self, channel):
        self.ListMemory = channel.unary_unary('/research.v1.MemoryService/ListMemory', request_serializer=research_dot_v1_dot_research__pb2.ListMemoryRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.ListMemoryResponse.FromString, _registered_method=True)
        self.CreateMemory = channel.unary_unary('/research.v1.MemoryService/CreateMemory', request_serializer=research_dot_v1_dot_research__pb2.CreateMemoryRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.MemoryItem.FromString, _registered_method=True)
        self.UpdateMemory = channel.unary_unary('/research.v1.MemoryService/UpdateMemory', request_serializer=research_dot_v1_dot_research__pb2.UpdateMemoryRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.MemoryItem.FromString, _registered_method=True)
        self.DeleteMemory = channel.unary_unary('/research.v1.MemoryService/DeleteMemory', request_serializer=research_dot_v1_dot_research__pb2.DeleteMemoryRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.DeleteMemoryResponse.FromString, _registered_method=True)
        self.DeleteAllMemory = channel.unary_unary('/research.v1.MemoryService/DeleteAllMemory', request_serializer=research_dot_v1_dot_research__pb2.DeleteAllMemoryRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.DeleteMemoryResponse.FromString, _registered_method=True)
        self.ConfirmMemory = channel.unary_unary('/research.v1.MemoryService/ConfirmMemory', request_serializer=research_dot_v1_dot_research__pb2.ConfirmMemoryRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.MemoryItem.FromString, _registered_method=True)
        self.ListMemoryAudit = channel.unary_unary('/research.v1.MemoryService/ListMemoryAudit', request_serializer=research_dot_v1_dot_research__pb2.ListMemoryAuditRequest.SerializeToString, response_deserializer=research_dot_v1_dot_research__pb2.ListMemoryAuditResponse.FromString, _registered_method=True)

class MemoryServiceServicer:

    def ListMemory(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def CreateMemory(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def UpdateMemory(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def DeleteMemory(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def DeleteAllMemory(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ConfirmMemory(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

    def ListMemoryAudit(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')

def add_MemoryServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {'ListMemory': grpc.unary_unary_rpc_method_handler(servicer.ListMemory, request_deserializer=research_dot_v1_dot_research__pb2.ListMemoryRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.ListMemoryResponse.SerializeToString), 'CreateMemory': grpc.unary_unary_rpc_method_handler(servicer.CreateMemory, request_deserializer=research_dot_v1_dot_research__pb2.CreateMemoryRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.MemoryItem.SerializeToString), 'UpdateMemory': grpc.unary_unary_rpc_method_handler(servicer.UpdateMemory, request_deserializer=research_dot_v1_dot_research__pb2.UpdateMemoryRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.MemoryItem.SerializeToString), 'DeleteMemory': grpc.unary_unary_rpc_method_handler(servicer.DeleteMemory, request_deserializer=research_dot_v1_dot_research__pb2.DeleteMemoryRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.DeleteMemoryResponse.SerializeToString), 'DeleteAllMemory': grpc.unary_unary_rpc_method_handler(servicer.DeleteAllMemory, request_deserializer=research_dot_v1_dot_research__pb2.DeleteAllMemoryRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.DeleteMemoryResponse.SerializeToString), 'ConfirmMemory': grpc.unary_unary_rpc_method_handler(servicer.ConfirmMemory, request_deserializer=research_dot_v1_dot_research__pb2.ConfirmMemoryRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.MemoryItem.SerializeToString), 'ListMemoryAudit': grpc.unary_unary_rpc_method_handler(servicer.ListMemoryAudit, request_deserializer=research_dot_v1_dot_research__pb2.ListMemoryAuditRequest.FromString, response_serializer=research_dot_v1_dot_research__pb2.ListMemoryAuditResponse.SerializeToString)}
    generic_handler = grpc.method_handlers_generic_handler('research.v1.MemoryService', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))
    server.add_registered_method_handlers('research.v1.MemoryService', rpc_method_handlers)

class MemoryService:

    @staticmethod
    def ListMemory(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/ListMemory', research_dot_v1_dot_research__pb2.ListMemoryRequest.SerializeToString, research_dot_v1_dot_research__pb2.ListMemoryResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def CreateMemory(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/CreateMemory', research_dot_v1_dot_research__pb2.CreateMemoryRequest.SerializeToString, research_dot_v1_dot_research__pb2.MemoryItem.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def UpdateMemory(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/UpdateMemory', research_dot_v1_dot_research__pb2.UpdateMemoryRequest.SerializeToString, research_dot_v1_dot_research__pb2.MemoryItem.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def DeleteMemory(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/DeleteMemory', research_dot_v1_dot_research__pb2.DeleteMemoryRequest.SerializeToString, research_dot_v1_dot_research__pb2.DeleteMemoryResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def DeleteAllMemory(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/DeleteAllMemory', research_dot_v1_dot_research__pb2.DeleteAllMemoryRequest.SerializeToString, research_dot_v1_dot_research__pb2.DeleteMemoryResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def ConfirmMemory(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/ConfirmMemory', research_dot_v1_dot_research__pb2.ConfirmMemoryRequest.SerializeToString, research_dot_v1_dot_research__pb2.MemoryItem.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)

    @staticmethod
    def ListMemoryAudit(request, target, options=(), channel_credentials=None, call_credentials=None, insecure=False, compression=None, wait_for_ready=None, timeout=None, metadata=None):
        return grpc.experimental.unary_unary(request, target, '/research.v1.MemoryService/ListMemoryAudit', research_dot_v1_dot_research__pb2.ListMemoryAuditRequest.SerializeToString, research_dot_v1_dot_research__pb2.ListMemoryAuditResponse.FromString, options, channel_credentials, insecure, call_credentials, compression, wait_for_ready, timeout, metadata, _registered_method=True)
