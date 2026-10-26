from pydantic import BaseModel
from typing import Literal

class ToolResult(BaseModel):
    status: Literal['ok', 'empty', 'error']
    data: dict | None = None
    evidence_ids: list[str] = []
    error_code: str | None = None
    retryable: bool = False
