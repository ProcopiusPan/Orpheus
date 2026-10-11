import json
import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "plugins/orpheus/scripts/sync_workspace.py"
SPEC = importlib.util.spec_from_file_location("orpheus_sync_workspace", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
sync_workspace = MODULE.sync_workspace
discover_facts = MODULE.discover_facts


def _fact_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "facts/fact-test-one").mkdir(parents=True)
    (repo / "reviews").mkdir()
    metadata = {
        "fact_id": "fact-test-one",
        "version": 1,
        "status": "ACTIVE",
        "evidence_level": "AI_REVIEWED",
        "admitted": "2026-09-11T00:00:00+00:00",
        "dependencies": [],
        "candidate_digest": "a" * 64,
        "review_digest": "b" * 64,
    }
    (repo / "facts/fact-test-one/v1.json").write_text(json.dumps(metadata), encoding="utf-8")
    (repo / "facts/fact-test-one/v1.md").write_text("# A test Fact\n\n## 命题\n\n对所有 $x$ 成立。\n", encoding="utf-8")
    (repo / "reviews" / f"{'a' * 64}.md").write_text("# PASS\n", encoding="utf-8")
    (repo / "reviews" / f"{'a' * 64}.json").write_text("{}", encoding="utf-8")
    return repo


def _add_fact(repo: Path, fact_id: str, title: str, digest_seed: str) -> None:
    (repo / f"facts/{fact_id}").mkdir(parents=True)
    metadata = {
        "fact_id": fact_id,
        "version": 1,
        "status": "ACTIVE",
        "evidence_level": "AI_REVIEWED",
        "admitted": "2026-09-11T00:00:00+00:00",
        "dependencies": [],
        "candidate_digest": digest_seed * 64,
        "review_digest": "c" * 64,
    }
    (repo / f"facts/{fact_id}/v1.json").write_text(json.dumps(metadata), encoding="utf-8")
    (repo / f"facts/{fact_id}/v1.md").write_text(f"# {title}\n\n## 命题\n\n成立。\n", encoding="utf-8")
    (repo / "reviews" / f"{digest_seed * 64}.md").write_text("# PASS\n", encoding="utf-8")
    (repo / "reviews" / f"{digest_seed * 64}.json").write_text("{}", encoding="utf-8")


def _add_fact_version(repo: Path, fact_id: str, version: int, title: str, digest_seed: str) -> None:
    metadata = {
        "fact_id": fact_id,
        "version": version,
        "status": "ACTIVE",
        "evidence_level": "AI_REVIEWED",
        "admitted": "2026-09-11T00:00:00+00:00",
        "dependencies": [],
        "candidate_digest": digest_seed * 64,
        "review_digest": "c" * 64,
    }
    fact_dir = repo / f"facts/{fact_id}"
    (fact_dir / f"v{version}.json").write_text(json.dumps(metadata), encoding="utf-8")
    (fact_dir / f"v{version}.md").write_text(f"# {title}\n\n## 命题\n\n版本 {version}。\n", encoding="utf-8")
    (repo / "reviews" / f"{digest_seed * 64}.md").write_text("# PASS\n", encoding="utf-8")
    (repo / "reviews" / f"{digest_seed * 64}.json").write_text("{}", encoding="utf-8")


def test_workspace_sync_migrates_standard_structure_and_is_idempotent(tmp_path):
    repo = _fact_repo(tmp_path)
    workspace = tmp_path / "workspace"
    papers = workspace / "papers"
    papers.mkdir(parents=True)
    (papers / "Author-2020-Example.pdf").write_bytes(b"existing paper")
    (papers / "Author-2020-Example.md").write_text("# Existing paper\n", encoding="utf-8")
    problem = workspace / "example-problem"
    problem.mkdir(parents=True)
    (problem / "README.md").write_text("# Problem\n\n[[研究结论与证明]]\n", encoding="utf-8")
    (problem / "研究结论与证明.md").write_text("# Proof\n", encoding="utf-8")
    (problem / "Fact候选.md").write_text("# Submission\n", encoding="utf-8")

    first = sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    assert first["status"] == "PASS"
    assert (workspace / "papers").is_dir()
    assert (papers / "Author-2020-Example.pdf").read_bytes() == b"existing paper"
    assert (papers / "Author-2020-Example.md").read_text(encoding="utf-8") == "# Existing paper\n"
    assert (workspace / "Orpheus研究/example-problem/问题与进展.md").exists()
    assert (workspace / "Orpheus研究/example-problem/证明草稿.md").exists()
    assert (workspace / "Orpheus研究/example-problem/提交与审查.md").exists()
    assert "[[证明草稿]]" in (workspace / "Orpheus研究/example-problem/问题与进展.md").read_text(encoding="utf-8")

    projection = next(p for p in (workspace / "Orpheus研究/Fact参考").glob("*.md") if p.name != "Fact索引.md")
    projection.write_text(projection.read_text(encoding="utf-8") + "\n用户批注：保留。\n", encoding="utf-8")
    second = sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    assert second["status"] == "PASS"
    final = projection.read_text(encoding="utf-8")
    assert "用户批注：保留。" in final
    assert final.count("ORPHEUS-SYNC-META:BEGIN") == 1
    assert final.count("fact-test-one") >= 1
    assert final.count("## Orpheus 同步元数据") == 1
    assert "Fact索引.md" not in projection.name


def test_workspace_check_reports_missing_fact_projection_without_writing(tmp_path):
    repo = _fact_repo(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "Orpheus研究/Fact参考").mkdir(parents=True)
    result = sync_workspace(workspace, repo, apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert result["status"] == "CONFLICT"
    assert any("MISSING_FACT_PROJECTION" in issue for issue in result["issues"])
    assert any("MISSING_DIRECTORY: papers" in issue for issue in result["issues"])
    assert not list(workspace.rglob("*.md"))


def test_paper_requires_sidecar_and_sync_does_not_rewrite_paper(tmp_path):
    repo = _fact_repo(tmp_path)
    workspace = tmp_path / "workspace"
    papers = workspace / "papers"
    papers.mkdir(parents=True)
    paper = papers / "Author-2020-Example.pdf"
    paper.write_bytes(b"paper bytes")
    result = sync_workspace(workspace, repo, apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert result["status"] == "CONFLICT"
    assert any("MISSING_PAPER_METADATA" in issue for issue in result["issues"])
    sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    assert paper.read_bytes() == b"paper bytes"
    assert not paper.with_suffix(".md").exists()
    paper.with_suffix(".md").write_text("# Existing metadata\n", encoding="utf-8")
    result = sync_workspace(workspace, repo, apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert result["status"] == "PASS"
    assert paper.with_suffix(".md").read_text(encoding="utf-8") == "# Existing metadata\n"


def test_workspace_sync_includes_all_active_facts(tmp_path):
    repo = _fact_repo(tmp_path)
    _add_fact(repo, "fact-test-two", "Second test Fact", "d")
    _add_fact(repo, "fact-test-three", "Third test Fact", "e")
    workspace = tmp_path / "workspace"
    result = sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    assert result["status"] == "PASS"
    assert result["active_facts"] == 3
    index = (workspace / "Orpheus研究/Fact参考/Fact索引.md").read_text(encoding="utf-8")
    for fact_id in ("fact-test-one", "fact-test-two", "fact-test-three"):
        assert fact_id in index
    assert len(list((workspace / "Orpheus研究/Fact参考").glob("*.md"))) == 4


def test_discover_facts_keeps_requested_version_scope_per_fact(tmp_path):
    repo = _fact_repo(tmp_path)
    _add_fact_version(repo, "fact-test-one", 2, "A test Fact v2", "f")
    _add_fact(repo, "fact-test-two", "Second test Fact", "d")

    facts = discover_facts(repo)

    assert {(fact.fact_id, fact.version) for fact in facts} == {
        ("fact-test-one", 2),
        ("fact-test-two", 1),
    }


def test_incremental_sync_updates_only_selected_projection_and_preserves_index(tmp_path):
    repo = _fact_repo(tmp_path)
    _add_fact(repo, "fact-test-two", "Second test Fact", "d")
    workspace = tmp_path / "workspace"
    sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    first_projection = next((workspace / "Orpheus研究/Fact参考").glob("A test Fact*.md"))
    before = first_projection.stat().st_mtime_ns

    _add_fact(repo, "fact-test-three", "Third test Fact", "e")
    result = sync_workspace(
        workspace,
        repo,
        apply=True,
        sync_time="2026-09-11T01:00:00+00:00",
        fact_id="fact-test-three",
        version=1,
    )

    assert result["status"] == "PASS"
    assert result["scope"] == "incremental"
    assert result["fact_ids"] == ["fact-test-three"]
    assert first_projection.stat().st_mtime_ns == before
    index = (workspace / "Orpheus研究/Fact参考/Fact索引.md").read_text(encoding="utf-8")
    for fact_id in ("fact-test-one", "fact-test-two", "fact-test-three"):
        assert fact_id in index
    assert (workspace / "Orpheus研究/Fact参考/Third test Fact.md").exists()


def test_default_repo_root_uses_mcp_entry_from_cached_plugin(tmp_path, monkeypatch):
    cache_plugin = tmp_path / "cache/personal/orpheus/skills"
    plugin = cache_plugin / "plugin"
    scripts = tmp_path / "real-repo/scripts"
    (plugin / "scripts").mkdir(parents=True)
    scripts.mkdir(parents=True)
    (tmp_path / "real-repo/.mcp.json").write_text("{}", encoding="utf-8")
    (tmp_path / "real-repo/facts").mkdir()
    entry = scripts / "orpheus_fact_stdio.py"
    entry.write_text("", encoding="utf-8")
    (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": {"orpheus-fact": {"args": [str(entry)]}}}), encoding="utf-8")
    monkeypatch.setattr(MODULE, "__file__", str(plugin / "scripts/sync_workspace.py"))
    assert MODULE.default_repo_root() == (tmp_path / "real-repo").resolve()


def test_check_detects_canonical_projection_change_but_ignores_sync_clock(tmp_path):
    repo = _fact_repo(tmp_path)
    workspace = tmp_path / "workspace"
    sync_workspace(workspace, repo, apply=True, sync_time="2020-01-01T00:00:00+00:00")
    result = sync_workspace(workspace, repo, apply=False, sync_time="2030-01-01T00:00:00+00:00")
    assert result["status"] == "PASS"
    assert all(action.startswith("current Fact projection") for action in result["actions"])
    metadata = repo / "facts/fact-test-one/v1.json"
    value = json.loads(metadata.read_text(encoding="utf-8"))
    value["evidence_level"] = "FORMAL"
    metadata.write_text(json.dumps(value), encoding="utf-8")
    result = sync_workspace(workspace, repo, apply=False, sync_time="2030-01-01T00:00:00+00:00")
    assert result["status"] == "CONFLICT"
    assert any("STALE_FACT_PROJECTION" in issue for issue in result["issues"])
    assert any(action.startswith("would update Fact projection") for action in result["actions"])


def test_workspace_sync_updates_revoked_fact_status(tmp_path):
    repo = _fact_repo(tmp_path)
    workspace = tmp_path / "workspace"
    sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    metadata_path = repo / "facts/fact-test-one/v1.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["status"] = "REVOKED"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    result = sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T01:00:00+00:00")
    assert result["total_facts"] == 1
    assert result["active_facts"] == 0
    projection = next((workspace / "Orpheus研究/Fact参考").glob("A test Fact*.md"))
    assert "- 状态：REVOKED" in projection.read_text(encoding="utf-8")


def test_same_title_facts_get_stable_distinct_projections(tmp_path):
    repo = _fact_repo(tmp_path)
    _add_fact(repo, "fact-test-two", "A test Fact", "d")
    workspace = tmp_path / "workspace"
    result = sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    assert result["total_facts"] == 2
    projections = sorted((workspace / "Orpheus研究/Fact参考").glob("A test Fact*.md"))
    assert len(projections) == 2
    assert any("(fact-tes)" in path.name for path in projections)
    again = sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    assert again["status"] == "PASS"
    assert len(list((workspace / "Orpheus研究/Fact参考").glob("A test Fact*.md"))) == 2


def test_projection_lookup_ignores_fact_ids_mentioned_only_as_dependencies(tmp_path):
    repo = _fact_repo(tmp_path)
    _add_fact(repo, "fact-test-two", "Second test Fact", "d")
    second_metadata = repo / "facts/fact-test-two/v1.json"
    metadata = json.loads(second_metadata.read_text(encoding="utf-8"))
    metadata["dependencies"] = [{"fact_id": "fact-test-one", "version": 1}]
    second_metadata.write_text(json.dumps(metadata), encoding="utf-8")
    second_markdown = repo / "facts/fact-test-two/v1.md"
    second_markdown.write_text(
        second_markdown.read_text(encoding="utf-8")
        + "\n## 依赖\n\n- [fact-test-one v1](../fact-test-one/v1.md)\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")

    result = sync_workspace(
        workspace,
        repo,
        apply=True,
        sync_time="2026-09-11T01:00:00+00:00",
        fact_id="fact-test-one",
        version=1,
    )

    assert result["status"] == "PASS"
    first = (workspace / "Orpheus研究/Fact参考/A test Fact.md").read_text(encoding="utf-8")
    second = (workspace / "Orpheus研究/Fact参考/Second test Fact.md").read_text(encoding="utf-8")
    assert "Fact ID：fact-test-one" in first
    assert "Fact ID：fact-test-two" in second


def test_summary_projection_is_rejected_until_canonical_proof_is_present(tmp_path):
    repo = _fact_repo(tmp_path)
    workspace = tmp_path / "workspace"
    fact_dir = workspace / "Orpheus研究/Fact参考"
    fact_dir.mkdir(parents=True)
    projection = fact_dir / "A test Fact.md"
    projection.write_text("# A test Fact\n\n证明摘要：略。\n\n用户批注：保留。\n", encoding="utf-8")
    checked = sync_workspace(workspace, repo, apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert checked["status"] == "CONFLICT"
    assert any("STALE_FACT_PROOF" in issue for issue in checked["issues"])
    sync_workspace(workspace, repo, apply=True, sync_time="2026-09-11T00:00:00+00:00")
    content = projection.read_text(encoding="utf-8")
    assert "## 命题" in content and "对所有 $x$ 成立。" in content
    assert "用户批注：保留。" in projection.read_text(encoding="utf-8")
    assert content.index("ORPHEUS-CANONICAL-FACT:BEGIN") < content.index("历史投影/用户批注")
