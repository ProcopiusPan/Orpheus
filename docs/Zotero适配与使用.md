# Zotero 适配与使用

## 角色与边界

若当前环境配置了 Zotero，Zotero Desktop 可作为全局文献书目、标签、集合、全文、附件和批注的主库。status、搜索、单条书目及 children、附件路径和已索引全文由已安装的官方 Zotero Skill/helper 完成。未配置 Zotero 时，项目 `papers/`、合法检索和其他可核验来源仍可支持研究。Orpheus 不把 Zotero HTTP 客户端复制进唯一 Fact stdio，也没有 Zotero 条目的新增、编辑、删除和 Connector 导入工具。项目 `papers/` 承担项目级文献信息登记、阅读入口和用户手动添加特定文献的入口，通常不保存独立全文副本。

Zotero Skill 是可选协作插件。它未安装、Zotero 未运行或 Local API 未启用时，直接使用项目 `papers/` 或合法检索取得的原文，不因此阻塞研究；若以后启用 Zotero，可以再把项目登记转换为硬链接或路径引用，并保留 sidecar 和阅读记录。

## 准备

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
