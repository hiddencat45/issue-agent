# Issue Agent

开发者 Issue 分诊与辅助修复：先只读看清问题，再提出补丁，人批准后才写入，并留下可回放记录。

当前**不会**自动改仓库、不会跑任意 Shell、不会在未批准时写入。

评测阶段已于 2026-09-26 收口。分诊/修复评测命令仍可复跑，但不再加玩具用例，也不把玩具仓库打分当成质量已验证。

## 准备

```powershell
python -m pip install -r requirements.txt
```

模型调用需要环境变量 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。可参考 `.env.example`，不要把密钥提交进仓库或贴到聊天里。

模型请求若遇到连接中断、stream_read_error、HTTP 520 / 5xx，或 overloaded / service_unavailable / server_error，会自动再试 1 次；仍失败则报错，不静默跳过。

`--workspace` 和 `--out-dir` 必须是绝对路径。

可选环境变量 `GITHUB_TOKEN`（或 `GH_TOKEN`），用于只读拉取 GitHub issue。公开 issue 可以留空。不要把 token 写进仓库或贴到聊天里。发评论必须显式 `--post-comment`；开 PR 必须显式 `--open-pr`。默认只预演。不会创建分支或 git push。



## 本地演示（实习作品闭环）

面试请看 `DEMO.md`（约 5 分钟，不调模型）。下面是同一条命令。

不调模型、不改仓库、不发 GitHub 评论。用内置小仓库走完：分诊报告 → 补丁预演 → 评论预览。

```powershell
python -m app.demo_loop --out-dir "D:\path\to\out"
```

输出目录会有 `WALKTHROUGH.md`、`report.json`、`patch.json`、`verify.json`、`comment.md`。打开 `WALKTHROUGH.md` 即可讲解。目标仓库是 `cases/demo/workspace`，其中 `format_note` 仍会 `strip()`；演示只预演去掉 strip，默认不写入。

若要当场调模型（需要 API Key），仍不写入、不发评论：

```powershell
python -m app.demo_loop --out-dir "D:\path\to\out" --live
```

对真实公开 issue 只读预演：先自己 clone 目标仓库，再拉取 issue。必须 `--live`，仍然不写入、不发评论、不开 PR。

```powershell
git clone --depth 1 https://github.com/saulpw/unzip-http.git "D:\path\to\unzip-http"
python -m app.demo_loop --live --github-issue "saulpw/unzip-http#23" --workspace "D:\path\to\unzip-http" --out-dir "D:\path\to\out"
```

本命令不会开 PR。真正写入请用 `python -m app.issue --allow-write ... --apply`；真正发评论请用 `python -m app.github_comment --post-comment`。

## GitHub

只读拉取 issue（含最多 20 条评论），再走现有分诊/提案流程。

评论默认只预演，不发到 GitHub。`--comment-file` 与 `--report-file` 必须二选一：前者发送现成 Markdown，后者把分诊 report.json 转成评论。加上 `--post-comment` 才会 POST；发评论需要 `GITHUB_TOKEN`。结果 JSON 不含 token。仍然不会开 PR。

```powershell
python -m app.github_issue --github-issue "https://github.com/owner/repo/issues/123" --out issue.txt
python -m app.issue --workspace "D:\path\to\repo" --github-issue "owner/repo#123" --out-dir "D:\path\to\out"
python -m app.github_comment --github-issue "owner/repo#123" --report-file "D:\path\to\out\report.json"
python -m app.github_comment --github-issue "owner/repo#123" --comment-file comment.md
python -m app.github_comment --github-issue "owner/repo#123" --report-file "D:\path\to\out\report.json" --post-comment
python -m app.github_pr --github-issue "owner/repo#123" --report-file "D:\path\to\out\report.json" --patch-file "D:\path\to\out\patch.json" --head "fix-branch"
python -m app.github_pr --github-issue "owner/repo#123" --report-file "D:\path\to\out\report.json" --patch-file "D:\path\to\out\patch.json" --head "fix-branch" --open-pr
```

开 PR 默认只预演，不会创建分支、不会 git push、不会写仓库。`--open-pr` 才会调用 GitHub API；需要 `GITHUB_TOKEN`，并且 **head 分支必须已经在 GitHub 上存在**。

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

写入成功后，可再加 `--pytest`，在目标仓库根目录运行 `python -m pytest -q`。这不是任意 Shell：不能改命令、不能加参数。测试失败不会撤销已经写入的文件。若加 --rollback-on-fail，会在 pytest 失败后把本轮改过的文件写回去；默认仍不回滚。pytest.json 仍会保留。

若 pytest 失败，输出目录会留下 pytest.json（含 stdout、stderr、退出码）。这不会自动再出一版补丁。要再提一版，可把失败输出当作只读上下文：

```powershell
python -m app.propose --workspace "D:\path\to\repo" --issue-file issue.txt --pytest-file "D:\path\to\out\pytest.json" --out next-patch.json --verify
python -m app.repair --workspace "D:\path\to\repo" --patch-file next-patch.json --allow-write notes.py --apply --pytest
```

写入并立刻跑测试（仍须 `--apply`）：

```powershell
python -m app.issue --workspace "D:\path\to\repo" --issue-file issue.txt --out-dir "D:\path\to\out" --allow-write notes.py --apply --pytest
```

pytest 失败后回滚本轮写入（仍保留 pytest.json）：

```powershell
python -m app.issue --workspace "D:\path\to\repo" --issue-file issue.txt --out-dir "D:\path\to\out" --allow-write notes.py --apply --pytest --rollback-on-fail
```

没有 `--apply` 时，目标仓库不会被修改。没有 `--pytest` 时，不会跑测试。

一份补丁可以改同一文件的多处，也可以改多个已有文件。`--apply` 时每个被改文件都要出现在 `--allow-write` 里，缺一个则全部不写。仍然不能新建或删除文件。可读可改的文本后缀现包括 .py/.md/.json/.yml/.js/.ts 等；仍不读二进制、隐藏文件或超过 200KB 的文件。旧的单处四字段补丁仍然可用。

## 拆开用

```powershell
python -m app.triage --workspace "D:\path\to\repo" --issue-file issue.txt --out report.json --trace-out triage-trace.json
python -m app.propose --workspace "D:\path\to\repo" --issue-file issue.txt --out patch.json --verify --trace-out propose-trace.json
python -m app.propose --workspace "D:\path\to\repo" --issue-file issue.txt --pytest-file "D:\path\to\out\pytest.json" --out next-patch.json --verify
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py --apply
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py --apply --pytest
python -m app.repair --workspace "D:\path\to\repo" --patch-file patch.json --allow-write notes.py --apply --pytest --rollback-on-fail
python -m app.trace_show --trace-file propose-trace.json
python -m app.trace_replay --workspace "D:\path\to\repo" --trace-file propose-trace.json
python -m app.github_issue --github-issue "owner/repo#123" --out issue.txt
python -m app.github_comment --github-issue "owner/repo#123" --report-file report.json
python -m app.github_comment --github-issue "owner/repo#123" --report-file report.json --post-comment
python -m app.github_pr --github-issue "owner/repo#123" --report-file report.json --patch-file patch.json --head "fix-branch"
python -m app.demo_loop --out-dir "D:\path\to\out"
python -m app.demo_loop --out-dir "D:\path\to\out" --live
```


## 分诊评测

对固定案例打分：是否提到该提到的文件，证据 quote 是否为原文。

```powershell
python -m app.eval_cases --workspace "D:\path\to\target-repo" --cases-dir "D:\path\to\issue-agent\cases\pagination" --out-dir "D:\path\to\out" --run
```

省略 `--run` 时，只评分 `--out-dir` 里已有的 `{id}.json` 报告，不调模型。

## 修复评测

对固定案例：补丁是否改到该改的文件、原文能否预演对上，然后在**仓库副本**上写入并跑 `python -m pytest -q`。当前真实缺陷包括：保留空格、逗号拼接，以及文档与测试不一致的 glue_tags（测试要逗号，README 要空格）。额外改已有说明文件不判失败。模板仓库不会被改。

```powershell
python -m app.eval_repair --workspace "D:\path\to\issue-agent\cases\repair\workspace" --cases-dir "D:\path\to\issue-agent\cases\repair" --out-dir "D:\path\to\out" --run
```

省略 `--run` 时，只评分已有补丁，不调模型。`--run` 会连续为保留空格、逗号拼接两条真实缺陷调用模型；一条失败不会跳过另一条。金标失败补丁（改错文件、原文对不上）仍不调模型，只用来确认评测会判失败。

## 测试

```powershell
python -m pytest -q
```

## 不要用

- `app/demo_read_file.py`：阶段一 demo，不是产品入口。本地演示请用 `python -m app.demo_loop`
- 已作废的空 prompts.py / schemas.py（不再使用）
