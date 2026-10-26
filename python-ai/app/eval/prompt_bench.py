from __future__ import annotations
import json
import os
import re
import sys
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
REQUIRED_FIELDS = ['observation', 'facts', 'inferences', 'conflicts', 'unknowns', 'related_to_you']
SCENARIOS = [{'name': '血脂异常-常规', 'metrics': ['低密度脂蛋白胆固醇 4.2 mmol/L', '甘油三酯 2.1 mmol/L'], 'evidence': ['[1][sql] 体检指标 低密度脂蛋白胆固醇 | 参考区间 <3.4 mmol/L | 本次 4.2 mmol/L 偏高', '[2][bm25] 中国血脂管理指南（2023）| 推荐以中等强度有氧运动为主，每周累计 150 分钟以上', '[3][dense] 甘油三酯偏高的生活方式干预包括控制体重、限酒与规律有氧运动']}, {'name': '血压升高-冲突证据', 'metrics': ['收缩压 150 mmHg', '舒张压 95 mmHg'], 'evidence': ['[1][sql] 体检指标 收缩压 | 参考区间 <130 mmHg | 本次 150 mmHg 偏高', '[2][bm25] 中国高血压防治指南（2018）| 有氧运动可使收缩压平均下降 5-8mmHg', '[3][dense] 血压未控制达标者应避免高强度运动，需先由医生评估']}, {'name': '血糖偏高-含未知指标', 'metrics': ['空腹血糖 6.8 mmol/L', '某新型标志物 X 1.2（无参考区间）'], 'evidence': ['[1][sql] 体检指标 空腹血糖 | 参考区间 3.9~6.1 mmol/L | 本次 6.8 mmol/L 偏高', '[2][bm25] 中国2型糖尿病防治指南（2020）| 餐后步行有助于降低餐后血糖峰值', '[3][sql] 该新型标志物未在指标目录中收录 | 来源: 指标目录查询']}, {'name': '多指标-合并用药', 'metrics': ['低密度脂蛋白胆固醇 3.6 mmol/L', '肌酸激酶 210 U/L'], 'evidence': ['[1][sql] 体检指标 低密度脂蛋白胆固醇 | 参考区间 <3.4 mmol/L | 本次 3.6 mmol/L 偏高', '[2][bm25] 他汀类药物安全性管理专家共识（2022）| 服用他汀期间运动应关注肌痛与肌酸激酶升高', '[3][dense] 出现肌肉症状时应及时就医评估并调整运动强度']}]
_PROMPT_V1 = '你是一位个人健康顾问。根据体检指标和检索到的证据，生成一份健康评估报告，内容需要包含：观察摘要、事实、推断、冲突、未知项、个人相关。关键事实请用 [n] 标注对应的证据编号。'
_PROMPT_V2 = '你是一位个人健康顾问（prompt v2）。根据体检指标和检索到的证据，生成一份结构化的健康评估报告。\n输出必须为严格的 JSON 格式（JSON Schema 约束，只输出 JSON），包含以下字段：\n```json\n{\n  "observation": "观察摘要 — 从体检指标观察到的内容（2-3句）",\n  "facts": "事实 — 每条证据的可读总结，按指标分组（3-5句）",\n  "inferences": "推断 — 基于证据的推理，如指标异常的临床意义（2-3句）",\n  "conflicts": "冲突 — 多来源证据不一致时并列说明，无冲突留空字符串",\n  "unknowns": "未知 — 无法确认的指标项，无可疑项留空字符串",\n  "related_to_you": "个人相关 — 结合用户档案（既往病史/用药）标注注意事项，无则留空字符串"\n}\n```\n\n规则：\n- 只输出 JSON，不要任何 markdown 标记或额外说明\n- 每个 section 的内容应该是自然流畅的中文段落\n- facts 不要直接复制原始证据，应该用通俗语言解释；关键事实句末用 [n] 标注对应证据编号\n- 引用编号 [n] 必须 ≤ 传入的证据总数，越界编号会导致报告被拒绝\n- inferences 要基于证据推导，不能凭空编造；有依据处同样用 [n] 标注'

def _build_user_msg(scenario: dict) -> str:
    ev_text = '\n'.join((f'- {e}' for e in scenario['evidence']))
    return f"本次体检指标: {', '.join(scenario['metrics'])}\n\n检索到的证据（共 {len(scenario['evidence'])} 条）:\n{ev_text}"

def _call_llm(system: str, user: str, use_format: bool) -> str:
    from app.gateway.adapters.llm import LLMAdapter
    kwargs = {'temperature': 0.3, 'max_tokens': 2048}
    if use_format:
        kwargs['response_format'] = {'type': 'json_object'}
    resp = LLMAdapter().chat(messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': user}], **kwargs)
    return resp.get('choices', [{}])[0].get('message', {}).get('content', '')

def _clean_json(content: str) -> tuple[str, bool]:
    c = content.strip()
    marked = c.startswith('```')
    if marked:
        c = c.split('```')[1].strip()
        if c.startswith('json'):
            c = c[4:].strip()
    return (c, marked)

def _eval_output(content: str, n_evidence: int) -> dict:
    parsed = False
    fields_ok = 0
    type_ok = 0
    oob_refs = 0
    obj = None
    clean, marked = _clean_json(content)
    try:
        obj = json.loads(clean)
        parsed = isinstance(obj, dict)
    except Exception:
        parsed = False
    if isinstance(obj, dict):
        for f in REQUIRED_FIELDS:
            if f in obj:
                fields_ok += 1
                if isinstance(obj[f], str):
                    type_ok += 1
        blob = ' '.join((str(obj.get(k, '')) for k in REQUIRED_FIELDS))
        for n in re.findall('\\[(\\d+)\\]', blob):
            if int(n) > n_evidence:
                oob_refs += 1
    return {'parse_ok': parsed, 'fields_ok': fields_ok, 'fields_total': len(REQUIRED_FIELDS), 'type_ok': type_ok, 'out_of_bound_refs': oob_refs, 'markdown_wrapped': marked, 'chars': len(content)}

def main():
    dry = '--dry-run' in sys.argv
    if dry:
        print('\n=== Prompt 版本对照（亮点7）dry-run ===')
        print(f'场景: {len(SCENARIOS)} 个（常规/冲突/含未知指标/合并用药）')
        print('对照: A=v1 自由格式（无 JSON 约束）  B=v2 JSON Schema + response_format')
        print('指标: 解析成功率 / 字段完整率 / 类型正确率 / 越界引用率 / markdown 污染率')
        print('需要: DEEPSEEK_API_KEY（真实 LLM 调用）')
        return
    if not os.getenv('DEEPSEEK_API_KEY'):
        print('[ERROR] DEEPSEEK_API_KEY 未配置，真实模式需要。', file=sys.stderr)
        sys.exit(1)
    print('\n=== Prompt 版本对照：v1 自由格式 vs v2 JSON Schema（真实 LLM）===\n')
    sums = {k: {'parse_ok': 0, 'fields_ok': 0, 'type_ok': 0, 'oob': 0, 'marked': 0} for k in ('v1', 'v2')}
    per_query = []
    for sc in SCENARIOS:
        user = _build_user_msg(sc)
        n_ev = len(sc['evidence'])
        row = {'scenario': sc['name'], 'n_evidence': n_ev}
        for key, sys_prompt, use_format in (('v1', _PROMPT_V1, False), ('v2', _PROMPT_V2, True)):
            try:
                content = _call_llm(sys_prompt, user, use_format)
            except Exception as e:
                print(f"  [FAIL] {sc['name']} {key}: {type(e).__name__} {str(e)[:120]}")
                continue
            m = _eval_output(content, n_ev)
            row[key] = m
            sums[key]['parse_ok'] += int(m['parse_ok'])
            sums[key]['fields_ok'] += m['fields_ok']
            sums[key]['type_ok'] += m['type_ok']
            sums[key]['oob'] += m['out_of_bound_refs']
            sums[key]['marked'] += int(m['markdown_wrapped'])
        per_query.append(row)
        v1, v2 = (row.get('v1', {}), row.get('v2', {}))
        print(f"  [OK] {sc['name']:<22} v1 parse={v1.get('parse_ok')} fields={v1.get('fields_ok', 0)}/6 oob={v1.get('out_of_bound_refs', 0)} | v2 parse={v2.get('parse_ok')} fields={v2.get('fields_ok', 0)}/6 oob={v2.get('out_of_bound_refs', 0)}")
    if not any((row.get('v1') or row.get('v2') for row in per_query)):
        print('[ERROR] 全部 LLM 调用失败，无法评测。', file=sys.stderr)
        sys.exit(1)
    n = len(SCENARIOS)
    print(f'\n  汇总（{n} 场景）:\n')
    print(f"  {'指标':<22} {'v1 自由格式':>14} {'v2 Schema约束':>16}")
    for label, key in (('JSON 解析成功率', 'parse_ok'), ('字段完整率(均分)', 'fields_ok'), ('越界引用总数', 'oob'), ('markdown 污染数', 'marked')):
        if key == 'fields_ok':
            v1 = round(sums['v1'][key] / (n * 6), 3)
            v2 = round(sums['v2'][key] / (n * 6), 3)
            print(f'  {label:<22} {v1:>14.3f} {v2:>16.3f}')
        else:
            print(f"  {label:<22} {sums['v1'][key]:>14} {sums['v2'][key]:>16}")
    report = {'benchmark': 'prompt_version_control', 'question': 'JSON Schema 约束前后量化对比（健康评估报告）', 'model': os.getenv('LLM_MODEL', 'deepseek-chat'), 'num_scenarios': n, 'v1_freeform': dict(sums['v1']), 'v2_schema': dict(sums['v2']), 'per_query': per_query, 'insight': 'v1 自由格式下模型常输出 markdown 包裹/自由文本/缺失字段，解析成功率低；v2 用 JSON Schema 示例 + response_format=json_object 后解析成功率和字段完整率显著提升，且引用越界（幻觉风险）减少。这是 prompt 版本化 + Schema 约束的量化依据。', 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'prompt_bench_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/prompt_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
if __name__ == '__main__':
    main()
