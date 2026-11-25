# Fact 工具与证据

## 读取与引用

用 `fact_search(query, limit)` 检索 ACTIVE 版本。空格分隔的关键词必须全部出现，忽略大小写，可分布在不同段落。匹配优先级依次为标题、命题、假设、证明及其余正文。返回精确版本、首要命中字段和原文片段；用 `fact_get(fact_id, version)` 核对假设及证明。检索有数量上限，换用结构别名可扩大覆盖。

要找直接依赖某个 Fact 的有效结果，在同一工具传入 `depends_on={"fact_id":"<Fact ID>","version":1}`。可省略 `query` 浏览直接下游，或加关键词缩小范围。

正式依据只有两类。已核对的外部原文写入 `sources`，注明 citation、版本和精确 locator；已核对的 ACTIVE Fact 写入 `dependencies`，绑定固定 ID 和整数版本。自足证明可无外部依据。经常复用的文献定理可先严查并形成文献 Fact；超出范围、版本变化或已有结论受质疑时重新核验。笔记、聊天与搜索摘要只作定位线索。

## 提交候选

提交前，从共用 `问题与进展.md` 的三个窗口小节查看相关草稿和提交记录，并核对相关 ACTIVE Fact。即使标题不同，也按假设、结论和证据比较：

- 已有 ACTIVE Fact 覆盖本结论时，引用其精确版本。已有同等或更强候选在审时，链接原记录，由原窗口跟进；独立推导可留在笔记，各窗继续其他工作。若更强候选被退回，仍可单独提交证明完整的较弱结论。
- 放宽了假设、加强了结论，或新方法、反例、计算证据本身可独立复用时，写清具体增量后单独提交。每份冷审报告只绑定实际受审的候选。
- 提交窗口随即在自己的共用进展小节链接提交记录。若并发提交后才发现完全重合，保留两个历史记录，由最早提交的窗口跟进；已有一路启动冷审时沿用该路。自己这条尚未启动的，在记录中链接正在跟进的候选，跳过重复冷审。

一个候选给出一个可独立引用的结论。`title`、`statement`、`assumptions`、`proof` 均为字符串。证明须展开关键推导、量词、分情况、边界和引用条件，足以从给定假设推出命题。`sources` 各项含 `citation`、`locator` 和可选 `excerpt`；`dependencies` 各项含 `fact_id` 与整数 `version`。修订已有 Fact 时可用同格式的 `revises`。

- 无本地附件时用 `candidate_submit(request_key, candidate)`。相同请求重试沿用请求键，修改候选内容使用新键。
- 带本地文件时优先用 `candidate_submit_files(request_key, candidate, artifact_files)`。每项传 `path`、`kind` 和可选 `name`，从服务可读的 UTF-8 文件直接绑定，此时 `candidate` 省略 `artifacts`。小型内存附件也可通过普通入口的 `artifacts` 传入安全文件名 `name`、`kind` 和 `content`。

每个包含新程序计算证据的候选须绑定实际脚本（`script`）、可读报告（`report`）和机器可读结果或证书（`data` 或 `certificate`）。报告写输入域、命令、关键环境、完备性边界和结果摘要。大文件走路径入口，超过单附件上限可分块。服务生成并校验内容摘要，附件随接纳版本保存在 `facts/<fact-id>/vN-artifacts/`。

算法正确性、特定输入的运行结果、由输出严格推出的结论可分别成 Fact，紧密相连的结论也可合并。复用先前计算时核对断言、输入范围、算法版本与输出，匹配即引用对应 ACTIVE 版本。只有新增或实质改变的计算才需绑定新的运行证据。

## 冷审与接纳

1. 首次返回 `SUBMITTED` 后记下候选标识。按上节确定由本窗口跟进的候选，立即安排全新 [Verifier](../skills/review-proof/SKILL.md)，并在提交记录中更新审查状态。幂等重试或续接时，先用 `submission_get` 和原线程记录确认是否已有审查或报告，只补做缺失的步骤。线程已满时保留原候选，先推进独立工作，回收已有结果后在下一自然检查点重试启动一次。达到在审容量时先回收再提交。只有已无独立工作时才等待。
2. 在下一项独立工作完成、准备提交下一候选、暂停或交接时回收报告。`submission_get(candidate_digest)` 查询已登记的状态。依赖在审候选的草稿标为暂定，接纳后才可用作正式依赖。
3. 宿主核对报告 schema、候选及规则摘要，在当前插件 `.mcp.json` 指向的仓库中登记报告。仅对已登记且无错误或未决缺口的 `PASS` 立即显式接纳。同一候选只做这一次正式冷审。

```powershell
python scripts/fact_admin.py review <candidate-digest> --file <review.json>
python scripts/fact_admin.py accept <candidate-digest>
```

`REJECT` 或 `INCONCLUSIVE` 均保留原候选和报告。提交窗口判断能否修复，修订稿换请求键并重新冷审。涉及项目总路线的取舍交给 Leader。

本地接纳后立即[同步项目阅读投影](workspace-notes.md#fact-阅读投影同步)，并报告接纳返回的 `remote_sync.status`。仅 `SYNCED` 表示已上传；`REMOTE_PENDING` 表示等待远端同步，`NOT_CONFIGURED` 表示未配置远端。远端可用后，幂等接纳同一候选可重试普通 push。

## 正式记录

`facts/<fact-id>/vN.md` 及相邻 JSON 是正式版本；AI 冷审等级为 `AI_REVIEWED`。发现疑似错误时用 `fact_issue_report(fact_id, version, reason)` 留存问题，撤销及依赖失效另走显式维护入口。不得直接编辑或删除 `facts/`、`reviews/`、manifest 或覆盖旧版本。完整性异常先保留记录，恢复或 Git revert 默认预览，仅在用户明确指定 `--apply` 时执行。
