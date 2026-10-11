# Fact 维护说明

公开源码不包含研究数据库。安装器在用户指定的独立安装目录初始化空 Fact 历史：`facts/MANIFEST.json` 登记初始约定文件，`facts/README.md` 保留约定；候选、审查、请求、问题与事件从空目录开始。每个接纳版本包含 Obsidian 可读的 `vN.md` 和机器元数据 `vN.json`。下述维护命令在该安装目录执行，不能在公开源码目录中生成私人研究数据。

## 正常流程

研究侧通过 stdio MCP 的 `candidate_submit` 提交固定候选。候选不能携带 `model`、`verdict` 或写入事实的命令。审查完成后，宿主使用明确的文件入口：

```text
python scripts/fact_admin.py review <candidate-digest> --file review.json
python scripts/fact_admin.py accept <candidate-digest>
```

接纳只追加版本，不覆盖既有数学正文；问题报告使用 MCP 的 `fact_issue_report`，不会直接改变 Fact 状态。撤销由用户明确执行：

```text
python scripts/fact_admin.py revoke <fact-id> <version> --reason "..."
```

撤销会保留原版本，追加状态事件，并递归标记依赖为 `INVALIDATED_BY_DEP`。

## 完整性和恢复

写入前会检查工作区是否被直接修改，并验证 `facts/MANIFEST.json` 覆盖的 facts、候选和审查文件哈希，以及 Fact 路径、版本、审查绑定和依赖。`issues/` 与 `incidents/` 是独立的 append-only 审计目录：不纳入事实 manifest，但每个事件必须同时有机器元数据和可读证据；完整性事件另保存 patch 并独立提交。

检查失败时先记录 `incidents/incident-*.json`、`.patch` 和 `.md`，随后拒绝写入。不会静默 reset 或覆盖现场。恢复必须显式指定 incident、已知 Git commit 和相对路径，再重新运行完整性检查。SQLite 如需加速，只能用 `GitFactStore.rebuild_index()` 从当前 Git tree 重建；删除 SQLite 不影响正式 Fact。

每次 push/PR 的 `scripts/audit_fact_change.py` 要求 canonical 路径变化与 `facts/MANIFEST.json` 同时变化；只改 manifest 会失败。CI 摘要只记录路径、哈希、计数、状态和 last-known-good commit，不导出 Fact 正文。`fact_admin.py restore` 和 `revert` 默认 dry-run，只有明确传入 `--apply` 才执行恢复或回滚。

## 远程保护

远程仓库若已配置为 `origin`，Fact 接纳后会以无交互、非 force 的普通 push 尝试同步当前 `HEAD` 到 `origin/main`；成功返回 `SYNCED`，网络、认证或远端分叉导致失败时保留本地接纳结果并返回 `REMOTE_PENDING`。对同一候选再次执行幂等接纳会重试同步。Orpheus 不自动创建 remote。分支保护或审查规则是否生效，必须根据实际 Git 主机、仓库权限和仓库配置检查，不能由备份或 CI 颜色推断。

