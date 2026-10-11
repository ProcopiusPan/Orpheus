"""Reliable project-local launcher for the Orpheus stdio MCP server."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service"))

# MCP JSON-RPC is UTF-8. Windows otherwise inherits a console code page and
# corrupts Chinese mathematical titles when Codex launches this process.
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from orpheus_fact.stdio_mcp import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["--root", str(ROOT)]))
