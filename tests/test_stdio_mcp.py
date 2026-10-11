import json
import asyncio
import os
from pathlib import Path
import sys

import pytest

from orpheus_fact.git_facts import GitFactStore
from orpheus_fact.stdio_mcp import build_server, load_file_artifacts
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).parents[1]


def _portable_entry():
    """Use the active test interpreter; the installed plugin config is Windows-specific."""
    return {"command": sys.executable,
            "args": [str(ROOT / "scripts" / "orpheus_fact_stdio.py")]}


def _query(entry):
    async def query():
        parameters = StdioServerParameters(command=entry["command"], args=entry["args"], cwd=str(ROOT))
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                result = await session.call_tool("fact_search", {"query": "空库探针", "limit": 20})
                return initialized, result
    return asyncio.run(query())


def test_plugin_uses_stdio_and_exposes_only_git_fact_tools(tmp_path):
    config = json.loads((Path(__file__).parents[1] / "plugins/orpheus/.mcp.json").read_text(encoding="utf-8"))
    entry = config["mcpServers"]["orpheus-fact"]
    if entry["command"] == "__GENERATED_BY_INSTALLER__":
        assert entry["args"] == ["__GENERATED_BY_INSTALLER__"]
    else:
        assert entry["command"] == "python" or entry["command"].lower().endswith("python.exe")
        assert entry["args"][-1].replace("\\", "/").endswith("scripts/orpheus_fact_stdio.py")
    assert "url" not in entry
    assert "bearer_token_env_var" not in entry

    import subprocess
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    names = {tool.name for tool in asyncio.run(build_server(GitFactStore(tmp_path)).list_tools())}
    assert names == {"fact_search", "fact_get", "candidate_submit", "candidate_submit_files", "submission_get", "fact_issue_report"}


def test_file_artifacts_are_read_directly_without_command_output(tmp_path):
    script = tmp_path / "run.py"
    report = tmp_path / "report.md"
    result = tmp_path / "result.jsonl"
    script.write_text("print(1)\n", encoding="utf-8")
    report.write_text("# Report\n\nResult: 1.\n", encoding="utf-8")
    result.write_text('{"result":1}\n' * 10000, encoding="utf-8")
    artifacts = load_file_artifacts([
        {"path": str(script), "kind": "script"},
        {"path": str(report), "kind": "report"},
        {"path": str(result), "kind": "data"},
    ])
    assert [artifact.name for artifact in artifacts] == ["run.py", "report.md", "result.jsonl"]
    assert artifacts[2].content == result.read_text(encoding="utf-8")


def test_configured_stdio_process_queries_empty_fact_store_without_mojibake():
    initialized, result = _query(_portable_entry())
    assert str(initialized.protocol_version) == "2025-11-25"
    assert not result.is_error
    assert result.content[0].text.strip() == '{\n  "facts": []\n}'


@pytest.mark.skipif(os.name != "nt", reason="installed plugin config is Windows-specific")
def test_installed_windows_configured_stdio_process_queries_empty_fact_store():
    config = json.loads((ROOT / "plugins/orpheus/.mcp.json").read_text(encoding="utf-8"))
    if config["mcpServers"]["orpheus-fact"]["command"] == "__GENERATED_BY_INSTALLER__":
        pytest.skip("Source template requires installation; generated configuration is checked by the installer tests and release smoke test")
    initialized, result = _query(config["mcpServers"]["orpheus-fact"])
    assert str(initialized.protocol_version) == "2025-11-25"
    assert not result.is_error
    assert result.content[0].text.strip() == '{\n  "facts": []\n}'
