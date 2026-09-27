# 5 分钟演示稿

给面试官看的稳定路径：**不调模型、不改仓库、不发 GitHub 评论、不开真实 PR**。

## 先跑测试

在 `issue-agent` 目录：

```powershell
python -m pytest -q
```

期望全部通过。说明约束是有测试托底的，不是口头约定。

## 再跑离线闭环

`--out-dir` 必须是绝对路径：

```powershell
python -m app.demo_loop --out-dir "D:\path\to\out"
```

打开输出里的 `WALKTHROUGH.md`。按文件讲：

1. `issue.txt`：用户说 `format_note` 不该 `strip`
2. `report.json`：分诊指向 `notes.py`
3. `patch.json` / `verify.json`：预演去掉 `strip`，原文对得上，**没有写入**
4. `comment.md`：GitHub 评论预览，底部写明需人工确认
5. `comment-preview.json`：`posted` 为 false
6. `pr.md` / `pr-preview.json`：PR 预览，`opened` 为 false

目标小仓库在 `cases/demo/workspace`。演示结束后 `notes.py` 里仍应有 `strip()`。

## 一句话产品边界

先只读看清问题，再提出补丁；人点名文件并批准后才写入。评论同样默认只预演。

不要说成：已在真实大仓库验证质量，或会自动修到测试全绿，或会自动开 PR。

## 可选加戏（需要 API Key，仍不写入）

```powershell
python -m app.demo_loop --out-dir "D:\path\to\out" --live
```

真实公开 issue 只读预演见 README。现场调模型可能慢，也可能分诊证据不全；面试主路径请用上面的离线命令。