# Issue Agent

开发者 Issue 分诊与辅助修复：先只读看清问题，再提出补丁，人批准后才写入，并留下可回放记录。

当前**不会**自动改仓库、不会跑任意 Shell、不会在未批准时写入。

## 准备

```powershell
python -m pip install -r requirements.txt
```

模型调用需要环境变量 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。可参考 `.env.example`，不要把密钥提交进仓库或贴到聊天里。

`--workspace` 和 `--out-dir` 必须是绝对路径。

## 推荐：一条工作流

分诊 → 提案 → 预演（不写仓库）：

```powershell
python -m app.issue --workspace "D:\path\to\repo" --issue-file issue.txt --out-dir "D:\path\to\out"
```

输出目录里会有 report.json、patch.json、verify.json、对应 trace 和 summary.json。

预演通过后真正写入（仍须点名文件）：

```powershell
python -m app.issue --workspace "D:\path\to\repo" --issue-file issue.txt --out-dir "D:\path\to\out" --allow-write notes.py --apply
```

没有 `--apply` 时，目标仓库不会被修改。

## 拆开用

```powershell
python -m app.triage --workspace "D:\path\to\repo" --issue-file issue.txt --out report.json --trace-out triage-trace.json
python -m app.propose --workspace "D:\path\to\repo" --issue-file issue.txt --out patch.json --verify --trace-out propose-trace.json
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py --apply
python -m app.trace_show --trace-file propose-trace.json
python -m app.trace_replay --workspace "D:\path\to\repo" --trace-file propose-trace.json
```

## 测试

```powershell
python -m pytest -q
```

## 不要用

- `app/demo_read_file.py`：阶段一 demo，不是产品入口
- 已作废的空 prompts.py / schemas.py（不再使用）
