from __future__ import annotations
import glob
import json
import logging
import os
import sys
import time
from datetime import datetime
from app.eval import judge as judge_mod
from app.eval import retrieval_bench
logger = logging.getLogger(__name__)
GATE_THRESHOLD = 0.8
_SLICES = [('s1', 'abnormal_metric', '异常指标识别（LDL-C 4.2 > 3.4）'), ('s2', 'no_answer', '无证据拒答'), ('s3', 'fake_citation', '伪造引用拦截'), ('s4', 'dual_bank', '双库分区命中（论文库 vs 病历库）'), ('s5', 'profile_safety', '档案安全约束命中（病史/用药）'), ('s6', 'trend_citation', '趋势引用（异常指标走本人历史通道）'), ('s7', 'exercise_citation', '运动建议必须带引用（论文库）'), ('s8', 'metric_consistency', '指标数值与库一致（需 DB）'), ('s9', 'normal_no_alarm', '正常指标不误报')]
_LDL_HIGH = {'metric_name': '低密度脂蛋白', 'metric_code': 'LDL_C', 'category': '血脂', 'flag': 'high'}

def _classify_flag(value, ref_low, ref_high, direction: str='both') -> str:
    if value is None:
        return 'unknown'
    flag = 'normal'
    if ref_high is not None and value > ref_high:
        flag = 'high'
    elif ref_low is not None and value < ref_low:
        flag = 'low'
    if direction == 'high' and flag == 'low':
        flag = 'normal'
    if direction == 'low' and flag == 'high':
        flag = 'normal'
    return flag

def _planner(**profile):
    from app.retrieval.query_planner import QueryPlanner
    return QueryPlanner(user_profile=profile or None)

def _slice_abnormal_metric():
    flag = _classify_flag(4.2, None, 3.4, 'high')
    plan = _planner().plan([_LDL_HIGH])
    routed = bool(plan.plans) and 'sql' in plan.channels_used
    return (flag == 'high' and routed, f'flag={flag}, 路由 sql={routed}')

def _slice_no_answer():
    from app.evidence.validator import refuse_if_no_evidence
    claims = [{'claim_id': 'c1', 'type': 'fact', 'text': '建议进行有氧运动', 'evidence_ids': []}]
    refuse, reason = refuse_if_no_evidence(claims, [])
    return (bool(refuse and reason), f'拒答={refuse}（{reason}）')

def _slice_fake_citation():
    from app.evidence.validator import validate_claims_against_evidence
    claims = [{'claim_id': 'c1', 'type': 'fact', 'text': '低密度脂蛋白胆固醇偏高需运动干预', 'evidence_ids': ['ev_fake_001']}]
    evidence = [{'evidence_id': 'ev_real_001', 'quote': '低密度脂蛋白胆固醇 4.2 mmol/L 偏高'}]
    errors = validate_claims_against_evidence(claims, evidence)
    blocked = len(errors) == 1 and errors[0].get('error_code') == 'CITATION_MISMATCH'
    return (blocked, f'拦截={blocked}, errors={errors}')

def _slice_dual_bank():
    plan = _planner().plan([_LDL_HIGH])
    srcs = set(plan.source_types_used)
    ok = {'guideline', 'case'} <= srcs
    return (ok, f'source_types={sorted(srcs)}')

def _slice_profile_safety():
    plan = _planner(condition=['高血脂'], medication=['他汀']).plan([_LDL_HIGH])
    safety = [p.subject for p in plan.plans if p.priority == 1 and p.subject in ('高血脂', '他汀')]
    return (len(safety) >= 2, f'安全约束计划={safety}')

def _slice_trend_citation():
    plan = _planner().plan([_LDL_HIGH])
    ok = 'sql' in plan.channels_used
    return (ok, f'channels={sorted(plan.channels_used)}（sql=本人指标历史趋势）')

def _slice_exercise_citation():
    plan = _planner().plan([], query='我想开始运动，应该怎么安排')
    exercise = [p for p in plan.plans if p.category == 'exercise']
    ok = bool(exercise) and all(('guideline' in p.source_types for p in exercise))
    detail = [(p.subject, p.source_types) for p in exercise]
    return (ok, f'运动计划={detail}')

def _slice_metric_consistency():
    try:
        from app.factory.repository import get_metric_by_code, list_metric_catalog
        rows = list_metric_catalog()
    except Exception as e:
        return (None, f'数据库不可用，跳过：{type(e).__name__}')
    if not rows:
        return (None, 'metric_catalog 为空（健康知识未 ingest），跳过')
    try:
        row = get_metric_by_code('LDL_C')
    except Exception:
        row = None
    if row is None or row.ref_high is None:
        row = next((r for r in rows if r.ref_high is not None), None)
    if row is None:
        return (None, '指标目录无带数值参考区间的指标，跳过')
    hi = row.ref_high
    in_range = (row.ref_low + hi) / 2 if row.ref_low is not None else hi - 0.1
    flag_high = _classify_flag(hi + 0.1, row.ref_low, hi, row.direction)
    flag_normal = _classify_flag(in_range, row.ref_low, hi, row.direction)
    ok = flag_high == 'high' and flag_normal == 'normal'
    return (ok, f'{row.metric_code} 库参考上限={hi} → flag(超上限)={flag_high}, flag(区间内)={flag_normal}')

def _slice_normal_no_alarm():
    flag = _classify_flag(2.5, None, 3.4, 'high')
    plan = _planner().plan([{'metric_name': '低密度脂蛋白', 'metric_code': 'LDL_C', 'category': '血脂', 'flag': 'normal'}])
    priority = plan.plans[0].priority if plan.plans else -1
    return (flag == 'normal' and priority == 3, f'flag={flag}, priority={priority}')
_DISPATCH = {'abnormal_metric': _slice_abnormal_metric, 'no_answer': _slice_no_answer, 'fake_citation': _slice_fake_citation, 'dual_bank': _slice_dual_bank, 'profile_safety': _slice_profile_safety, 'trend_citation': _slice_trend_citation, 'exercise_citation': _slice_exercise_citation, 'metric_consistency': _slice_metric_consistency, 'normal_no_alarm': _slice_normal_no_alarm}

def _run_slices() -> dict:
    details = []
    for sid, cat, desc in _SLICES:
        try:
            passed, note = _DISPATCH[cat]()
        except Exception as e:
            passed, note = (None, f'执行异常，跳过：{type(e).__name__}: {e}')
        if passed is None:
            logger.warning('[eval] 切片 %s (%s) 跳过：%s', sid, cat, note)
            details.append({'id': sid, 'category': cat, 'desc': desc, 'status': 'skipped', 'passed': False, 'note': note})
            continue
        details.append({'id': sid, 'category': cat, 'desc': desc, 'status': 'ok', 'passed': bool(passed), 'note': note})
    executed = [d for d in details if d['status'] == 'ok']
    passed = sum((1 for d in executed if d['passed']))
    return {'total': len(details), 'executed': len(executed), 'skipped': len(details) - len(executed), 'passed': passed, 'pass_rate': round(passed / len(executed), 3) if executed else 0.0, 'details': details, 'note': '行为切片为规则判定版（QueryPlanner 路由 + 引用校验规则）；需数据库的切片在库未就绪时跳过，不计入分母。文档注入/记忆投毒的端到端拦截演示见 memory_bench。'}
RETRIEVAL_GATE = (('recall@10', 0.5), ('mrr', 0.6))
GENERATION_GATE = (('faithfulness', 0.7), ('citation_accuracy', 0.9), ('answer_relevancy', 0.7))

def _layer_gate_checks(retrieval: dict, gen: dict) -> tuple[list[dict], list[str]]:
    checks: list[dict] = []
    unexecuted: list[str] = []
    agg = dict((retrieval or {}).get('aggregated') or {})
    if not agg:
        unexecuted.append('检索层指标未执行：' + str((retrieval or {}).get('error') or (retrieval or {}).get('status') or '无数据'))
    else:
        for metric, threshold in RETRIEVAL_GATE:
            val = agg.get(metric)
            if val is None:
                unexecuted.append(f'检索层指标缺失: {metric}')
                continue
            checks.append({'layer': 'retrieval', 'metric': metric, 'value': round(float(val), 4), 'threshold': threshold, 'passed': float(val) >= threshold})
    mode = str((gen or {}).get('judge_mode') or '')
    if (gen or {}).get('sample') == 'demo':
        unexecuted.append('生成层指标未真实执行（被评对象为内置演示样例，非真实管线产出）')
    elif mode != 'llm':
        unexecuted.append(f"生成层指标未真实执行（judge_mode={mode or 'unknown'}，规则兜底不参与门禁）")
    else:
        for metric, threshold in GENERATION_GATE:
            val = (gen or {}).get(metric)
            if val is None:
                unexecuted.append(f'生成层指标缺失: {metric}')
                continue
            checks.append({'layer': 'generation', 'metric': metric, 'value': round(float(val), 4), 'threshold': threshold, 'passed': float(val) >= threshold})
    return (checks, unexecuted)

def _load_real_judge_gen() -> dict | None:
    import json as _json
    pattern = os.path.join(os.path.dirname(__file__), 'reports', 'judge_real_*.json')
    hits = sorted(glob.glob(pattern))
    explicit = os.getenv('EVAL_JUDGE_REPORT')
    if explicit:
        hits = [explicit]
    if not hits:
        return None
    try:
        with open(hits[-1], encoding='utf-8') as f:
            report = _json.load(f)
    except Exception:
        return None
    if report.get('demo') is not False or not report.get('aggregate'):
        return None
    if str(report.get('timestamp', ''))[:10] != datetime.now().date().isoformat():
        return None
    if not report.get('cases') or report.get('succeeded') != report['cases']:
        return None
    if report.get('llm_judged') != report['cases']:
        return None
    agg = report['aggregate']
    return {'judge_mode': 'llm', 'sample': 'real_pipeline', 'source_report': os.path.basename(hits[-1]), 'cases': report.get('succeeded'), 'faithfulness': agg.get('llm_judge_faithfulness'), 'citation_accuracy': agg.get('citation_accuracy'), 'answer_relevancy': agg.get('llm_judge_answer_relevancy'), 'llm_judge_faithfulness': agg.get('llm_judge_faithfulness'), 'timestamp': report['timestamp'], 'check_error_count': report.get('check_error_count', 0), 'score_source': 'LLM faithfulness/relevancy; registered-reference citation accuracy'}

def run_all(gate_mode: bool=False, retrieval_mode: str='auto') -> dict:
    start = time.time()
    slices = _run_slices()
    if slices['skipped']:
        logger.warning('[eval] %d/%d 个切片因依赖未就绪被跳过', slices['skipped'], slices['total'])
    try:
        retrieval = retrieval_bench.run_retrieval_bench(retrieval_mode)
    except Exception as e:
        logger.warning('[eval] 检索评测不可用（%s）：%s', type(e).__name__, e)
        retrieval = {'benchmark': 'retrieval_quality', 'mode': retrieval_mode, 'status': 'unavailable', 'error': f'{type(e).__name__}: {e}', 'aggregated': {}}
    gen = _load_real_judge_gen()
    if gen is None:
        gen = judge_mod.evaluate_report(question=_DEMO_QUESTION, report_text=_DEMO_REPORT, claims=_DEMO_CLAIMS, evidence=_DEMO_EVIDENCE, retrieved=_DEMO_RETRIEVED, relevant=_DEMO_RELEVANT, judge_mode='rule')
        if isinstance(gen, dict):
            gen.setdefault('sample', 'demo')
    layer_checks, unexecuted = _layer_gate_checks(retrieval, gen)
    if slices['skipped']:
        unexecuted.append(f"行为切片未完整执行: skipped={slices['skipped']}")
    layer_ok = not unexecuted and all(c['passed'] for c in layer_checks)
    pipeline_ok = not gen.get('check_error_count', 0)
    overall = round(slices['pass_rate'], 3)
    report = {'eval_version': 'v2.3', 'timestamp': datetime.now().isoformat(timespec='seconds'), 'duration_sec': round(time.time() - start, 1), 'slices': slices, 'retrieval': retrieval, 'generation': gen, 'layer_gate_checks': layer_checks, 'unexecuted_metrics': unexecuted, 'overall_pass_rate': overall, 'gate': {'threshold': GATE_THRESHOLD, 'passed': overall >= GATE_THRESHOLD and layer_ok and pipeline_ok, 'coverage_complete': not unexecuted, 'pipeline_validation_passed': pipeline_ok, 'slice_pass_rate': overall, 'layer_metrics_passed': layer_ok, 'executed_layer_metrics': len(layer_checks)}}
    return report
_DEMO_QUESTION = '我的低密度脂蛋白胆固醇 4.2 mmol/L 偏高，适合做什么运动？'
_DEMO_REPORT = '低密度脂蛋白胆固醇参考区间为 <3.4 mmol/L，4.2 mmol/L 属于偏高[1]。建议以中等强度有氧运动为主，每周累计 150 分钟以上[2]。合并他汀用药者运动时应关注肌痛[3]。'
_DEMO_CLAIMS = [{'claim_id': 'c1', 'type': 'fact', 'text': '低密度脂蛋白胆固醇 4.2 mmol/L 偏高', 'evidence_ids': ['e1']}, {'claim_id': 'c2', 'type': 'fact', 'text': '中等强度有氧运动每周 150 分钟', 'evidence_ids': ['e2']}, {'claim_id': 'c3', 'type': 'inference', 'text': '该用户应优先进行有氧运动', 'evidence_ids': []}]
_DEMO_EVIDENCE = [{'evidence_id': 'e1', 'quote': '体检指标 低密度脂蛋白胆固醇 参考区间 <3.4 mmol/L'}, {'evidence_id': 'e2', 'quote': '推荐以中等强度有氧运动为主，每周累计 150 分钟以上'}]
_DEMO_RETRIEVED = ['m_LDL_C', 'noise_1', 'g1']
_DEMO_RELEVANT = {'m_LDL_C', 'g1'}

def main():
    argv = sys.argv[1:]
    gate = '--gate' in argv
    json_out = '--json' in argv
    ci_mode = '--ci' in argv
    if ci_mode:
        logging.basicConfig(level=logging.ERROR)
    retrieval_mode = 'auto'
    if '--retrieval-mode' in argv:
        retrieval_mode = argv[argv.index('--retrieval-mode') + 1]
    report = run_all(gate_mode=gate, retrieval_mode=retrieval_mode)
    if not ci_mode:
        print(f"\n=== 评测总报告 {report['eval_version']} ===")
        s = report['slices']
        print(f"行为切片: {s['passed']}/{s['executed']} ({s['pass_rate']:.0%})  跳过 {s['skipped']}（依赖未就绪）")
        ret = report['retrieval']
        if ret.get('status') == 'unavailable':
            print(f"检索质量: 不可用（{ret['error']}）")
        else:
            agg = ret['aggregated']
            print(f"检索质量(mode={ret['mode']}): recall@5={agg.get('recall@5')} mrr={agg.get('mrr')} 空召回={agg.get('empty_recall_rate')}")
        print(f"生成质量(judge={report['generation']['judge_mode']}): faithfulness={report['generation']['faithfulness']} citation_acc={report['generation'].get('citation_accuracy')}")
        checks = report.get('layer_gate_checks') or []
        if checks:
            print('层指标门禁:')
            for c in checks:
                mark = '✅' if c['passed'] else '❌'
                print(f"  {mark} [{c['layer']}] {c['metric']}={c['value']} (阈值 {c['threshold']})")
        else:
            print('层指标门禁: 无已执行指标')
        for note in report.get('unexecuted_metrics') or []:
            print(f'  ⚠️ 未执行（阻止门禁通过）: {note}')
        print(f"行为切片通过率: {report['overall_pass_rate']:.0%} (阈值 {GATE_THRESHOLD:.0%})｜层指标: {('全部达标' if report['gate']['layer_metrics_passed'] else '有未达标项')} → {('✅ 通过' if report['gate']['passed'] else '❌ 未通过')}")
    if json_out or ci_mode:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if (gate or ci_mode) and (not report['gate']['passed']):
        sys.exit(1)
    sys.exit(0)
if __name__ == '__main__':
    main()
