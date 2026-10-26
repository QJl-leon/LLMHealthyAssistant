# 500 篇论文脚本

本目录集中保存两份 ZIP 共 500 篇论文的解析记录、补解析、核验、报告、六策略分块和向量导入脚本。脚本从自身位置定位项目，可从任意工作目录执行；命令中的相对参数路径仍以当前工作目录为准。

| 脚本 | 用途 | 输出 / 影响 |
| --- | --- | --- |
| `run_parse.py` | 调用原项目解析器处理两个 ZIP 并导出正文 | 更新 PostgreSQL，写入工作区 `实验2_解析结果/` |
| `recover_empty_paper.py` | 用 PDFium 补解析 PMC13131944 | 更新 PostgreSQL 及解析产物；需要已安装的 `pypdfium2` |
| `verify_results.py` | 核对 500 篇数据库记录与正文导出 | `实验2_解析结果/verification.json` |
| `render_report.py` | 根据解析统计更新实验 2 报告 | 工作区 `实验2_文档解析三通道_实验报告.md` |
| `chunk_papers.py` | 生成六种策略的分块 JSONL | 项目 `data/paper_chunks/<时间>/` |
| `import_vectors.py` | 读取已完成分块，生成向量及独立 Milvus 集合 | 项目 `data/paper_vectors/` 的断点文件，Milvus 中的实验集合 |
| `make_eval_set.py` | 汇合人工核对题并生成覆盖 500 篇的原文定位题 | 本目录的 `eval_set_v1.jsonl` 和校验元数据 |
| `benchmark.py` | 在六个实验集合上依次运行 Dense、BM25、RRF 检索评测 | 项目 `data/paper_bench/<时间>/` 的报告和逐题结果 |

通用生产代码继续位于 `python-ai/app/factory/ingest_papers.py` 和 `python-ai/app/retrieval/index_builder.py`，供本目录脚本复用。分块说明见 [论文六策略分块使用说明](论文六策略分块使用说明.md)，评测方法与命令见 [论文六策略检索评测说明](论文六策略检索评测说明.md)，已完成实验的统计与结论见 [500 篇论文六策略实验报告](500篇论文六策略实验报告.md)。已有数据和日志保留原位置。

## 解析、核验与分块

```bash
cd /home/ubuntu/RAG-job
LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/run_parse.py
LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/recover_empty_paper.py
LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/verify_results.py
LLMHealthyAssistant/python-ai/.venv/bin/python LLMHealthyAssistant/scripts/papers500/render_report.py

cd LLMHealthyAssistant
python-ai/.venv/bin/python scripts/papers500/chunk_papers.py
```

前四个脚本会更新现有记录或报告，只在需要重新解析、核验时执行。补解析读取主解析产物；报告读取已有解析统计。

## 导入现有六策略结果

从项目根目录执行。两次运行分别完成四种策略和剩余两种；首轮总体状态虽失败，其四种已完成策略仍可导入，`.partial` 文件不会被读取。

先离线校验，不连接数据库，也不调用 embedding API：

```bash
cd /home/ubuntu/RAG-job/LLMHealthyAssistant
python-ai/.venv/bin/python scripts/papers500/import_vectors.py \
  --chunk-dirs data/paper_chunks/20260929_000905_462742 \
               data/paper_chunks/20260929_031543_567680 \
  --long-text truncate \
  --dry-run
```

确认截断统计后，正式导入：

```bash
python-ai/.venv/bin/python scripts/papers500/import_vectors.py \
  --chunk-dirs data/paper_chunks/20260929_000905_462742 \
               data/paper_chunks/20260929_031543_567680 \
  --long-text truncate
```

必须在项目 `.env` 中配置有效的 `SILICONFLOW_API_KEY`、`EMBEDDING_MODEL`（本批分块使用 `BAAI/bge-m3`）、`EMBEDDING_DIM`（该模型为 1024）、`MILVUS_HOST`、`MILVUS_PORT`。Milvus 需支持项目已有的 BM25 Function；脚本沿用项目的 `pymilvus` 依赖。无需 PostgreSQL，不重新分块，不发布知识版本。会产生 embedding API 用量。

默认建立六个集合：`papers500_baseline`、`papers500_fixed_length`、`papers500_fixed_symbol`、`papers500_semantic_window`、`papers500_semantic_split`、`papers500_structured_row`。Dense 使用 COSINE/HNSW，Sparse 使用 BM25。`papers_lib` 保留原状；应用现有检索通道不会自动查询这些实验集合，后续评测应显式指定集合。

可用 `--strategies fixed_length semantic_window` 只导入部分策略。每种策略必须恰好有一份完整结果，校验 500 篇唯一论文、块 ID、连续块序号、版本、元数据、正文长度以及 `summary.json` 完成状态和数量。少量实验数据可显式改变 `--expected-papers`，不支持用不完整文件冒充 500 篇。

## 超长文本与实验含义

默认 `--long-text error`，超过 `--max-text-bytes 8192` 或 `--max-text-chars 6000` 就在预检阶段失败。6000 字符是可配置的字符保护值，不能替代模型 token 上限；服务端拒绝请求时会重试并停止，不能当作成功。

上面的六策略命令显式使用 `--long-text truncate`：**向量与 BM25 都基于截断后的同一段文本，结构化行不再代表完整全文检索。** 按当前默认上限离线核验，500 个结构化行中有 498 个需截断；其他五种策略均无需截断。原 JSONL 全文不修改；Milvus 保存 `text_truncated`、`original_characters`、`original_bytes`、`doc_id`、`pmcid`、`chunk_index`、策略、回退原因及论文元数据，可按原块 ID 在断点文件所记录的输入 JSONL 中追溯全文。若实验必须比较全文单块，应另行设计长文向量与外部全文存储方案，不能把此截断配置解释为全文方案。

## 重试与续跑

embedding 默认每批 16 条，失败最多重试 3 次；验证返回条数、维度、有限数值、非零向量。无效批次停止，不写入零向量。最多积累 256 条后 `upsert`、`flush`，成功后原子更新断点；失败时保留已经完成的批次。

中断后使用**同一命令加 `--resume`**。输入 SHA-256、集合签名、模型、维度、文本处理参数、版本、租户和 Milvus 地址必须一致；变更实验时使用新前缀，例如 `--collection-prefix papers500_v2`。相同块 ID 的 `upsert` 可重放未保存断点的批次。集合已存在但没有匹配的断点文件时停止，脚本没有删除集合选项；请保留 `data/paper_vectors/` 及原始分块文件。不要并发启动同一实验导入。

完成状态包括向量写入、flush、两种索引创建和集合 load。脚本生成与离线校验不代表真实 API 或 Milvus 导入已经完成。

## 离线测试

```bash
python-ai/.venv/bin/python -m pytest scripts/papers500/tests -q
python-ai/.venv/bin/python scripts/papers500/import_vectors.py --help
```
