# Orpheus

A lightweight mathematical research plugin for Codex. The main conversation leads research, native agents collaborate, Skills guide research and cold review, and a local stdio MCP service maintains Git-versioned Facts.

[中文说明](README.md) · [Installation guide](docs/快速开始.md)

## Capabilities

- Extract useful local theorems, compare research routes, and preserve explicit user goals.
- Maintain resumable Markdown notes compatible with Obsidian, including failed approaches and literature reading.
- Independently review immutable candidates in fresh sessions before explicit Fact acceptance.
- Preserve exact dependencies, proofs, computation scripts and bound results in Git history.
- Search prior work across fields when starting a problem or discovering a structure; reuse relevant theories, locate the contribution, and explore related or stronger results. Zotero is optional.

## Install on Windows

Requirements: Python 3.13, Git, Codex CLI with `codex plugin add`, and Codex desktop for research. Obsidian and Zotero are optional.

Download and extract `orpheus-0.1.0-windows.zip` from [Releases](https://github.com/ProcopiusPan/Orpheus/releases). Open PowerShell in the extracted directory:

```powershell
$target = Join-Path $env:USERPROFILE "Orpheus"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_portable.ps1" -InstallPath $target
```

Choose a separate empty directory for the installation. The installer creates a virtual environment, downloads pinned dependencies, initializes a fresh local Fact history and installs `orpheus@personal`. Start a new Codex conversation in your own research project and ask it to use Orpheus for your problem.

You can also install from a downloaded source ZIP using the same command.

## Notes and Facts

Notes live in the project's `Orpheus研究/`, literature records in `papers/`, and candidates, review reports and accepted Facts in the installation directory. A local stdio MCP service manages Facts; the installer configures its environment and paths.

Research materials are stored locally. For remote backups, supply your own empty private repository using `-RemoteUrl`, `-GitName` and `-GitEmail`. See the Chinese [advanced installation guide](docs/安装便携包.md) for upgrades, parallel installations and removal.

## Development

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/package_release.py
```

The release script runs tests, packages the source files and generates file checksums. See [release validation](docs/Release-validation.md) for the validation record.

Feedback and contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

Licensed under [MIT](LICENSE).
