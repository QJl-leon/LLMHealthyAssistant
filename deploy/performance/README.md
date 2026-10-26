# 本地测试工具与 Mac 远程接入

当前只有一套线上服务。Mac 是客户端负载机，不是另一套服务端测试实例。

已配置：服务器只读就绪检查、测试窗口导出、远程 HTTPS/SSE 客户端、资源停发条件和测试配置。当前合成图片探针可用；另已准备受控真实单任务模式，需模型可用性和就绪检查通过。原模型首次真实任务出现 VLM 404；现已切换 qwen3-vl-plus 并完成健康链路本机复验，可按 README_SINGLE.md 进行单任务 Mac 测量。并发容量、4–8 小时长稳及服务端故障注入未启用。

## 服务器侧

在项目根目录执行：

```bash
python-ai/.venv/bin/python deploy/performance/preflight.py --out ../线上测试部署/results/server-readiness.json

# 每轮使用新 run_id，开始前登记
python-ai/.venv/bin/python deploy/observability/run_record.py begin mac_smoke_20261019_001

# Mac 完成测试，确认任务结束后导出
python-ai/.venv/bin/python deploy/observability/run_record.py finish mac_smoke_20261019_001
```

`ready_for_smoke=true` 代表可执行单任务质量门禁探针；`ready_for_load=false` 必须保留实际阻塞项，不能改 JSON 绕过。强制认证、版本、数据库迁移、权限与真实报告链路验收、独立目标均通过后才能正式加压。

窗口工具支持 `--project-root`、`--output-root`、`--prometheus-url`、`--containers`、`--nginx-log`，全局参数写在 `begin/finish` 前。导出格式已升级为 v2：`metrics.jsonl.gz` 按 30 分钟分块，包含应用和 Milvus 原生指标；另导出任务关联日志、Nginx 日志和资源日志，以及源码、二进制、前端、迁移配置快照。源文件哈希不能证明 Python 已加载模块的版本。

## Mac 客户端准备

需要 Python 3.11 或更新版本、终端、SSH/SCP，以及访问网站的稳定网络。浏览器可用于人工功能检查，不能代替持续负载脚本。

从服务端下载客户端压缩包、校验文件并解压。进入解压后的 `rag-performance-client` 目录：

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r client/requirements.lock
```

从服务器单独复制专用测试账号文件到 `client.env`，权限设为 0600。客户端只需要以下字段，不需要服务器 `.env`、JWT 密钥、数据库密码或模型 API Key：

```dotenv
RAG_BASE_URL=https://www.smproject.site
RAG_TEST_EMAIL=<专用测试邮箱>
RAG_TEST_PASSWORD=<专用测试密码>
RAG_TEST_TENANT_ID=<测试账号所属租户>
RAG_PROMETHEUS_URL=http://127.0.0.1:9190
```

同一次测试必须由 Mac 和服务器使用完全相同的 run_id。当前可执行：

```bash
.venv/bin/python client/load_client.py \
  --config config/smoke.json \
  --env-file client.env \
  --run-id mac_smoke_20261019_001 \
  --out results/mac_smoke_20261019_001
```

该命令只创建一个合成 1×1 图片任务，预期状态 `awaiting_images`、模型调用数 0；不生成报告、不测报告延迟。若模型调用数不为 0 或结果异常，客户端判为失败。这里的请求数也不能作为容量结论。

若结果文件夹已存在，使用新 run_id 和新目录；不要覆盖上一轮结果，也不要在旧任务未确认结束时自动重试。

## 监控访问

在 Mac 的另一终端保持 SSH 隧道：

```bash
ssh -N -L 9190:127.0.0.1:9190 ubuntu@43.165.5.253
```

浏览器访问 `http://127.0.0.1:9190`。单次 smoke 不依赖此隧道；后续正式负载客户端使用它读取资源指标，监控不可用时停发新任务。无需开放 9108、9109、9110 或 9190 公网端口。

## 后续负载配置

| 配置 | 用途 | 当前状态 |
| --- | --- | --- |
| `smoke.json` | 1 个合成质量门禁任务 | 可用 |
| `baseline.json` | 单任务真实报告基线 | 模板，未启用 |
| `capacity.json` | 固定并发；调整 1、2、3、4 等档位 | 模板，未启用 |
| `arrival.json` | 固定到达率 | 模板，未启用 |
| `soak.json` | 4 小时持续到达；8 小时需同步调整时长和总任务上限 | 模板，未启用 |
| `fault-client.json` | 一次客户端断线后带事件 ID 重连 | 仅隔离目标可启用，不包含服务端故障命令 |

正式负载必须指向独立服务端，提供一小时内产生且目标地址匹配的成功就绪报告：

```bash
.venv/bin/python client/load_client.py \
  --config config/baseline.json --env-file client.env \
  --readiness server-readiness.json \
  --run-id baseline_001 --out results/baseline_001
```

当前生产域名只允许 smoke，以及通过独立就绪检查且严格限 1 个任务的 single_report 模式；closed/arrival 负载仍拒绝。改配置中的 environment 字段不能解除负载保护。

正式测试前复制 `config/samples.example.json` 为 `config/samples.json`，放置真实脱敏样本并调整路径；模板中的图片文件不存在，不能直接开跑。报告容量测试先只保留有效报告样本，避免质量拦截掩盖报告生成成本。多样本按 weight 抽样；补图样本使用 new_images。支持补图和固定次数的发布确认；遇到未预期的记忆确认或其他人工中断会停发，要求人工处理，不假装报告已完成。

配置中的任务数、时长、并发、未完成任务数和可见 Token 总量均有限。到达率模式达到未完成任务上限时记录未发出的计划任务，不静默丢弃；记录调度延误。Token 是完成后可观察的软限制，在途用量可能超出；金额硬上限需在模型供应商侧单独设置。配置内的数值只是模板，必须根据真实单任务基线与费用预算调整。

## 停发与结果

正式负载启用前先检查监控。运行中依据内存、磁盘、CPU 与排队、队列增长、依赖不可用、容器 OOM/重启、失败比例、未完成任务和 Token 预算停发。停止新增任务时不立即取消在途任务，等待其结束或超时；不确定任务状态会停止下一轮并要求服务器核对。

客户端结果：`run-config.json`、`tasks.jsonl`、`client-events.jsonl`、`summary.json`。不保存密码、Token、模型正文和图片内容；事件仅保存类型、时间、序号。报告可读结果才统计为报告完成；等待补图单列。Mac 上退出脚本或合盖不能证明服务器任务已取消，必须核对在途任务。

当前无独立实例，因此不提供可直接在生产执行的重启、停数据库、断依赖、OOM 或填盘脚本。相应故障实验尚未具备执行条件。

真实单任务基线操作另见 [README_SINGLE.md](README_SINGLE.md)，使用单独的新客户端包，原 smoke 包及其校验值保持不变。
