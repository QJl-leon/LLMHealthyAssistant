# Mac 两批受限并发验证

本轮固定 qwen3-vl-plus、同一专用账号和单张英文合成报告。每批并发 2、总计 2 个任务；最多两批、合计 4 个任务。不测试容量极限，不注入故障，不自动升到并发 3。

服务端登记限制批次顺序及数量，已登记批次不可重复发起；第一批成功且完全回落后才能开始第二批。任务失败、缺少日志、模型降级、没有实际重叠或延迟超过初筛目标时，都阻止进入下一批。正式 ready_for_load=false 保持不变；本模式是用户授权的线上小规模验证例外，未开放 closed/arrival 负载。

## 准备

Python 3.11+、SSH 密钥登录、SCP 和稳定 HTTPS 访问；在 Mac 上运行，保持唤醒。旧包保留，本包解压到新目录。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r client/requirements.lock
scp ubuntu@43.165.5.253:/home/ubuntu/RAG-job/线上测试部署/测试账号.env ./client.env
chmod 600 client.env
```

也可复制旧测试目录的专用 client.env。不要复制服务器 .env 或模型 API Key；不要回传 client.env。

另一终端保持 SSH 监控隧道；若旧隧道还在且正常，可继续使用，不要重复占用同一端口：

```bash
ssh -N -L 9190:127.0.0.1:9190 ubuntu@43.165.5.253
```

## 执行

先运行第一批：

```bash
.venv/bin/python client/run_concurrency.py --batch 1
```

固定 run_id 为 mac_c2_20261019_batch_01。脚本先取得服务端一次性批次登记，再开启记录窗口并发最多两个真实任务，结束后核对回落、导出、回传客户端结果、在服务端逐任务验收并下载归档。会真实调用模型并产生费用。

仅在输出 healthy_concurrency_passed=true、errors=[] 且退出码为 0 后，运行第二批：

```bash
.venv/bin/python client/run_concurrency.py --batch 2
```

固定 run_id 为 mac_c2_20261019_batch_02。服务器会再次核对上一批结果、当前空闲和模型配置。第二批结束后停止，不再追加第三批或自行修改任务量。

每批两个任务，每任务超时 300 秒；可见 Token 软上限每批 60,000、整轮 120,000。按照已有单任务均值，四个任务粗估 45,048 Token，实际可能不同；软上限不是供应商费用硬上限，在途用量可能使其被突破。

## 验收与异常

每个任务均须发布、保存、可读，有非空指标及章节、有实际用量；任务和报告 ID 不重复，预期报告版本数为 1，OCR/VLM、草稿和保存阶段均成功。服务端用两个任务的 vision_observe 起止时间计算真实重叠时长，必须大于 0。

每批记录逐任务报告耗时。中位数暂以不超过单任务基线 21.558 秒的 1.5 倍（约 32.34 秒）作为初筛目标，超出则暂停调查，不代表 SLA 或容量上限。阶段与端到端耗时分开统计。

结果在 results/<run_id>/client 和 server-archive；concurrency-validation.json 同时保留在 Mac 与服务器同 run_id 目录，最终包含 healthy_concurrency_passed、errors、server_vision_overlap_seconds、各任务报告耗时及 Token。每批结束时服务端登记状态必须为 passed，才允许下一批。

失败后不要再次执行普通启动命令，也不要改 run_id 或复制新目录重试。终端断开不证明后端调用已停止。若提示仍有在途任务，等待服务端确认回落后，仅补充导出：

```bash
.venv/bin/python client/run_concurrency.py --batch 1 --finalize
```

第二批则改为 --batch 2。finalize 不创建任务，不释放或重置已经消耗的批次额度。登记后若客户端未发出任务或窗口未建立，需要服务端核对实际状态，不能自动重新登记。此次验证结束后，任何进一步测试都需要新计划。

样本有 6 个源数据行，已有报告保存 7 条指标，其来源尚待内容核对；性能链路验收不代替提取准确性验收。本轮仅同账号固定样本，不覆盖跨用户权限、持续容量、长稳或故障恢复。
