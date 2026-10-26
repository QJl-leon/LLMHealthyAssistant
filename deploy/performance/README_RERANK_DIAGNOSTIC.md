# Mac 并发 6：重排 HTTP 诊断

上一轮六个报告都可读，但两个重排阶段发生 HTTPStatusError，因缺少状态码无法确认根因。旧失败记录保留，并发 8 没有启动。

本轮已经上线重排观测并重启 Python 服务，模型仍为 qwen3-vl-plus，重排仍为 jina-reranker-v3。50 项 Python 回归、116 项测试工具检查通过；数据库、Redis、Milvus、MinIO、gRPC、Go 和正式 HTTPS 前端检查通过。

## 本轮范围

只发一组 6 个真实合成报告任务，固定 run_id 为 mac_c6diag_20261019_c6。最多 6 个任务，不自动重试、不进入并发 8。

仅此指定 run_id 绕过重排缓存，强制观测真实重排 HTTP 调用；不读取或写入这次重排的共享缓存条目，不清空任何缓存。其他 run_id 沿用原缓存行为。此设置只服务于这次诊断，不能把结果和暖缓存基线直接混合比较。

新日志记录：供应商、模型、缓存 hit/miss/disabled/bypass、HTTP 状态码、耗时、数值型 Retry-After、异常类型和任务关联。连接或超时没有响应时状态码为 null，不伪造状态码。不记录 API Key、请求正文、查询、文档、响应正文、完整 URL 或未筛选响应头。HTTP 请求耗时不是新引入的本地排队时间；本轮未增加重试、退避或并发限流。

## Mac 准备

Mac 需要 Python 3.11+、SSH 密钥登录、稳定网络。解压到新目录，不覆盖旧结果。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r client/requirements.lock
scp ubuntu@43.165.5.253:/home/ubuntu/RAG-job/线上测试部署/测试账号.env ./client.env
chmod 600 client.env
```

可复用已有专用 client.env，不复制服务器 .env 或模型密钥。另一终端保持原监控隧道，已有正常隧道无需重复启动：

```bash
ssh -N -L 9190:127.0.0.1:9190 ubuntu@43.165.5.253
```

## 执行一次

```bash
.venv/bin/python client/run_rerank_diagnostic.py
```

脚本先检查 Mac 的网站连通性和隧道，取得新的一次性诊断登记，开启窗口，然后并发最多 6 个任务。之后检查回落、回传客户端记录、在服务器逐任务核对阶段和 HTTP 观测，再下载归档。每任务超时 300 秒；本轮系统可见 Token 软上限 180,000。在途用量可能突破软阈值，不等同供应商账单硬上限；本轮会真实调用模型并产生费用。

## 如何判断结果

- healthy_concurrency_passed：完整健康链路是否通过，任何模型阶段错误仍判失败，报告可读不能掩盖重排降级。
- diagnostic_evidence_complete：六个任务是否各有一次 scoped cache bypass 和一次真实 HTTP 尝试的日志。即便健康门禁失败，诊断证据仍可能完整。
- rerank_http_status_counts：各状态码次数；no_response 表示无 HTTP 响应，结合 error_type 判断超时或连接问题。
- rerank_http_observations：逐任务状态码、耗时、异常类型等白名单字段。

如果再次失败，客户端可能以非零退出，但仍会在任务回落后归档；不要立即重复启动或升档。即便本轮全部 200，也只能说明此轮未复现原错误，不能直接宣布根因已修复。

等待结果后：若是 429，再核对供应商限流或配额；4xx 核查权限或请求；5xx 核查上游；无响应核查超时/连接。不同错误分别处理，不盲目添加重试。

## 归档和异常

结果在 results/mac_c6diag_20261019_c6/client 和 server-archive；concurrency-validation.json 在 Mac 和服务器同 run_id 目录保存。脚本自动同步结果，不回传 client.env。

若仍有在途任务，停止并等待服务端确认回落后，仅补充导出：

```bash
.venv/bin/python client/run_rerank_diagnostic.py --batch 1 --finalize
```

finalize 不创建任务，不重置失败批次。Mac 退出或休眠不代表后端模型调用已取消。

已知 Triglycerides 空格导致重复指标的问题未修，本轮只诊断重排异常，不验收内容准确性、容量极限、稳定 P95、长稳或故障恢复。原正式 ready_for_load=false 保留；本轮是明确授权的受控诊断。
