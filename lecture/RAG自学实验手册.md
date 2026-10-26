# RAG 实验（9 个）

所有命令在 `python-ai` 目录下执行（除实验 1 的启动部分）。报告都在 `app/eval/reports/` 下。

---

## 实验 1：部署启动

**目的**：把整条链路跑起来，确认服务都活着。

**操作**：

```bash
# 进入项目根目录
cd /niceoffer/src/LLMHealthyAssistant

# 安装依赖（必须带 --extra dev）
cd python-ai
uv sync --extra dev

# 回根目录一键启动（PG/Redis/Milvus/MinIO + 四层服务，含建表、灌语料、发版本、重建索引）
cd ..
./start.sh

# 验证
curl -s http://localhost:8080/healthz    # 返回 OK
pgrep -f grpc_server.py                  # 有 PID
```

索引手动重建的标准命令（后面实验弄坏索引后都用它恢复）：

```bash
cd python-ai && uv run python -m app.retrieval.index_builder --rebuild --version kv_20260915_001
```

---

## 实验 2：文档解析三通道

**目的**：看同一张体检报告图片，OCR 和 VLM 两个通道各自解析出什么、冲突时系统怎么裁决。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 全链演示：OCR → 坐标还原 → 行解析 → VLM → JSON 提取 → 合并裁决 → 置信度
# 结果有缓存，第一次真实调 API，之后免费重跑
uv run python ../lecture/demo_channels.py "../测试图像 2.png"
```

对照输出里这三段：③ OCR 通道产出多少条指标、④ VLM 通道产出多少条、⑥ 合并裁决里哪条被拒绝（日志里有 `拒绝入库 身高=5.12 ... 采信 VLM`）。

---

## 实验 3：chunking 六策略对比

**目的**：同一批语料换六种切块方式，看检索指标差多少；体会"字段完整才算召回"。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 一次跑六策略对比（baseline / fixed_length / fixed_symbol / semantic_window / semantic_split / structured_row）
uv run python -m app.eval.chunk_bench
```

换策略跑单策略验证（环境变量切换，零改码）：

```bash
export CHUNK_STRATEGY=fixed_length
# 依次换：fixed_symbol / semantic_window / semantic_split
```

改窗口上限看截断损失：编辑 `app/eval/chunk_bench.py` 顶部 `CHUNK_MAX = 400`，改成 200 跑一次、800 跑一次，改回 400。

报告：`app/eval/reports/chunk_bench_<日期>.json`，看 `recall@5` / `mrr` / `hit@1`。

---

## 实验 4：embedding 对比 + 缓存收益 + 维度守卫

**目的**：换 embedding 模型看质量差多少；看缓存命中前后的延迟差；亲眼看配错维度被守卫拦下。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 1. 单模型基线
uv run python -m app.eval.embedding_bench

# 2. 多模型对比（模型名换成你 Key 里可用的）
uv run python -m app.eval.embedding_bench --models BAAI/bge-m3,Qwen/Qwen3-Embedding-0.6B

# 3. 缓存收益：连跑两次，对比冷/热延迟
source ../.env && uv run python -m app.eval.cache_bench
source ../.env && uv run python -m app.eval.cache_bench
```

维度守卫（会动到索引，先备份 `.env`）：

```bash
# 备份
cp ../.env ../.env.bak

# 把 ../.env 里 EMBEDDING_DIM 改成 999，然后重建索引——观察当场报错
uv run python -m app.retrieval.index_builder --rebuild --version kv_20260915_001

# 还原 .env，再跑一次上面的重建命令恢复索引
mv ../.env.bak ../.env
```

---

## 实验 5：索引选型与扫参

**目的**：对比 HNSW 和 IVF_SQ8 在召回 / 延迟上的取舍；扫 `ef` / `M` 参数。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 1. 当前索引参数基线
uv run python -m app.eval.index_tuning

# 2. 扫参
uv run python -m app.eval.index_tuning --ef 32,64,128 --M 16

# 3. 无 key 预览
uv run python -m app.eval.index_tuning --dry-run

# 固定 IVF_SQ8 的 nlist=128，用100条不同查询比较五组 nprobe（独立临时集合）
uv run python -m app.eval.index_tuning --index-type IVF_SQ8 --nlist 128 --nprobe 4,8,16,32,64 --num-queries 100 --json

# 将 nlist 增大到512，使用相同100条查询重测
uv run python -m app.eval.index_tuning --index-type IVF_SQ8 --nlist 512 --nprobe 4,8,16,32,64 --num-queries 100 --json

# 预览 IVF_SQ8 参数，不连接外部服务
uv run python -m app.eval.index_tuning --index-type IVF_SQ8 --dry-run
```

换索引类型（会动到索引）：把 `../.env` 里 `PAPERS_INDEX_TYPE` 从 `IVF_SQ8` 改成 `IVF_FLAT`，跑实验 1 里的重建命令，再跑 `index_tuning` 对比；测完改回 `IVF_SQ8` 再重建一次。

---

## 实验 6：召回——单通道 vs 多路融合

**目的**：对比 SQL / BM25 / Dense 各通道和混合检索的指标；看 RRF K 值的影响；对比 BM25 两种实现。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 1. 主评测：92 条预标注查询，单通道 vs hybrid
uv run python -m app.eval.real_eval
# 快速版（前 10 条）：
uv run python -m app.eval.real_eval --limit 10
# 难负例子集 / 主题语义子集：
uv run python -m app.eval.real_eval --hard
uv run python -m app.eval.real_eval --topic

# 2. BM25 两种实现对比：Milvus 全文 vs PG LIKE 回退
uv run python -m app.eval.bm25_bench

# 3. RRF K 值扫描
uv run python -m app.eval.rrf_tuning

# 4. 检索基准（含空召回率、通道覆盖率）
uv run python -m app.eval.retrieval_bench --mode real
```

---

## 实验 7：rerank

**目的**：对比 RRF only 和 RRF + Cross-Encoder 精排的指标与延迟。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 真实调 /rerank
uv run python -m app.eval.rerank_bench

# 无 key 预览
uv run python -m app.eval.rerank_bench --dry-run
```

---

## 实验 8：HyDE

**目的**：对比原始 query 和"假设文档"检索的效果；验证生产默认关闭的 HyDE 是否值得开。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 需要 LLM Key，先 source 环境变量
source ../.env && uv run python -m app.eval.hyde_bench
```

对照读数：`recall@10` / `mrr` / 额外延迟 / token 成本。

相关代码 `app/retrieval/hyde.py`：只替换 Dense 向量（BM25 仍用原 query）、`strip_numbers()` 剥离假设文档里的数字、失败回退原 query。

---

## 实验 9：端到端门禁

**目的**：全链路跑通 9 类行为切片门禁，确认退出码；把前面实验选出的参数组合起来复测。

**操作**：

```bash
cd /niceoffer/src/LLMHealthyAssistant/python-ai

# 汇总报告
uv run python -m app.eval.run

# 门禁模式（行为切片通过率 < 0.8 → 退出码 1）
uv run python -m app.eval.run --gate

# CI 模式
uv run python -m app.eval.run --ci
```

综合复测：把你选出的 `CHUNK_STRATEGY` / `ef` / RRF K 值组合配置好，重跑实验 3 → 6 → 7，对比默认配置的指标。
