# Orpheus

**让数学研究可续接，让证明可审查，让结果可复用。**

Orpheus 是运行在 Codex 中的轻量数学研究插件。Codex 负责推理与协作，Orpheus 将研究过程保存为可读笔记，把经过独立审查的局部结论积累为 Git Fact，并支持持续整理成论文。

[下载最新版](https://github.com/ProcopiusPan/Orpheus/releases/latest) · [快速开始](docs/快速开始.md) · [English](README.en.md)

## 它做什么

- **续接研究**：在 Obsidian 可读笔记中保留问题、推导、失败路线与阅读记录，新对话从已有进展继续。
- **积累结论**：将证明完整的小结论交给全新会话独立审查，接纳后保存为 Git Fact，保留证明、依赖和计算材料。
- **利用文献**：在新问题和新结构出现时跨领域检索已有工作，扩展阅读相关结果；可选用 Zotero 管理文献。
- **整理成文**：通过内置 [Fact 论文写作 Skill](plugins/orpheus/skills/fact-paper-writing/SKILL.md)组织已接纳的结果，增量更新稿件并精修表达。

主对话统筹研究，按需调用 Codex 原生子代理；各角色模型可由用户指定或沿用宿主默认配置。

## 安装

当前安装器支持 **Windows、Python 3.13、Git，以及可执行 `codex plugin add` 的 Codex CLI**。Codex 桌面版用于实际研究；Obsidian 和 Zotero 可选。

1. 从 [Latest Release](https://github.com/ProcopiusPan/Orpheus/releases/latest) 下载 Windows 安装包（文件名以 `-windows.zip` 结尾）并解压。
2. 在解压目录打开 PowerShell，执行：

```powershell
$target = Join-Path $env:USERPROFILE "Orpheus"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_portable.ps1" -InstallPath $target
```

3. 看到 `INSTALLED` 后，在 Codex 中选择自己的数学研究文件夹并新建对话。
4. 输入“使用 Orpheus 研究以下问题”，随后给出问题和目标；需要时同时指定各角色的模型。

也可以下载 GitHub 的源码 ZIP，在源码目录运行同一安装命令。选择独立空目录作为安装位置。

安装器会建立 Python 环境、下载依赖、初始化 Fact 历史并注册插件。Codex 模型使用用户自己的账户。已有插件的升级、并行试用和卸载见[高级安装](docs/安装便携包.md)。

## 代码、研究笔记与 Fact 的位置

| 内容 | 位置 |
| --- | --- |
| 可公开的插件源码与测试 | 本代码仓库 |
| 问题笔记、过程和结论索引 | 用户研究项目的 `Orpheus研究/` |
| 文献信息、阅读记录和用户添加的原文入口 | 用户研究项目的 `papers/` |
| 候选、冷审报告、正式 Fact 与独立 Git 历史 | 用户选择的安装目录 |

研究资料保存在本地。需要远程备份时，在安装命令中通过 `-RemoteUrl` 指定自己的空私有仓库，详见[快速开始](docs/快速开始.md)。

插件通过本地 stdio MCP 服务管理 Fact，环境和路径由安装器配置。

## 从 Fact 写论文

在研究项目中告诉 Codex：

```text
使用 Orpheus 的 Fact 论文写作 Skill，根据已接纳 Fact 和相关文献整理这篇论文，并按新结果更新正文。目标稿件：填写文件路径；读者、语言与格式：填写要求。
```

写作会读取完整证明及计算附件，围绕数学论证组织材料，并处理来源对应、稿件同步与可读性精修。也可以只要求更新某个章节或润色已有稿件。

## 开发与测试

在干净源码 checkout 中运行：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/package_release.py
```

发布脚本运行测试、按源码清单打包并生成文件校验值。验收记录见[发布验证](docs/Release-validation.md)。

## 许可证与贡献

代码与 Skills 使用 [MIT 许可证](LICENSE)。欢迎反馈和贡献，详见[贡献说明](CONTRIBUTING.md)。

[高级安装](docs/安装便携包.md) · [文献管理](docs/Zotero适配与使用.md) · [Fact 维护](docs/Fact维护说明.md)
