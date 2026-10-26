from celery import Celery
import os
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
app = Celery('lha-workers', broker=REDIS_URL)
app.conf.update(task_serializer='json', accept_content=['json'], result_serializer='json', timezone='Asia/Shanghai', enable_utc=True, task_track_started=True, task_acks_late=True, worker_prefetch_multiplier=1, beat_schedule={'memory-decay-daily': {'task': 'memory.decay', 'schedule': 86400.0}})

@app.task(name='factory.parse_exam_report', bind=True, max_retries=3)
def parse_exam_report_task(self, file_path: str, user_id: str, report_date: str='', institution: str=''):
    from app.factory import health_parser
    path = (file_path or '').lower()
    if path.endswith('.pdf'):
        report, metrics = health_parser.parse_exam_pdf(file_path, user_id, report_date=report_date, institution=institution)
    else:
        report, metrics = health_parser.parse_exam_image(file_path, user_id, report_date=report_date, institution=institution)
    if not metrics:
        return {'file': file_path, 'total': 0, 'inserted': 0}
    report_id, inserted = health_parser.save_report_and_metrics(report, metrics)
    return {'file': file_path, 'report_id': report_id, 'total': len(metrics), 'inserted': inserted}

@app.task(name='factory.index_build', bind=True, max_retries=2)
def index_build_task(self, kv: str, strategy: str='auto'):
    from app.factory.repository import materialize_knowledge_docs
    from app.retrieval.index_builder import rebuild_from_pg
    materialized = materialize_knowledge_docs(kv)
    result = rebuild_from_pg(kv, strategy=strategy)
    return {'status': 'done', 'version': kv, 'materialized': materialized, 'rebuild': result}

@app.task(name='memory.decay', bind=True, max_retries=1)
def memory_decay_task(self):
    from app.memory.decay_job import run
    report = run()
    return {'status': 'done', **report}
