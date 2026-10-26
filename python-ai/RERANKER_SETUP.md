# Jina / Qwen reranker 配置

推荐模型：`jina-reranker-v3`，支持中文的多语言 listwise reranker，可作为 Qwen reranker 的对照。

项目根目录 `.env` 已设置服务商、模型、接口地址和超时。仅需填写：

```dotenv
JINA_API_KEY=你的Jina密钥
QWEN_RERANK_API_KEY=你的千问AI平台密钥
```

获取密钥：https://jina.ai/api-dashboard/key-manager

Qwen 使用千问AI平台的 `qwen3-rerank`，接口为 `https://maas.qianwenaiapi.com/compatible-api/v1/reranks`。`QWEN_RERANK_API_KEY` 填写千问AI平台 Key。平台模型不能直接等同于开源 Qwen3-Reranker-0.6B，实验按实际模型名记录。模型名、地址和路径已配置。

已有 SiliconFlow Key 继续用于 Dense embedding。Jina Key 与 Qwen Key 分别使用各自服务的凭据。

从 `python-ai` 目录预览实验七配置（不发送请求）：

```bash
.venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv("../.env", override=True); from app.eval.rerank_bench import main; main()' --dry-run
# Qwen 配置预览
.venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv("../.env", override=True); from app.eval.rerank_bench import main; main()' --provider qwen --dry-run
```

填写后，从同一目录运行实验七：

```bash
.venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv("../.env", override=True); import os; os.environ.update(CACHE_ENABLED="false", HYDE_ENABLED="false", RERANK_ENABLED="false", RERANK_BENCH_KNOWLEDGE_VERSION="kv_exp6_sample"); from app.eval.rerank_bench import main; main()'
```

实验七仍显式调用重排；`RERANK_ENABLED=false` 关闭粗排阶段的隐式重排，保证前后对照有效。脚本沿用原来的六条查询和主题词相关性标签，结果写入原评测报告目录。

运行命令末尾加 `--provider qwen` 使用 Qwen，加 `--provider jina` 使用 Jina v3。不加时使用 `.env` 的默认服务商（当前为 Jina）。服务重启后可通过 `RERANKER_PROVIDER=qwen` 将应用默认精排切换到 Qwen。

代码中也可以显式选择，两组凭据与接口独立：

```python
from app.gateway.adapters.reranker import RerankerAdapter

qwen = RerankerAdapter(provider='qwen')
jina = RerankerAdapter(provider='jina')
# 填写对应 Key 后可调用：adapter.rerank(query, documents, top_k=10)
```

Qwen 接口说明：https://platform.qianwenai.com/docs/api-reference/rerank/openai-rerank

模型与接口文档：https://jina.ai/models/jina-reranker-v3/ ，https://api.jina.ai/docs
