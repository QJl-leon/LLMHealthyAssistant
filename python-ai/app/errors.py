from enum import Enum
from dataclasses import dataclass, field
from typing import Optional

class ErrorCode(str, Enum):
    IMAGE_QUALITY_LOW = 'IMAGE_QUALITY_LOW'
    OCR_LOW_CONFIDENCE = 'OCR_LOW_CONFIDENCE'
    RETRIEVAL_EMPTY = 'RETRIEVAL_EMPTY'
    MODEL_TIMEOUT = 'MODEL_TIMEOUT'
    CITATION_MISMATCH = 'CITATION_MISMATCH'
    PERMISSION_DENIED = 'PERMISSION_DENIED'
    MEMORY_CONFIRM_REQUIRED = 'MEMORY_CONFIRM_REQUIRED'
    RATE_LIMITED = 'RATE_LIMITED'
    UPSTREAM_UNAVAILABLE = 'UPSTREAM_UNAVAILABLE'
    BAD_REQUEST = 'BAD_REQUEST'
    INTERNAL_ERROR = 'INTERNAL_ERROR'
    TASK_NOT_FOUND = 'TASK_NOT_FOUND'
_ERROR_META: dict[str, dict] = {ErrorCode.IMAGE_QUALITY_LOW: {'retryable': True, 'ui_action': '引导补拍（附具体动作）'}, ErrorCode.OCR_LOW_CONFIDENCE: {'retryable': True, 'ui_action': '标记低置信区域，建议补拍'}, ErrorCode.RETRIEVAL_EMPTY: {'retryable': False, 'ui_action': "显示'未找到证据'，非报错"}, ErrorCode.MODEL_TIMEOUT: {'retryable': True, 'ui_action': "'模型繁忙'，自动重试一次"}, ErrorCode.CITATION_MISMATCH: {'retryable': False, 'ui_action': '报告回炉，用户无感知'}, ErrorCode.PERMISSION_DENIED: {'retryable': False, 'ui_action': '明确拒绝文案'}, ErrorCode.MEMORY_CONFIRM_REQUIRED: {'retryable': False, 'ui_action': '弹出记忆确认卡片'}, ErrorCode.RATE_LIMITED: {'retryable': True, 'ui_action': '提示稍后重试'}, ErrorCode.UPSTREAM_UNAVAILABLE: {'retryable': True, 'ui_action': '降级提示'}, ErrorCode.BAD_REQUEST: {'retryable': False, 'ui_action': '检查请求参数'}, ErrorCode.INTERNAL_ERROR: {'retryable': False, 'ui_action': '内部错误，联系管理员'}, ErrorCode.TASK_NOT_FOUND: {'retryable': False, 'ui_action': '任务不存在或已过期'}}

def is_retryable(code: str) -> bool:
    return _ERROR_META.get(code, {}).get('retryable', False)

def ui_action(code: str) -> str:
    return _ERROR_META.get(code, {}).get('ui_action', '未知错误')

@dataclass
class AgentError(Exception):
    error_code: str
    message: str
    retryable: bool = False
    details: dict = field(default_factory=dict)

    def __str__(self):
        return f'[{self.error_code}] {self.message}'
