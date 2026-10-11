# Orpheus

**运行在 Codex 中的轻量数学研究插件：保存可续接的研究笔记，提炼有用途的局部定理，并通过独立冷审积累 Git Fact。**

[English](README.en.md) · [快速开始](docs/快速开始.md) · [高级安装](docs/安装便携包.md) · [文献管理](docs/Zotero适配与使用.md) · [Fact 维护](docs/Fact维护说明.md)

第一次使用可以从[快速开始](docs/快速开始.md)阅读。

## 它做什么

- Codex 主对话统筹研究，按需使用原生子代理开展证明、计算和文献阅读；各角色模型由用户指定或沿用宿主默认配置。
- 从现象提炼自然、局部有力且有用途的结论；在里程碑比较深化、推广、应用和换路线，保留用户明确指定的总目标。
- 将过程、失败路线和阅读记录保存为 Obsidian 可读 Markdown。一个研究项目可以包含多个问题。
- 固定候选经过全新会话独立冷审后显式接纳，保留证明、精确依赖、脚本及计算结果；Fact 使用 Git 版本历史和完整性检查。
- 文献阅读会探索同篇论文的相关与更强结果，并根据价值追踪前置工作、推广和修正。Zotero 可选。

## 安装

当前安装器支持 **Windows、Python 3.13、Git，以及可执行 `codex plugin add` 的 Codex CLI**。Codex 桌面版用于实际研究；Obsidian 和 Zotero 可选。

1. 从 [Releases](https://github.com/ProcopiusPan/Orpheus/releases) 下载 `orpheus-0.1.0-windows.zip` 并解压。
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
