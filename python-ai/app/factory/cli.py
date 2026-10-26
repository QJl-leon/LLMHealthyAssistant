import os
import argparse
import logging
from datetime import datetime
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def cmd_init():
    from app.factory.repository import init_tables
    from app.memory.repository import init_memory_tables
    logger.info('正在初始化数据表...')
    init_tables()
    logger.info('  ✅ factory 表（sources / knowledge_versions / parsed_documents / metric_catalog / health_reports / health_metrics / health_guidelines / medical_cases）')
    init_memory_tables()
    logger.info('  ✅ memory 表（memory_items / memory_audit_log）')
    logger.info('✅ 全部表结构初始化完成')

def cmd_seed(knowledge_version: str='draft'):
    from app.factory.seed import seed_corpus
    logger.info('正在装载语料（knowledge_version=%s）...', knowledge_version)
    results = seed_corpus(knowledge_version=knowledge_version)
    logger.info('✅ 语料装载完成:')
    for table, count in results.items():
        logger.info('   %s: %d 条', table, count)
    logger.info('   metric_catalog → 体检指标目录')
    logger.info('   health_guidelines → 健康论文库')
    logger.info('   medical_cases → 病历案例库')
    logger.info('\n下一步: python -m app.factory.cli version publish <kv>')

def cmd_ingest(args):
    if args.corpus or args.sample:
        cmd_seed()
        return
    print('用法: ingest --corpus  （--sample 为等价旧用法）')

def cmd_version(args):
    from app.factory.repository import get_current_version, publish_version, rollback_version, list_sources
    if args.action == 'list':
        _list_versions()
        return
    if args.action == 'publish':
        current = get_current_version()
        if current:
            logger.info('当前版本: %s (发布於 %s)', current.version, current.published_at.strftime('%Y-%m-%d %H:%M') if current.published_at else 'unknown')
        sources = list_sources(status='approved')
        if not sources:
            logger.warning('⚠️  没有已批准的 sources，请先运行 `python -m app.factory.cli seed`')
            return
        source_ids = [s.id for s in sources]
        new_version = args.kv or f"kv_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        kv = publish_version(new_version, source_ids)
        logger.info('✅ 版本已发布: %s', kv.version)
        logger.info('   包含 sources: %d', len(source_ids))
        for s in sources:
            logger.info('     - %s (level=%d)', s.name, s.level)
        logger.info('   draft 语料已晋升为该版本，parsed_documents 已物化')
        logger.info('\n下一步:')
        logger.info('  1. 运行索引构建: python -m app.retrieval.index_builder --rebuild')
        logger.info('  2. 验证检索: python -m app.eval --json')
        return
    if args.action == 'rollback':
        current = get_current_version()
        if not current:
            logger.warning('⚠️  无已发布版本可回滚')
            return
        logger.info('当前版本: %s', current.version)
        new_kv = rollback_version(current.version)
        logger.info('✅ 已回滚 → 新版本: %s', new_kv.version)
        logger.info('   实际生效的仍是 %s 的 sources（回滚标记已创建）', current.version)
        return
    print('用法: version list | publish <kv> | rollback')

def cmd_status():
    from app.factory.repository import get_current_version, list_sources
    print('\n═══════════════════════════════════════════')
    print('  数据工厂状态')
    print('═══════════════════════════════════════════')
    kv = get_current_version()
    if kv:
        print(f'  当前知识版本: {kv.version}')
        print(f"  发布日期:      {(kv.published_at.strftime('%Y-%m-%d %H:%M') if kv.published_at else 'unknown')}")
        print(f'  包含 sources:  {len(kv.source_ids)}')
    else:
        print('  当前知识版本: (无) — 请先运行 `version publish <kv>`')
    print()
    approved = list_sources('approved')
    pending = list_sources('pending')
    if approved:
        print(f'  已批准 sources ({len(approved)}):')
        for s in approved:
            print(f'    ✅ [{s.level}] {s.name}')
    else:
        print('  已批准 sources: (无)')
    if pending:
        print(f'  待审核 sources ({len(pending)}):')
        for s in pending:
            print(f'    ⏳ [{s.level}] {s.name}')
    print()
    try:
        from app.factory.repository import list_metric_catalog, list_guidelines, list_cases
        print(f'  体检指标目录 (metric_catalog):   {len(list_metric_catalog())} 条')
        print(f'  健康论文库   (health_guidelines): {len(list_guidelines())} 条')
        print(f'  病历案例库   (medical_cases):    {len(list_cases())} 条')
    except Exception as e:
        logger.warning('无法统计语料条数: %s', e)
    print()
    if not kv:
        print('  💡 快速开始: python -m app.factory.cli seed && python -m app.factory.cli version publish kv_20260915_001')
    elif not approved:
        print('  💡 下一步: python -m app.factory.cli seed')
    else:
        print('  💡 索引命令: python -m app.retrieval.index_builder --rebuild')
    print()

def _list_versions():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
    try:
        conn = psycopg2.connect(DB)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT version, published_at, rollback_of, array_length(source_ids, 1) as source_count FROM knowledge_versions ORDER BY published_at DESC LIMIT 20')
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            print('(无版本记录)')
            return
        print(f"\n{'版本':<30} {'发布时间':<22} {'sources':>8}  {'回滚自'}")
        print('-' * 85)
        for r in rows:
            ts = str(r['published_at'])[:19] if r['published_at'] else '-'
            rb = r['rollback_of'] or ''
            print(f"{r['version']:<30} {ts:<22} {r['source_count'] or 0:>8}  {rb}")
        print()
    except Exception as e:
        logger.warning('无法连接数据库: %s', e)
        print('(数据库不可达，无法列出版本)')

def main():
    parser = argparse.ArgumentParser(description='数据工厂 CLI — 语料装载与知识版本管理', formatter_class=argparse.RawDescriptionHelpFormatter, epilog='\n示例:\n  python -m app.factory.cli init\n  python -m app.factory.cli seed\n  python -m app.factory.cli ingest --corpus\n  python -m app.factory.cli version publish kv_20260915_001\n  python -m app.factory.cli status\n        ')
    sub = parser.add_subparsers(dest='command')
    sub.add_parser('init', help='初始化数据库表结构')
    sub.add_parser('seed', help='装载 corpus 语料（指标目录/健康论文库/病历案例库）')
    p_ingest = sub.add_parser('ingest', help='导入数据')
    p_ingest.add_argument('--corpus', action='store_true', help='装载三份 JSON 语料（metric_catalog / guidelines / cases）')
    p_ingest.add_argument('--sample', action='store_true', help='兼容旧用法，语义等同 --corpus')
    p_ver = sub.add_parser('version', help='知识版本管理')
    p_ver.add_argument('action', nargs='?', choices=['list', 'publish', 'rollback'], default='list', help='操作: list | publish <kv> | rollback')
    p_ver.add_argument('kv', nargs='?', default=None, help='版本号（publish 时可省略，省略则按时间自动生成）')
    sub.add_parser('status', help='查看当前数据状态')
    args = parser.parse_args()
    if args.command == 'init':
        cmd_init()
    elif args.command == 'seed':
        cmd_seed()
    elif args.command == 'ingest':
        cmd_ingest(args)
    elif args.command == 'version':
        cmd_version(args)
    elif args.command == 'status':
        cmd_status()
    else:
        parser.print_help()
if __name__ == '__main__':
    main()
