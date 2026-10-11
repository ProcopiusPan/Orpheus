# Orpheus

A lightweight mathematical research plugin for Codex. The main conversation leads research, native agents collaborate, Skills guide research and cold review, and a local stdio MCP service maintains Git-versioned Facts.

[中文说明](README.md) · [Installation guide](docs/快速开始.md)

## Capabilities

- Extract useful local theorems, compare research routes, and preserve explicit user goals.
- Maintain resumable Markdown notes compatible with Obsidian, including failed approaches and literature reading.
- Independently review immutable candidates in fresh sessions before explicit Fact acceptance.
- Preserve exact dependencies, proofs, computation scripts and bound results in Git history.
- Explore related and stronger literature results. Zotero is optional.

`AI_REVIEWED` is an AI review status, not formal proof certification. Git integrity checks support detection and recovery; they are not operating-system isolation.

## Install on Windows

Requirements: Python 3.13, Git, Codex CLI with `codex plugin add`, and Codex desktop for research. Obsidian and Zotero are optional.

Download and extract the Windows ZIP from Releases. Open PowerShell in the extracted directory:

```powershell
$target = Join-Path $env:USERPROFILE "Orpheus"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install_portable.ps1" -InstallPath $target
```

The installer creates a virtual environment, downloads pinned dependencies, initializes a fresh local Fact history and installs `orpheus@personal`. It refuses nonempty targets and existing same-name plugins. Start a new Codex conversation in your own research project and ask it to use Orpheus for your problem.

You can also install from a downloaded source ZIP. Keep the public source checkout separate from the installation and research project. Notes live in the project's `Orpheus研究/`, literature records in `papers/`, and accepted Facts in the installation directory.

No remote is configured by default. To back up research, supply your own empty private repository using `-RemoteUrl`, `-GitName` and `-GitEmail`. Never use the public source repository as the remote for private Facts. See the Chinese [advanced installation guide](docs/安装便携包.md) for parallel installations and upgrade boundaries.

This release uses a local stdio server and an installer; adding a GitHub marketplace alone does not initialize the Python environment or Fact storage. Linux/macOS installation and official directory distribution have not been validated.

## Development

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/package_release.py
```

Tests use synthetic data and temporary repositories. No real-model mathematical benchmark is included. Contributions are welcome; follow [CONTRIBUTING.md](CONTRIBUTING.md) and do not attach private research or credentials.

Licensed under [MIT](LICENSE).
