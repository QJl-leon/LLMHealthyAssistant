import os
import logging
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from app.memory.curator import ProfileEntry
from app.memory import crypto
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')

def _conn():
    return psycopg2.connect(DATABASE_URL)

def init_memory_tables():
    sql = "\n    CREATE TABLE IF NOT EXISTS memory_items (\n        id            UUID PRIMARY KEY,\n        user_id       TEXT NOT NULL,\n        kind          TEXT NOT NULL,              -- basic / condition / medication / allergy / goal / exercise\n        content       TEXT NOT NULL,              -- 密文（hex，AES-256-GCM）\n        content_hash  TEXT NOT NULL DEFAULT '',   -- SHA-256(明文)，去重用（不泄露明文）\n        metric_codes  TEXT[] NOT NULL DEFAULT '{}', -- 关联指标编码（按指标命中记忆）\n        source        TEXT NOT NULL DEFAULT 'user_stated',\n        confidence    REAL DEFAULT 1.0,\n        version       INT NOT NULL DEFAULT 1,\n        superseded_at TIMESTAMPTZ,\n        deleted_at    TIMESTAMPTZ,\n        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),\n        CONSTRAINT chk_memory_kind CHECK (\n            kind IN ('basic','condition','medication','allergy','goal','exercise')\n        )\n    );\n\n    ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';\n    ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS metric_codes TEXT[] NOT NULL DEFAULT '{}';\n    -- B6a（2026-09-20）：置信度衰减治理\n    -- pending_confirmation: 衰减到阈值以下转入待确认队列（用户确认后复位）\n    -- last_confirmed_at:    衰减计时基准（写入 / 更新 / 确认时刷新）\n    ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS pending_confirmation BOOLEAN NOT NULL DEFAULT FALSE;\n    ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now();\n\n    -- 旧枚举兼容迁移（avoidance/focus → condition/goal），保证 CHECK 约束可加且幂等\n    UPDATE memory_items SET kind = 'condition' WHERE kind = 'avoidance';\n    UPDATE memory_items SET kind = 'goal' WHERE kind = 'focus';\n\n    DO $$\n    BEGIN\n        ALTER TABLE memory_items ADD CONSTRAINT chk_memory_kind CHECK (\n            kind IN ('basic','condition','medication','allergy','goal','exercise')\n        );\n    EXCEPTION\n        WHEN duplicate_object THEN NULL;\n        WHEN duplicate_table THEN NULL;\n        WHEN check_violation THEN NULL;\n    END $$;\n\n    CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_items (user_id);\n    CREATE INDEX IF NOT EXISTS idx_memory_user_kind ON memory_items (user_id, kind);\n    CREATE INDEX IF NOT EXISTS idx_memory_metric_codes\n        ON memory_items USING GIN (metric_codes);\n\n    CREATE TABLE IF NOT EXISTS memory_audit_log (\n        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),\n        user_id     TEXT NOT NULL,\n        action      TEXT NOT NULL,               -- write / update / delete / delete_all\n        target_id   TEXT NOT NULL DEFAULT '',\n        detail      TEXT DEFAULT '',\n        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()\n    );\n\n    CREATE INDEX IF NOT EXISTS idx_audit_user ON memory_audit_log (user_id);\n    CREATE INDEX IF NOT EXISTS idx_audit_time ON memory_audit_log (created_at DESC);\n\n    -- 情景记忆：历史体检分析摘要（Python 独占）\n    CREATE TABLE IF NOT EXISTS episodic_memories (\n        id              UUID PRIMARY KEY,\n        user_id         TEXT NOT NULL,\n        task_id         TEXT NOT NULL,\n        product_name    TEXT NOT NULL DEFAULT '',      -- 报告标识（体检机构/报告标题）\n        product_type    TEXT NOT NULL DEFAULT '',      -- 报告类型\n        metric_codes    TEXT[] NOT NULL DEFAULT '{}',  -- 本次解析的指标编码（按指标命中记忆）\n        summary         TEXT NOT NULL DEFAULT '',\n        unknowns        TEXT NOT NULL DEFAULT '',\n        report_version  TEXT NOT NULL DEFAULT '',\n        related_hits    TEXT[] NOT NULL DEFAULT '{}',\n        created_at      TIMESTAMPTZ NOT NULL DEFAULT now()\n    );\n\n    ALTER TABLE episodic_memories ADD COLUMN IF NOT EXISTS metric_codes TEXT[] NOT NULL DEFAULT '{}';\n\n    CREATE INDEX IF NOT EXISTS idx_episodic_user ON episodic_memories (user_id);\n    CREATE INDEX IF NOT EXISTS idx_episodic_user_time ON episodic_memories (user_id, created_at DESC);\n    CREATE INDEX IF NOT EXISTS idx_episodic_product ON episodic_memories (user_id, product_name);\n    CREATE INDEX IF NOT EXISTS idx_episodic_metric_codes\n        ON episodic_memories USING GIN (metric_codes);\n    "
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info('[MemoryRepo] 表初始化完成（memory_items / episodic_memories）')

def save_episodic(*, user_id: str, task_id: str, product_name: str='', product_type: str='', metric_codes: list[str] | None=None, summary: str='', unknowns: str='', report_version: str='', related_hits: list[str] | None=None) -> dict:
    from uuid import uuid4
    eid = str(uuid4())
    codes = [c for c in metric_codes or [] if c]
    hits = related_hits or []
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO episodic_memories\n                   (id, user_id, task_id, product_name, product_type,\n                    metric_codes, summary, unknowns, report_version, related_hits, created_at)\n                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())', (eid, user_id, task_id, product_name or '', product_type or '', codes, summary or '', unknowns or '', report_version or '', hits))
        conn.commit()
    logger.info('[MemoryRepo] episodic saved id=%s user=%s label=%s metrics=%d', eid, user_id, product_name, len(codes))
    return {'id': eid, 'user_id': user_id, 'task_id': task_id, 'product_name': product_name}

def search_episodic(user_id: str, *, product_name: str='', metric_codes: list[str] | None=None, limit: int=5) -> list[dict]:
    codes = [c for c in metric_codes or [] if c]
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows: list = []
            if product_name and product_name != 'unknown':
                cur.execute('SELECT * FROM episodic_memories\n                       WHERE user_id = %s AND product_name ILIKE %s\n                       ORDER BY created_at DESC LIMIT %s', (user_id, f'%{product_name}%', limit))
                rows = list(cur.fetchall())
            if len(rows) < limit and codes:
                cur.execute('SELECT * FROM episodic_memories\n                       WHERE user_id = %s AND metric_codes && %s::text[]\n                       ORDER BY created_at DESC LIMIT %s', (user_id, codes[:20], limit))
                for r in cur.fetchall():
                    if str(r['id']) not in {str(x['id']) for x in rows}:
                        rows.append(r)
                    if len(rows) >= limit:
                        break
            if len(rows) < limit:
                cur.execute('SELECT * FROM episodic_memories\n                       WHERE user_id = %s\n                       ORDER BY created_at DESC LIMIT %s', (user_id, limit))
                for r in cur.fetchall():
                    if str(r['id']) not in {str(x['id']) for x in rows}:
                        rows.append(r)
                    if len(rows) >= limit:
                        break
    out = []
    for r in rows[:limit]:
        out.append({'id': str(r['id']), 'task_id': r['task_id'], 'product_name': r['product_name'] or '', 'product_type': r['product_type'] or '', 'metric_codes': list(r.get('metric_codes') or []), 'summary': r['summary'] or '', 'unknowns': r['unknowns'] or '', 'report_version': r['report_version'] or '', 'related_hits': list(r['related_hits'] or []), 'created_at': r['created_at'].isoformat() if r.get('created_at') else ''})
    return out

def insert_entry(entry: ProfileEntry, user_id: str) -> ProfileEntry:
    enc = crypto.encrypt(entry.content)
    chash = crypto.content_hash(entry.content)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO memory_items\n                   (id, user_id, kind, content, content_hash, metric_codes,\n                    source, confidence, version, created_at)\n                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', (entry.id, user_id, entry.kind, enc, chash, list(entry.metric_codes or []), entry.source, entry.confidence, entry.version, entry.created_at))
        conn.commit()
    return entry

def supersede_and_insert(user_id: str, entry_id: str, new_entry: ProfileEntry) -> ProfileEntry:
    now = datetime.utcnow()
    enc = crypto.encrypt(new_entry.content)
    chash = crypto.content_hash(new_entry.content)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE memory_items SET superseded_at = %s\n                   WHERE id = %s AND user_id = %s\n                     AND superseded_at IS NULL AND deleted_at IS NULL', (now, entry_id, user_id))
            cur.execute('INSERT INTO memory_items\n                   (id, user_id, kind, content, content_hash, metric_codes,\n                    source, confidence, version, created_at)\n                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)', (new_entry.id, user_id, new_entry.kind, enc, chash, list(new_entry.metric_codes or []), new_entry.source, new_entry.confidence, new_entry.version, new_entry.created_at))
        conn.commit()
    return new_entry

def soft_delete_entry(entry_id: str, user_id: str) -> bool:
    now = datetime.utcnow()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE memory_items SET deleted_at = %s\n                   WHERE id = %s AND user_id = %s\n                     AND deleted_at IS NULL', (now, entry_id, user_id))
        conn.commit()
        return cur.rowcount > 0

def soft_delete_all(user_id: str) -> int:
    now = datetime.utcnow()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE memory_items SET deleted_at = %s\n                   WHERE user_id = %s AND deleted_at IS NULL', (now, user_id))
        conn.commit()
        return cur.rowcount

def get_active_entries(user_id: str) -> list[ProfileEntry]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT id, kind, content, metric_codes, source, confidence, version,\n                          superseded_at, deleted_at, created_at,\n                          pending_confirmation, last_confirmed_at\n                   FROM memory_items\n                   WHERE user_id = %s\n                     AND superseded_at IS NULL\n                     AND deleted_at IS NULL\n                   ORDER BY kind, created_at DESC', (user_id,))
            rows = cur.fetchall()
    entries = []
    for r in rows:
        entries.append(ProfileEntry(id=str(r['id']), kind=r['kind'], content=crypto.maybe_decrypt(r['content']), metric_codes=list(r.get('metric_codes') or []), source=r['source'], confidence=r['confidence'] or 1.0, version=r['version'], created_at=r['created_at'], superseded_at=r['superseded_at'], deleted_at=r['deleted_at'], pending_confirmation=bool(r.get('pending_confirmation'))))
    return entries

def decay_inferred_entries(user_id: Optional[str]=None, decay_days: int=90, decay_factor: float=0.5, decay_threshold: float=0.3) -> list[dict]:
    user_clause = 'AND user_id = %s' if user_id else ''
    sql = f"\n        WITH candidates AS (\n            SELECT id, confidence AS old_confidence\n            FROM memory_items\n            WHERE source != 'user_stated'\n              AND superseded_at IS NULL\n              AND deleted_at IS NULL\n              AND pending_confirmation = FALSE\n              AND last_confirmed_at < now() - make_interval(days => %s)\n              {user_clause}\n        ),\n        updated AS (\n            UPDATE memory_items m\n            SET confidence = m.confidence * %s,\n                pending_confirmation = CASE\n                    WHEN m.confidence * %s < %s THEN TRUE\n                    ELSE m.pending_confirmation\n                END\n            FROM candidates c\n            WHERE m.id = c.id\n            RETURNING m.id, m.user_id, m.kind, m.confidence AS new_confidence,\n                      m.pending_confirmation, c.old_confidence\n        )\n        SELECT * FROM updated\n    "
    params: list = [decay_days]
    if user_id:
        params.append(user_id)
    params += [decay_factor, decay_factor, decay_threshold]
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    for r in rows:
        r['id'] = str(r['id'])
    return rows

def confirm_entry(user_id: str, entry_id: str) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('UPDATE memory_items\n                   SET confidence = 1.0,\n                       pending_confirmation = FALSE,\n                       last_confirmed_at = now()\n                   WHERE id = %s AND user_id = %s\n                     AND superseded_at IS NULL AND deleted_at IS NULL', (entry_id, user_id))
        conn.commit()
        return cur.rowcount > 0

def get_pending_confirmation_entries(user_id: str) -> list[ProfileEntry]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT id, kind, content, metric_codes, source, confidence, version,\n                          superseded_at, deleted_at, created_at, pending_confirmation\n                   FROM memory_items\n                   WHERE user_id = %s\n                     AND pending_confirmation = TRUE\n                     AND superseded_at IS NULL\n                     AND deleted_at IS NULL\n                   ORDER BY created_at DESC', (user_id,))
            rows = cur.fetchall()
    entries = []
    for r in rows:
        entries.append(ProfileEntry(id=str(r['id']), kind=r['kind'], content=crypto.maybe_decrypt(r['content']), metric_codes=list(r.get('metric_codes') or []), source=r['source'], confidence=r['confidence'] or 0.5, version=r['version'], created_at=r['created_at'], pending_confirmation=True))
    return entries

def entry_exists(user_id: str, kind: str, content: str) -> bool:
    chash = crypto.content_hash(content)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM memory_items\n                   WHERE user_id = %s AND kind = %s AND content_hash = %s\n                     AND superseded_at IS NULL AND deleted_at IS NULL\n                   LIMIT 1', (user_id, kind, chash))
            return cur.fetchone() is not None

def write_audit(user_id: str, action: str, target_id: str, detail: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO memory_audit_log (user_id, action, target_id, detail)\n                   VALUES (%s, %s, %s, %s)', (user_id, action, target_id, detail))
        conn.commit()

def get_audit_log(user_id: Optional[str]=None, limit: int=100) -> list[dict]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if user_id:
                cur.execute('SELECT * FROM memory_audit_log\n                       WHERE user_id = %s ORDER BY created_at DESC LIMIT %s', (user_id, limit))
            else:
                cur.execute('SELECT * FROM memory_audit_log ORDER BY created_at DESC LIMIT %s', (limit,))
            return [dict(r) for r in cur.fetchall()]
