# Issue Agent

受控的本地代码仓库助手：先只读分诊，再提出补丁，人批准后才写入，并留下可回放的运行记录。

当前**不会**自动改仓库、不会跑任意 Shell、不会在未批准时写入。

## 准备

在仓库根目录使用已有虚拟环境。模型调用需要环境变量 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`（不要把密钥写进仓库或贴到聊天里）。

`--workspace` 必须是**绝对路径**，且目录已存在。

## 命令

只读分诊：

```powershell
python -m app.triage --workspace "D:\path\to\repo" --issue-file issue.txt --out report.json --trace-out triage-trace.json
```

提出补丁（不写仓库）：

```powershell
python -m app.propose --workspace "D:\path\to\repo" --issue-file issue.txt --out patch.json --verify --trace-out propose-trace.json
```

预演写入（仍不改文件）：

```powershell
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py --trace-out repair-trace.json
```

真正写入：

```powershell
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py --apply --trace-out repair-trace.json
```

查看 / 重放记录（不调模型）：

```powershell
python -m app.trace_show --trace-file propose-trace.json
python -m app.trace_replay --workspace "D:\path\to\repo" --trace-file propose-trace.json
```

## 测试

```powershell
python -m pytest -q
```

## 不要用

- 空的 `app/prompts.py`、`app/schemas.py`：阶段二起已作废，分诊用 `triage_*`，修复用 `repair_*`
- `app/demo_read_file.py`：阶段一 demo，分诊与修复不要走它
