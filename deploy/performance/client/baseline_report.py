#!/usr/bin/env python3
"""Summarize sequential single-report runs; never merge local/Mac observations."""
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
import statistics


FIELDS = [('upload_seconds','上传'),('create_api_seconds','创建接口'),
          ('first_business_event_seconds','首业务事件（从上传前计时）'),
          ('first_content_seconds','首有效内容（从上传前计时）'),
          ('report_readable_seconds','报告可读（从上传前计时）'),
          ('create_to_report_seconds','创建成功至报告可读'),('elapsed_seconds','流程含用量核对')]


def collect(client_dirs, server_root, excluded):
    tasks=[];stages=[];hashes=set();versions=set();origins=set()
    for directory in client_dirs:
        config=json.loads((directory/'run-config.json').read_text())
        origins.add(config.get('measurement_origin','unspecified'))
        hashes.add(json.dumps(config.get('sample_files_sha256',{}),sort_keys=True))
        for line in (directory/'tasks.jsonl').read_text().splitlines():
            row=json.loads(line)
            if row['run_id'] in excluded:continue
            archive=server_root/row['run_id']
            if (directory.parent/'server-archive').is_dir():archive=directory.parent/'server-archive'
            manifest=archive/'run.json'
            if manifest.exists():
                deployed=json.loads(manifest.read_text())
                env=deployed.get('environment',{})
                application={k:v for k,v in env.get('files_sha256',{}).items()
                             if k.startswith(('python-ai/app/','go-backend/','.run/'))}
                versions.add(json.dumps({'files':application,'models':env.get('model_config',{})},sort_keys=True))
            events=archive/'task-events.jsonl.gz'
            if events.exists():
                with gzip.open(events,'rt') as stream:
                    task_events=[json.loads(r) for r in stream]
                selected=[r for r in task_events if r.get('task_id')==row.get('task_id') and r.get('event')=='stage_end']
                row['stage_errors']=[{'stage':r.get('stage'),'error_type':r.get('error_type')} for r in selected if r.get('outcome')=='error']
                seen={r.get('stage') for r in selected}
                row['missing_required_stages']=sorted({'model.ocr','model.vlm','orchestrator.report_draft','save_report'}-seen)
                row['server_evidence_present']=True
                stages.extend(selected)
            else:
                row['stage_errors']=[]
                row['missing_required_stages']=['server_evidence']
                row['server_evidence_present']=False
            row['healthy_baseline']=(row.get('success') is True and row.get('status')=='published'
                                     and row.get('model_call_count',0)>0 and row.get('server_evidence_present')
                                     and not row['stage_errors'] and not row['missing_required_stages'])
            tasks.append(row)
    if len(hashes)>1:raise ValueError('Different sample hashes: do not combine into one baseline')
    if len(versions)>1:raise ValueError('Application/model versions differ: analyze separately')
    if len(origins-{'unspecified'})>1:raise ValueError('Local and remote measurements must not be merged')
    return tasks,stages


def render(tasks,stages,origin):
    healthy=[r for r in tasks if r['healthy_baseline']]
    rows=[f'# 单任务基线观察报告\n',f'测量来源：{origin}。',
          f'总任务：{len(tasks)}；报告成功：{sum(r.get("success",False) for r in tasks)}；无阶段错误的基线样本：{len(healthy)}。',
          '\n少量样本仅列中位数、最小值、最大值，不据此宣布稳定 P95 或容量。登录不计入任务耗时。',
          '\n## 任务结果\n','| run_id | 结果 | 模型调用 | Token | 阶段错误 |', '| --- | --- | --- | --- | --- |']
    for r in tasks:
        errors=', '.join(str(e['stage'])+':'+str(e['error_type']) for e in r['stage_errors']) or ('无' if r['server_evidence_present'] else '缺少服务端证据')
        if r.get('missing_required_stages'):errors+='; missing: '+', '.join(r['missing_required_stages'])
        rows.append(f'| {r["run_id"]} | {r.get("status",r.get("error_type","unknown"))} | {r.get("model_call_count","—")} | {r.get("total_tokens","—")} | {errors} |')
    rows.extend(['\n## 耗时（秒）\n','以下为本次全部观察值；有阶段错误的任务不能归入健康路径基线。',
                 '\n| 指标 | 样本数 | 中位数 | 最小值 | 最大值 |','| --- | --- | --- | --- | --- |'])
    for key,label in FIELDS:
        values=[r[key] for r in tasks if key in r]
        if values:rows.append(f'| {label} | {len(values)} | {statistics.median(values):.4f} | {min(values):.4f} | {max(values):.4f} |')
    per_stage=defaultdict(list)
    for r in stages:
        if r.get('duration_ms') is not None:per_stage[(r.get('stage'),r.get('outcome'))].append(r['duration_ms'])
    rows.extend(['\n## 服务端阶段观察\n','阶段耗时包含下层调用且可能重叠，不能相加作为总耗时。',
                 '\n| 阶段 | 结果 | 次数 | 中位数 ms | 最大值 ms |','| --- | --- | --- | --- | --- |'])
    for (stage,outcome),values in sorted(per_stage.items()):
        rows.append(f'| {stage} | {outcome} | {len(values)} | {statistics.median(values):.3f} | {max(values):.3f} |')
    if len(healthy)!=len(tasks):rows.append('\n存在缺失证据或阶段错误；报告可读取不代表所有模型分支正常，不建议继续批量基线测量。')
    rows.append('\nToken 为系统用量口径，可能包含估算，不等同供应商账单。原始时间戳和 run_id 保留不改写。')
    return '\n'.join(rows)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clients',nargs='+',type=Path,required=True)
    parser.add_argument('--server-root',type=Path,required=True)
    parser.add_argument('--exclude-run',action='append',default=[])
    parser.add_argument('--origin',choices=['server-local','remote-mac'],required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    tasks,stages=collect(args.clients,args.server_root,set(args.exclude_run))
    if not tasks:raise ValueError('No measurement rows')
    args.out.write_text(render(tasks,stages,args.origin))
    print(args.out)
    return 0 if all(r['healthy_baseline'] for r in tasks) else 2


if __name__=='__main__':
    raise SystemExit(main())
