# 500 篇论文分块检索测试集（v1）

数据文件：[`paper_chunk_v1.jsonl`](paper_chunk_v1.jsonl)。每行是一道有已知证据出处的问题。

## 覆盖范围

- 31 道问题，26 篇不同论文；每道都有中文和英文两种问法，可展开为 62 次查询。
- `papers_200`：9 篇论文、12 道问题；`papers_diet_advice_300`：17 篇论文、19 道问题。
- 包含 2 篇 XML 论文及 5 道证据位于 PDF 后段的问题；其余问题主要检验首页摘要中的证据。
- 所有 `evidence_anchor` 均已在本地原始 PDF/XML 中核对。PDF 文本使用与论文导入器相同的 `pdfplumber` 逐页提取；XML 文本按导入器的标签规则提取。PDF 页码从 1 开始，XML 无页码。

## 字段

| 字段 | 用途 |
| --- | --- |
| `query_zh`, `query_en` | 两种查询措辞，分别统计，避免把跨语言检索差异混进分块效果。 |
| `pmcid`, `expected_doc_id`, `source_file` | 已知相关论文、项目入库后的 UUID、原文件路径。 |
| `expected_answer_zh` | 人工核对的简短答案，用于人工复核检索证据。 |
| `evidence_page`, `evidence_anchor`, `evidence_context` | 证据在原文件中的位置和文本。后两者保留了原解析文本的连字/串列现象，便于发现解析质量问题。 |
| `source_set`, `topic`, `file_format`, `title` | 分组统计和排错用元数据。 |

`expected_doc_id` 与导入器相同，按 `uuid5(NAMESPACE_URL, "lha-papers::<PMCID>")` 计算。Milvus 子块的 `doc_id` 可用此值匹配目标论文。

## 推荐评测方式

1. 固定同一批 500 篇论文、同一知识版本、同一检索模型与参数，仅改变分块策略；每篇论文分别分块，不跨论文拼接。
2. 对每条记录分别提交 `query_zh` 和 `query_en`。记录 top-1/top-5 的子块文本、`doc_id`、`parent_key` 和排序分数。
3. **论文命中**：top-k 中至少一个子块的 `doc_id == expected_doc_id`，计算已知正例 Hit@1、Hit@5 和 MRR。
4. **证据命中**：人工检查 top-k 子块或扩展后的父块是否确实包含足以回答问题的段落；`evidence_anchor` 是定位线索，不要求它必须完整落在单个子块中。单独记录“论文命中但证据未命中”。
5. 分别汇总中文/英文、PDF/XML、首页/后段以及两批语料的结果；同时记录平均块长、块数、索引体积和检索延迟。

每题目前只标注了**一个确认相关的论文**；其他论文也可能回答同一问题。因此这些数据可测“已知正例命中率”，不能直接解释为对全部相关文献的完整 Recall。此版没有无答案题，也不足以单独证明全 500 篇的总体性能。

现有 `app.eval.chunk_bench` 读取的是健康指标目录，**不会自动加载本测试集**。如用 `app.retrieval.index_builder --papers-only --strategy ...` 做多策略实验，要注意该命令会重建并替换 `papers_lib`；先保存当前索引或使用隔离的评测集合。
