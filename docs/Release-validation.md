# Release validation

## 0.1.1 — 2026-10-18

- Three bundled Skills passed structural validation: research, independent proof review, and Fact-based paper writing. Their Markdown references and interface metadata were checked.
- Source tests: 58 passed, 1 skipped. The skipped test requires an installed Windows MCP configuration.
- Temporary Windows installation tests confirmed that all five paper-writing files are installed with their original contents.
- The local plugin was upgraded through the Codex CLI; source, personal plugin source and the installed cache were compared file by file.
- The portable archive includes cross-field prior-work search and generalized paper-writing guidance. Archive integrity, file digests, extracted Markdown links and private-path scans were checked.
- The Fact service is unchanged from 0.1.0. Full dependency installation and MCP handshake validation from that release are recorded below; this update adds Skills and documentation.

## 0.1.0 — 2026-10-11

Validated on 2026-10-11 before public distribution.

- Source tests: 58 passed, 1 skipped. The skipped test requires an already-installed Windows MCP configuration; the source deliberately contains an installer-generated placeholder.
- Both Skills passed their structural validation. Markdown links and formula delimiter checks passed; these checks do not replace Obsidian rendering or mathematical review.
- A fresh Windows PowerShell 5.1 installation downloaded the pinned dependencies, created a Python 3.13 virtual environment and initialized an empty independent Git history.
- The generated MCP command completed a real stdio handshake, exposed six tools and returned an empty Fact search result.
- The real Codex CLI installed plugin version 0.1.0 in an isolated configuration. Existing user plugins were not modified.
- Source and archive checks found no inherited research records, original candidate/Fact identifiers, developer account markers, local user paths or matching credential patterns. The release archive content digests and ZIP integrity passed.
- The Fact service code is unchanged from the tested implementation. Public-release changes concern packaging, generic documentation, metadata and tests of the installer template.

No real-model mathematics benchmark, Linux/macOS installer, Obsidian UI rendering or remote branch protection was validated in this release. The repository is a source distribution; each installation owns a separate research history.
