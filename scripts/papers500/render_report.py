"""Replace only the paper parsing section using completed run evidence."""
from pathlib import Path
import json

root = Path(__file__).resolve().parents[3]
out = root / '实验2_解析结果'
summary = json.loads((out/'summary.json').read_text())
assert 'finished_at' in summary, 'Parsing must finish before updating the report'
rows = [json.loads(line) for line in (out/'paper_results.jsonl').read_text().splitlines()]
report = root/'实验2_文档解析三通道_实验报告.md'
original = report.read_text()
prefix = original.split('\n---\n\n# 补充部分：论文压缩包解析')[0]
if '> 记录范围：' not in prefix:
    prefix = prefix.replace('# 实验 2：文档解析三通道 实验报告', '# 实验 2：文档解析三通道 实验报告\n\n> 记录范围：前半部分保留旧服务器上的体检图片 OCR/VLM 实验，本次未重跑；后半部分已替换为本机两个论文压缩包重新解析的实际记录。', 1)
archives = summary['archives']
lines = [prefix.rstrip(), '', '---', '', '# 补充部分：论文压缩包解析（本机重新执行）', '', '## 本次执行信息', '',
    f"- 开始时间：`{summary['started_at']}`。", f"- 结束时间：`{summary['finished_at']}`。",
    '- 环境：Ubuntu 24.04；项目目录 `/home/ubuntu/RAG-job/LLMHealthyAssistant`。',
    f"- Python：`{summary['python']}`；pdfplumber：`{summary['pdfplumber']}`。",
    '- 数据库：本机 PostgreSQL 16，`lha` 数据库，`sources` / `parsed_documents` 表。',
    f"- 本次知识版本：`{summary['version']}`。",
    '- 目标：重新解析两份压缩包，提取正文并写入 PostgreSQL，导出正文与逐篇结果，以本机实测替换原论文解析记录。',
    '- 本次止于解析与正文入库，未执行 embedding、Milvus 索引重建或知识版本发布。', '',
    '## 输入文件核验', '', '| 压缩包 | 索引条目 | PDF | XML |', '| --- | ---: | ---: | ---: |']
for a in archives:
    lines.append(f"| `{a['archive']}` | {a['total']} | {a['pdf_files']} | {a['xml_files']} |")
lines += ['', '两个压缩包位于 `/home/ubuntu/RAG-job/`。索引中的 500 个 PMCID 均唯一，没有跨包重复；全部索引条目均能定位到对应文件。', '', '输入 SHA-256：', '']
for a in archives:
    lines.append(f"- `{a['archive']}`：`{a['sha256']}`")
lines += ['', '## 执行命令', '', '主解析阶段的记录脚本直接调用项目原有 `ingest_papers()`，没有修改解析策略；额外保存运行时间、输入校验值和数据库导出。', '', '```bash', 'cd /home/ubuntu/RAG-job', 'LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/run_parse.py', '```', '',
    '对应的原项目命令（重新执行会覆盖相同 PMCID 的解析记录）：', '', '```bash', 'cd /home/ubuntu/RAG-job/LLMHealthyAssistant', 'source scripts/local/local-env.sh', 'cd python-ai']
for a in archives:
    lines += [f"uv run --frozen --extra dev --env-file ../.env python -m app.factory.ingest_papers \\", f"  --zip ../../{a['archive']} --version {summary['version']}"]
lines += ['```', '', '## 解析策略', '',
    '1. 读取 ZIP 内 `_index.csv`，取得 PMCID、标题、期刊、年份、DOI、许可和文件路径等元数据。',
    '2. 按现有规则过滤标题或文献类型中的撤稿、勘误和更正标记。',
    '3. PDF 使用 `pdfplumber` 逐页提取文本；XML 使用 `ElementTree` 提取 abstract/body 内的标题、段落、表格和图注等文本。',
    '4. 清理不可打印控制字符，保留换行和制表符；整篇文本为空时记录并跳过。',
    '5. 以 PMCID 生成稳定 UUID5，替换同一来源的旧记录，写入 `sources` 及 `parsed_documents.content.raw_text`。', '',
    '`ingest_papers.py` 固定使用上述文本解析路径，不触发 OCR/VLM 回退；本次未调用付费模型 API。页面级异常在现有解析器内会被转为空文本，因此“成功入库”仅代表提取到非空正文，不等于逐页完整性或语义质量已全部验证。', '',
    '## 实测结果', '', '下表为原解析器完整重跑的结果，单篇 PDFium 补解析另列于后。', '', '| 压缩包 | 总条目 | 过滤 | 成功入库 | 空文本 | 文件解析失败 | 耗时（秒） |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for a in archives:
    lines.append(f"| `{a['archive']}` | {a['total']} | {a['removed_retracted']} | {a['ingested']} | {a['empty_text']} | {a['failed']} | {a['elapsed_seconds']:.3f} |")
if summary.get('recovery'):
    recovery = summary['recovery']
    lines += ['', '### 空文本论文补解析', '',
        '`PMC13131944`（Circadian biology and exercise: the time to move）的输入文件为有效 PDF。pdfplumber 返回 0 页；已安装的 PDFium 能读取 19 页，并在全部页面提取到文本，因此不能将原日志中的“可能扫描件”当作诊断结论。',
        f"补解析使用 `recover_empty_paper.py`，只对该篇采用 `pypdfium2` 提取，再通过原有入库函数写入。本次补解析成功 {recovery['ingested']} 篇，耗时 {recovery['elapsed_seconds']:.3f} 秒。",
        '原解析器成功 499 篇，加上补解析 1 篇，最终共 500 篇。原项目解析器源码未修改。', '',
        '```bash', 'cd /home/ubuntu/RAG-job', 'LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/recover_empty_paper.py', 'LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/verify_results.py', 'LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/render_report.py', '```', '',
        '诊断依据：[empty_paper_diagnostic.json](实验2_解析结果/empty_paper_diagnostic.json)；执行记录：[recovery.log](实验2_解析结果/recovery.log)。']
lines += ['', f"- PostgreSQL 本版本论文数：**{summary['database_papers']}**。", f"- 唯一 PMCID：**{summary['unique_pmcids']}**；关联到来源表的记录数：**{summary['linked_sources']}**。", f"- 已存正文中的空文本数：**{summary['empty_stored_texts']}**。", f"- 正文字符总数：**{summary['total_characters']:,}**（字符数，不是 token 数）。", f"- 单篇字符数范围：**{summary['min_characters']:,}–{summary['max_characters']:,}**。", '', '未入库条目：', '']
missing = [r for r in rows if r['status'] != 'stored']
if missing:
    lines += ['| 压缩包 | PMCID | 标题 | 结果 |', '| --- | --- | --- | --- |']
    for r in missing:
        reason = '过滤' if r['status']=='filtered' else '未入库，具体原因见解析日志'
        if f"文本为空（可能扫描件）{r['pmcid']}" in (out/'parse.log').read_text():
            reason = '提取正文为空，跳过入库'
        lines.append(f"| `{r['archive']}` | `{r['pmcid']}` | {(r['title'] or '').replace('|','/')} | {reason} |")
else:
    lines += ['无。']
lines += ['', '## 数据库核验', '', '```sql', "SELECT count(*) AS papers,", "       count(DISTINCT content->>'pmcid') AS unique_pmcids,", "       sum(length(content->>'raw_text')) AS total_characters", 'FROM parsed_documents', "WHERE kind = 'paper'", f"  AND knowledge_version = '{summary['version']}';", '```', '', f"实际结果：`papers={summary['database_papers']}, unique_pmcids={summary['unique_pmcids']}, total_characters={summary['total_characters']}`。", '', '## 执行中断与恢复', '',
    '首次运行期间 PostgreSQL 收到 fast shutdown 指令，连接被关闭，解析任务因 Connection refused 中断；容器检查为 OOMKilled=false。恢复 PostgreSQL 后从头重跑两个压缩包，最终结果以完整重跑及数据库核验为准。未确认关闭指令的来源。', f"重跑开始前数据库已有 {summary['papers_before']} 篇部分结果，项目按 PMCID 覆盖，未将这些记录重复计入最终数量。", '',
    '## 结果文件', '',
    '- [运行汇总 summary.json](实验2_解析结果/summary.json)：时间、版本、哈希、每包统计及数据库核验结果。',
    '- [独立核验 verification.json](实验2_解析结果/verification.json)：500 篇导出与数据库逐篇相同，正文哈希全部匹配。',
    '- [补解析前汇总 primary_summary.json](实验2_解析结果/primary_summary.json)。',
    '- [补解析脚本 recover_empty_paper.py](LLMHealthyAssistant/scripts/papers500/recover_empty_paper.py)。',
    '- [完整正文 parsed_papers.jsonl](实验2_解析结果/parsed_papers.jsonl)：逐篇正文、元数据、来源 ID 和内容哈希。',
    '- [逐篇状态 paper_results.jsonl](实验2_解析结果/paper_results.jsonl)：500 条索引记录的入库状态与字符数。',
    '- [完整重跑日志 parse.log](实验2_解析结果/parse.log)。',
    '- [首次中断日志 interrupted_console.log](实验2_解析结果/interrupted_console.log)。',
    '- [执行脚本 run_parse.py](LLMHealthyAssistant/scripts/papers500/run_parse.py)。', '', '## 结论', '',
    f"本机已完成两份压缩包的重新解析，共处理 {sum(a['total'] for a in archives)} 条论文索引，成功写入 {summary['database_papers']} 篇非空正文。上述数据来自本次实际运行与数据库查询，已替换旧服务器的论文解析统计；后续分块和向量化可使用知识版本 `{summary['version']}`。", '']
report.write_text('\n'.join(lines))
