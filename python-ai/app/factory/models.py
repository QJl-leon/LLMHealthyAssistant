from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class Source(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    level: int
    license_: str = Field(default='', alias='license')
    url: str = ''
    hash: str
    status: str = 'pending'
    created_at: datetime = Field(default_factory=datetime.utcnow)

class KnowledgeVersion(BaseModel):
    version: str
    source_ids: list[UUID] = []
    published_at: Optional[datetime] = None
    rollback_of: Optional[str] = None

class ParsedDocument(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    knowledge_version: str = ''
    kind: str
    content: dict
    content_hash: str = ''
    created_at: datetime = Field(default_factory=datetime.utcnow)

class MetricCatalogRow(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    metric_code: str
    name_cn: str
    name_en: str = ''
    category: str = ''
    unit: str = ''
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    ref_text: str = ''
    direction: str = 'both'
    advice_hint: str = ''
    source_id: UUID
    knowledge_version: str = ''

class HealthReport(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: str
    report_date: str
    institution: str = ''
    report_type: str = 'physical_exam'
    source_id: Optional[UUID] = None
    knowledge_version: str = ''
    content_hash: str = ''
    created_at: datetime = Field(default_factory=datetime.utcnow)

class HealthMetric(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    report_id: UUID
    user_id: str
    metric_code: str
    metric_name: str
    category: str = ''
    value_num: Optional[float] = None
    value_text: str = ''
    unit: str = ''
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    ref_text: str = ''
    flag: str = 'unknown'
    measured_at: str = ''
    source_page: Optional[int] = None

class HealthGuideline(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    doc_type: str
    evidence_level: str = 'B'
    title: str
    org: str = ''
    year: Optional[int] = None
    topic: str = ''
    content: str
    url: str = ''
    source_id: UUID
    knowledge_version: str = ''

class MedicalCase(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    case_code: str
    age_band: str = ''
    sex: str = ''
    chief_complaint: str = ''
    findings: str = ''
    metrics: dict = {}
    diagnosis: str = ''
    intervention: str = ''
    outcome: str = ''
    evidence_level: str = 'C'
    source_id: UUID
    knowledge_version: str = ''
