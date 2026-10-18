# Orpheus

**Keep research resumable, proofs reviewable, and results reusable.**

Orpheus is a lightweight mathematical research plugin for Codex. Codex handles reasoning and collaboration; Orpheus preserves readable research notes, accumulates independently reviewed local results as Git-versioned Facts, and helps turn them into papers.

[Download latest](https://github.com/ProcopiusPan/Orpheus/releases/latest) · [Quick start (中文)](docs/快速开始.md) · [中文说明](README.md)

## Capabilities

- **Resume research**: keep problems, derivations, failed approaches and reading records in Obsidian-compatible notes, then continue in a new conversation.
- **Build reusable knowledge**: review small, complete results in fresh sessions and preserve accepted Facts with their proofs, dependencies and computation artifacts in Git.
- **Use prior work**: search across fields when starting a problem or discovering a structure, explore related results, and optionally manage literature with Zotero.
- **Write papers**: use the bundled [Fact-based paper-writing Skill](plugins/orpheus/skills/fact-paper-writing/SKILL.md) to organize accepted results, update manuscripts incrementally and polish the prose.

The main conversation leads research and uses Codex's native agents as needed. Models for each role can be selected by the user or inherited from the host configuration.

## Install on Windows

Requirements: Python 3.13, Git, Codex CLI with `codex plugin add`, and Codex desktop for research. Obsidian and Zotero are optional.

Download the Windows installer archive (the filename ends in `-windows.zip`) from the [Latest Release](https://github.com/ProcopiusPan/Orpheus/releases/latest) and extract it. Open PowerShell in the extracted directory:

```powershell
$target = Join-Path $env:USERPROFILE "Orpheus"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_portable.ps1" -InstallPath $target
```

Choose a separate empty directory for the installation. The installer creates a virtual environment, downloads pinned dependencies, initializes a fresh local Fact history and installs `orpheus@personal`. Start a new Codex conversation in your own research project and ask it to use Orpheus for your problem.

You can also install from a downloaded source ZIP using the same command.

## Notes and Facts

Notes live in the project's `Orpheus研究/`, literature records in `papers/`, and candidates, review reports and accepted Facts in the installation directory. A local stdio MCP service manages Facts; the installer configures its environment and paths.

Research materials are stored locally. For remote backups, supply your own empty private repository using `-RemoteUrl`, `-GitName` and `-GitEmail`. See the Chinese [advanced installation guide](docs/安装便携包.md) for upgrades, parallel installations and removal.

## Writing from Facts

For paper writing, ask Codex to use Orpheus's Fact-based paper-writing Skill and specify the target manuscript, scope, audience, language and format. It reads the accepted evidence and organizes the mathematical argument, citations and supporting examples. Chapter updates and prose-only revisions are also supported.

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

[Advanced installation (中文)](docs/安装便携包.md) · [Literature management (中文)](docs/Zotero适配与使用.md) · [Fact maintenance (中文)](docs/Fact维护说明.md)
