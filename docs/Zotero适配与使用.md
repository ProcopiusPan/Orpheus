# Zotero 适配与使用

## 角色与边界

若当前环境配置了 Zotero，Zotero Desktop 可作为全局文献书目、标签、集合、全文、附件和批注的主库。检索、读取、导出和导入优先复用已安装的 Zotero Skill/helper；集合归类也可通过 Zotero 10+ 的官方本地 API 在授权后完成。未配置 Zotero 时，项目 `papers/`、合法检索和其他可核验来源仍可支持研究。项目 `papers/` 承担项目级文献信息登记、阅读入口和用户手动添加特定文献的入口，通常不保存独立全文副本。文献管理不加入 Fact stdio 服务。

Zotero Skill 是可选协作插件。它未安装、Zotero 未运行或 Local API 未启用时，直接使用项目 `papers/` 或合法检索取得的原文，不因此阻塞研究；若以后启用 Zotero，可以再把项目登记转换为硬链接或路径引用，并保留 sidecar 和阅读记录。

## 日常归类

新增、复用或阅读文献时，按已有主题和实际项目用途顺手归类；一篇文章可属于多个集合。优先沿用用户现有结构，没有合适结构时可按阅读入口、研究项目、学科主题和待核对组织。分类是可修改的导航信息，后续使用中可以直接纠正，不设专门审批、审查或复核流程。

仅处理本轮涉及的文献和碰到的漏分条目，不反复全库整理；无需另建分类报告。归类不改变用户阅读状态或书目、笔记和附件。具体操作见[文献归类](../plugins/orpheus/references/literature-management.md)。Zotero 10+ 写入需要用户在软件中授权；较旧或不可写环境先保留项目导航，之后再补分类，不阻塞研究。

## 准备

### Windows 跨对话授权

Orpheus 的官方本地 API 写入统一经过 `plugins/orpheus/scripts/zotero_local.py`。首次运行 `python -B <orpheus-plugin-root>/scripts/zotero_local.py authorize` 并在 Zotero 选择“始终允许”；此后不同对话和插件版本从当前 Windows 用户的凭据管理器复用密钥，不需要再次申请。授权按 Zotero 实例隔离，凭据不随插件包、Git 或研究项目分发。

`status` 不弹窗，只报告连接与缓存是否存在，不能单凭缓存存在断言密钥仍有效。`request PATCH /api/users/0/items/ITEMKEY --json-file change.json` 使用共享授权执行官方写入，JSON 中需带当前对象版本；仅当密钥缺失或收到 401 时才请求官方授权，拒绝或其他错误不循环弹窗。`forget` 删除 Orpheus 本机缓存，不撤销 Zotero 侧授权。细节及边界见[文献归类的跨对话授权](../plugins/orpheus/references/literature-management.md#跨对话授权windows)。非 Windows 暂未实现此持久授权入口。

在 Zotero 中启动 Desktop，并在设置中启用允许本机应用访问的 Local API。用 Zotero Skill 的 helper 检查：

```text
python3 <zotero-skill-root>/skills/zotero/scripts/zotero.py status --json
```

helper 会返回 readiness/status。若 Zotero 未运行或 Local API 未启用，应停止 Zotero 查询；条目没有本地附件、附件路径失效或全文没有索引时，分别保留 helper 的 `ATTACHMENT_MISSING`、`ATTACHMENT_PATH_UNAVAILABLE` 或 `FULLTEXT_UNAVAILABLE` 状态。

由 Codex 根据已安装 Skill 的路径解析 `<zotero-skill-root>`，不要把缓存版本号写进项目文档。典型的只读检索链是：

```powershell
$helper = "<zotero-skill-root>\skills\zotero\scripts\zotero.py"
python3 $helper status --json
$hits = python3 $helper search "Higher Algebra" --json | ConvertFrom-Json
$item = $hits | Select-Object -First 1
$item | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 item.json
$children = python3 $helper children $item.key --json | ConvertFrom-Json
$attachment = $children | Where-Object { $_.itemType -eq "attachment" } | Select-Object -First 1
$fileUrl = python3 $helper file-url $attachment.key
$attachmentPath = ([Uri]$fileUrl).LocalPath
python3 plugins/orpheus/scripts/register_zotero_paper.py `
  --metadata-json item.json `
  --attachment-path $attachmentPath `
  --attachment-key $attachment.key `
  --workspace "D:\\Research\\MyProject" `
  --related-question "当前数学问题"
```

需要全文时，对选中的 attachment key 调用 `python3 $helper fulltext <attachment-key> --out attachment-fulltext.txt`；全文只是阅读材料，仍需回到原文核对正式 citation 和 locator。

## 登记到项目

先用 Zotero Skill/helper 找到明确的 Zotero item key、attachment key、本地附件路径，并把书目 JSON 导出到临时文件。然后运行 Orpheus 自带的项目登记脚本，提供项目根目录和可选的关联问题，例如：

```text
python plugins/orpheus/scripts/register_zotero_paper.py `
  --metadata-json item.json `
  --attachment-path "C:\\tools\\zotero\\storage\\ITEM1234\\paper.pdf" `
  --attachment-key ATTACH123 `
  --workspace "D:\\Research\\MyProject" `
  --related-question "当前数学问题"
```

默认 `hardlink` 在 `workspace/papers/` 创建与选定附件同一卷的硬链接。脚本不访问 Zotero，也不复制 PDF 数据；Obsidian 看到的是普通本地文件，sidecar 中由脚本保存完整性摘要、Zotero item key（如有）、attachment key、附件路径、来源和关联问题。硬链接要求源文件和项目在同一卷；失败时不会偷偷复制或覆盖文件，可明确重试 `--storage-mode path`。硬链接只是项目阅读入口；若使用 Zotero，全文主副本仍由 Zotero 管理。

`path` 模式只生成 sidecar，保存选定附件的绝对路径，不复制大文件。登记或 `sync_workspace.py sync` 会自动生成完整性摘要；`sync_workspace.py check --workspace <项目根>` 会验证路径引用仍指向现有文件并重新计算登记目标，硬链接模式则验证 sidecar 记录的项目文件仍存在并核对内容。对用户手动放入且标为 `storage_mode: manual_original` 的原文，脚本会自动补齐摘要；已有摘要与文件不一致时报告 `PAPER_HASH_MISMATCH`，不会静默覆盖旧登记。它不会替用户导入或移动文件。附件移动、存储迁移或路径失效时，检查会报告对应登记目标缺失。

登记按 sidecar 中的 Zotero item key 或 attachment key 去重，重复调用返回 `ALREADY_REGISTERED`，保留原有文件和用户批注。已有同名文件也不会覆盖，会追加 Zotero key 形成稳定的新文件名。

## 研究与 Fact 边界

登记生成的 sidecar 是 Obsidian 阅读入口，不是正式 Fact。Zotero 元数据、全文和本地路径不能直接写入候选的 `sources`；正式候选仍要补充完整 citation 和精确到 theorem、proposition、section、page 或 version 的 locator，并实际核对原文。项目中的手动原文可以直接用于阅读和核对；若随后启用 Zotero，再按登记流程补充对应关联。
