# Mac 真实单任务基线

线上已按用户要求切换为 `qwen3-vl-plus`，完成一次服务器本机真实任务复验：报告发布、保存和读取成功，模型阶段无错误，从上传前到报告可读约 23.25 秒、21,377 Token。这不是 Mac 基线或稳定 P95。新版客户端锁定该模型，并检查 OCR、VLM、报告生成和保存的阶段证据。

此包自带固定英文合成报告，不包含真实患者信息或任何凭证。Python 3.11+；依赖沿用客户端已验证版本。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r client/requirements.lock
scp ubuntu@43.165.5.253:/home/ubuntu/RAG-job/线上测试部署/测试账号.env ./client.env
chmod 600 client.env
```

在另一终端保持监控隧道：

```bash
ssh -N -L 9190:127.0.0.1:9190 ubuntu@43.165.5.253
```

先执行 1 次远程验证/预热：

```bash
.venv/bin/python client/run_single.py --run-id mac_qwen3_20261019_warmup_001
```

协调器自动执行：SSH 就绪检查、窗口 begin、固定样本的一个真实报告任务、检查任务回落、窗口 finish、下载服务端归档并回传客户端结果。对源样本做 SHA-256 校验；遇到模型阶段错误或不确定任务状态返回非零，停止后续测量。发布确认仅针对本合成测试任务自动执行。

首轮无错误通过后执行 5 次串行测量：

```bash
for i in 01 02 03 04 05; do
  .venv/bin/python client/run_single.py --run-id "mac_qwen3_20261019_measure_${i}" || break
done
```

每个进程限 1 个任务、并发 1、300 秒超时；不是容量测试。每轮可见 Token 30,000 为软限制，在途用量不能靠脚本保证不超出。使用专用账号并事先核对模型费用预算。

如果服务器尚有在途任务，不会关闭窗口或创建下一轮。确认回落后，对同一 run_id 补充导出，不创建任务：

```bash
.venv/bin/python client/run_single.py --run-id mac_qwen3_20261019_measure_01 --finalize
```

每次使用新 run_id，不能覆盖旧目录。Mac 结果在 `results/<run_id>/client`，服务端归档在同级 `server-archive`。不要上传 `client.env`。SSH 断开、关闭终端或 Mac 休眠不证明服务器模型调用已经取消。

汇总 5 个正式样本，不加入预热：

```bash
.venv/bin/python client/baseline_report.py \
  --clients results/mac_qwen3_20261019_measure_*/client \
  --server-root results --origin remote-mac --out mac-single-report-baseline.md
```

汇总比对样本及应用/模型配置，不混合本机与 Mac 测量；列中位数、最小值、最大值。5 个样本不足以宣布稳定 P95。图像样本为清晰的单张英文合成表格，不能推广为中文照片、多图或生产容量结论。
