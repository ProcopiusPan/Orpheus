# Fact 工具与证据

`fact_search(query, limit)` 返回有效 Fact 的 ID、版本、标题和证据等级。`fact_get(fact_id, version)` 返回 Git 中该精确版本的数学正文与机器元数据。版本必须精确，不用“最新”暗中替换证明依赖。

**检索语义：** 当前 `fact_search` 对 Fact 正文做不区分大小写的连续子串匹配，不做分词、关键词 AND／OR 或语义检索。空格分隔的多个词会作为一个完整字符串匹配；零命中不能说明没有与这些关键词相关的结果。按独立关键词、结构别名和一般定理术语分别查询，再读取命中的实际命题；命中也可能仅来自证明或引用。结果受 `limit` 截断，一次查询不证明已穷尽。必要时只读检索正式库或阅读索引扩大定位范围，最终仍用 `fact_get` 核实状态、精确版本和数学内容。

`candidate_submit(request_key, candidate)` 接受标题、命题、假设、证明、来源、依赖和可选修订来源，并把固定候选写入 Git commit。使用稳定请求键；相同内容会复用候选哈希，改变内容必须更换请求键。

`candidate_submit_files(request_key, candidate, artifact_files)` 用于带本地附件的候选。`candidate` 不内嵌 `artifacts`；`artifact_files` 每项只含 `path`、`kind` 和可选 `name`。Fact 服务直接从本地文件读取 UTF-8 内容并构造同一种不可变候选，附件不会经过命令输出或模型上下文。大脚本、结果和证书优先使用此入口；不要先用 `Get-Content` 把全文读回对话。

候选字段：`title`、`statement`、`assumptions`、`proof` 为字符串；`proof` 必须是展开对象、推导、量词、分情况、边界和引用条件的完整正式证明，不接受只写思路或证明梗概；`sources` 为含 `citation`、`locator`、可选 `excerpt` 的列表；`dependencies` 为 `fact_id` 与整数 `version` 的列表；小附件可通过 `artifacts` 内嵌，每项含安全文件名 `name`、`kind`（`script|report|data|certificate`）和 `content`；大附件使用 `candidate_submit_files` 的路径描述；`revises` 可选，格式同依赖。不要添加 `verified`、`verdict` 等字段。

计算 Fact 必须同时附带三类内容：实际执行的脚本（`script`）、用户可读实验报告（`report`），以及机器可读的结果或证书（`data` 或 `certificate`）。服务会拒绝缺少任一类的新计算候选，并在接纳时再次检查。候选摘要自动绑定附件完整内容；接纳后附件写入 `facts/<fact-id>/vN-artifacts/`，服务自动记录类型、长度和内容摘要并纳入完整性检查。

研究者不在候选正文、实验报告或手写 manifest 中抄写附件 SHA-256、字节数或候选摘要，也不负责使多处人工副本一致。实验报告只记录输入域、运行命令、关键环境、算法完备性边界和可读输出摘要；结果附件直接保存足以复用和核验结论的输入标识、关键输出、计数或见证。超出单附件上限的大型结果可按稳定文件名分块，分块清单由实际 `artifacts` 和服务元数据给出，不另造带哈希的人工 manifest。不能只指向工作区临时文件。

计算结果按“算法 Fact → 运行 Fact → 数学结果 Fact”组织；短而紧密的算法与运行可以合并。算法 Fact 保存脚本及其正确性和适用边界；运行 Fact 依赖算法 Fact，保存确定输入、环境、报告、数据或证书；数学结果 Fact 只承担从已核验输出到数学断言的推导。不要按函数、循环或流水线阶段机械拆分。

后续审查若已有内容匹配的有效计算 Fact，应通过精确 `dependencies` 复用，不再重跑，也不必在每个下游 Fact 重复附同一脚本。是否匹配以 Fact 的断言、输入范围、算法版本和结果内容为准；文件身份由服务自动处理，不要求研究者比较或抄写哈希。输入、算法或结果实质变化时提交新的计算候选。经原文严查形成的文献 Fact 也按精确版本复用；只有候选扩大引用范围、来源版本变化或该 Fact 被质疑时才重新核验原文。

`submission_get(candidate_digest)` 查询候选是否已有绑定审查，返回 `SUBMITTED` 或审查 verdict。`PASS` 仍需通过显式接纳入口才能生成 Fact；`REJECT` 不自动表示命题为假。

提交返回 `SUBMITTED` 后，下一动作是启动不继承研究推导的新冷审查者。冷审异步进行；Leader 可以继续不依赖该候选的工作，并在自然检查点回收结果。未经接纳的候选不能写入其他候选的 `dependencies`，基于它的推导只能标为暂定。在审候选遵守宿主当前可用的审查容量，达到边界后先回收已有 verdict 再提交新的候选。

审查完成后，宿主先核对报告 schema、候选哈希和规则摘要，再在当前插件 `.mcp.json` 指向的 Orpheus 仓库中运行：

```powershell
python scripts/fact_admin.py review <candidate-digest> --file <review.json>
python scripts/fact_admin.py accept <candidate-digest>
```

第二条命令只在 verdict 为 `PASS` 且没有错误或未解决缺口时执行。接纳结果的 `remote_sync.status` 为 `SYNCED`、`REMOTE_PENDING` 或 `NOT_CONFIGURED`；只有 `SYNCED` 可以报告为已上传。后两种情况下本地 Fact 仍已接纳，幂等地再次接纳同一候选会重试无交互普通 push。`REJECT` 或 `INCONCLUSIVE` 不得接纳；修订内容使用新请求键重新提交和冷审。研究阶段不另设提交前审计。

`fact_issue_report(fact_id, version, reason)` 提交疑似错误并生成 Git 记录；问题报告不会直接撤销。修订应作为新候选提交，撤销使用显式维护入口并传播依赖失效。

`facts/<fact-id>/vN.md` 与相邻 JSON 是 canonical 版本；SQLite 和其他阅读副本都可删除重建。禁止直接编辑 `facts/`、`reviews/` 或 manifest；发现异常先保留 incident，再显式恢复。REJECT 或 INCONCLUSIVE 后只能以新请求键提交修订候选并重新冷审查，不能覆盖旧候选或旧报告。模型审查证据标记 `AI_REVIEWED`，不能称为证明内核检查。
