# Orpheus

**运行在 Codex 中的轻量数学研究插件：保存可续接的研究笔记，提炼有用途的局部定理，并通过独立冷审积累 Git Fact。**

[English](README.en.md) · [快速开始](docs/快速开始.md) · [高级安装](docs/安装便携包.md) · [文献管理](docs/Zotero适配与使用.md) · [Fact 维护](docs/Fact维护说明.md)

第一次使用请从快速开始阅读。本公开源码和安装包不包含开发者的研究数据、原仓库历史、账户或本机路径。

## 它做什么

- Codex 主对话统筹研究，按需使用原生子代理开展证明、计算和文献阅读；各角色模型由用户指定或沿用宿主默认配置。
- 从现象提炼自然、局部有力且有用途的结论；在里程碑比较深化、推广、应用和换路线，保留用户明确指定的总目标。
- 将过程、失败路线和阅读记录保存为 Obsidian 可读 Markdown。一个研究项目可以包含多个问题。
- 固定候选经过全新会话独立冷审后显式接纳，保留证明、精确依赖、脚本及计算结果；Fact 使用 Git 版本历史和完整性检查。
- 文献阅读会探索同篇论文的相关与更强结果，并根据价值追踪前置工作、推广和修正。Zotero 可选。

> [!important] 证据边界
> `AI_REVIEWED` 只表示独立 AI 审查通过，不是形式化证明或专家认证。有限计算不能代替一般性证明；重要结论仍须复核。Git 提供修改检测与恢复依据，不是操作系统级隔离。

## 安装

当前安装器支持 **Windows、Python 3.13、Git，以及可执行 `codex plugin add` 的 Codex CLI**。Codex 桌面版用于实际研究；Obsidian 和 Zotero 可选。

1. 下载 Release 中的 `orpheus-0.1.0-windows.zip` 并解压。
2. 在解压目录打开 PowerShell，执行：

```powershell
$target = Join-Path $env:USERPROFILE "Orpheus"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_portable.ps1" -InstallPath $target
```

3. 看到 `INSTALLED` 后，在 Codex 中选择自己的数学研究文件夹并新建对话。
4. 输入“使用 Orpheus 研究以下问题”，随后给出问题和目标；需要时同时指定各角色的模型。

也可以下载 GitHub 的源码 ZIP，在源码目录运行同一安装命令。**安装目标必须是另一个空目录，不要在公开源码 checkout 中开展私人研究。**

首次安装会从 Python 包索引下载锁定依赖，Codex 模型使用用户自己的账户。安装器拒绝覆盖非空安装目录或同名已安装插件。已有插件的升级、并行试用和卸载见[高级安装](docs/安装便携包.md)。

## 代码、研究笔记与 Fact 的位置

| 内容 | 位置 |
| --- | --- |
| 可公开的插件源码与测试 | 本代码仓库 |
| 问题笔记、过程和结论索引 | 用户研究项目的 `Orpheus研究/` |
| 文献信息、阅读记录和用户添加的原文入口 | 用户研究项目的 `papers/` |
| 候选、冷审报告、正式 Fact 与独立 Git 历史 | 用户选择的安装目录 |

默认不配置远程仓库。需要备份时，可在安装命令中指定用户自己的空私有仓库 `-RemoteUrl`，详见[快速开始](docs/快速开始.md)。**公开代码仓库不能作为私人 Fact 的上传目标。**不会上传开发者或其他用户的研究数据。

插件包含本地 stdio MCP 服务，安装器生成本机路径；它不托管数学数据库，也不提供跨用户云端服务。GitHub 源码分发目前采用安装器，不能仅添加仓库到插件目录就完成 Python 环境和 Fact 历史初始化。macOS、Linux 安装和官方插件目录上架尚未验收。

## 开发与测试

在干净源码 checkout 中运行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/package_release.py
```

发布脚本先运行测试，再按白名单打包；排除研究数据、Git 历史、虚拟环境与凭据，并生成内容摘要清单。额外私人标识可通过 `ORPHEUS_PRIVATE_MARKERS` 环境变量提供，每行一个。测试与安装验证不代表数学正确性或真实研究效果已经得到保证。

## 许可证与贡献

代码与 Skills 使用 [MIT 许可证](LICENSE)。贡献前请阅读 [贡献说明](CONTRIBUTING.md)。报告问题时请使用最小复现，移除私人 Fact、凭据和本机身份信息。
