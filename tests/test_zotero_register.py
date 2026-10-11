import hashlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "plugins/orpheus/scripts/register_zotero_paper.py"
SPEC = importlib.util.spec_from_file_location("orpheus_zotero_register", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

SYNC = ROOT / "plugins/orpheus/scripts/sync_workspace.py"
SYNC_SPEC = importlib.util.spec_from_file_location("orpheus_sync_for_zotero_register", SYNC)
SYNC_MODULE = importlib.util.module_from_spec(SYNC_SPEC)
assert SYNC_SPEC.loader is not None
sys.modules[SYNC_SPEC.name] = SYNC_MODULE
SYNC_SPEC.loader.exec_module(SYNC_MODULE)


def test_register_accepts_official_helper_normalized_shape_and_hashes(tmp_path):
    source = tmp_path / "zotero" / "paper.pdf"
    source.parent.mkdir()
    source.write_bytes(b"fixture pdf")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    # Shape captured from the installed official helper's read-only search:
    # [{"key": "FU57LIDV", "itemType": "journalArticle", "title":
    # "Parametrized higher category theory", "creators": ["Jay Shah"],
    # "year": "2023"}]
    metadata = {"key": "FU57LIDV", "itemType": "journalArticle", "title": "Parametrized higher category theory", "creators": ["Jay Shah"], "year": "2023"}
    result = MODULE.register_paper(metadata, source, workspace, attachment_key="ATTACH123", related_questions=["Question A"])
    assert result["status"] == "REGISTERED"
    sidecar = Path(result["sidecar"])
    text = sidecar.read_text(encoding="utf-8")
    assert "authors:\n  - 'Jay Shah'" in text
    assert "year: '2023'" in text
    assert "zotero_item_key: 'FU57LIDV'" in text
    assert "zotero_attachment_key: 'ATTACH123'" in text

    raw_workspace = tmp_path / "raw-workspace"
    raw_workspace.mkdir()
    raw = {"key": "RAW123", "data": {"key": "RAW123", "title": "Raw item", "date": "2022", "creators": [{"firstName": "Grace", "lastName": "Hopper"}]}}
    raw_result = MODULE.register_paper(raw, source, raw_workspace, attachment_key="RAWATTACH")
    assert "Hopper-2022-Raw item" in Path(raw_result["sidecar"]).name


def test_sync_reports_hash_mismatch_for_zotero_targets(tmp_path):
    source = tmp_path / "zotero.pdf"
    source.write_bytes(b"original")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    metadata = {"key": "ITEM1234", "title": "Hash Test", "creators": ["Author"], "year": "2024"}
    result = MODULE.register_paper(metadata, source, workspace, attachment_key="ATTACH123")
    paper = Path(result["paper_file"])
    paper.write_bytes(b"changed")
    checked = SYNC_MODULE.sync_workspace(workspace, tmp_path / "empty-repo", apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert any("PAPER_HASH_MISMATCH" in issue for issue in checked["issues"])

    source.write_bytes(b"original")
    path_workspace = tmp_path / "path-workspace"
    path_workspace.mkdir()
    MODULE.register_paper(metadata, source, path_workspace, attachment_key="ATTACH999", storage_mode="path")
    source.write_bytes(b"changed again")
    checked = SYNC_MODULE.sync_workspace(path_workspace, tmp_path / "empty-repo", apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert any("PAPER_HASH_MISMATCH" in issue for issue in checked["issues"])


def test_sync_accepts_path_registration_and_manual_original_sidecar(tmp_path):
    source = tmp_path / "zotero.pdf"
    source.write_bytes(b"zotero attachment")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    metadata = {"key": "ITEMPATH", "title": "Path Test", "creators": ["Author"], "year": "2024"}
    result = MODULE.register_paper(metadata, source, workspace, attachment_key="ATTACHPATH", storage_mode="path")
    assert result["paper_file"] is None
    assert result["storage_mode"] == "path_reference"

    manual = workspace / "papers/Manual-2025-Note.pdf"
    manual.write_bytes(b"manual original")
    manual_hash = hashlib.sha256(manual.read_bytes()).hexdigest()
    manual.with_suffix(".md").write_text(
        "---\n"
        "title: 'Manual Note'\n"
        f"sha256: '{manual_hash}'\n"
        "source_mode: 'manual_original'\n"
        "zotero_import_status: 'pending'\n"
        "storage_mode: 'manual_original'\n"
        "---\n\n# 文献阅读入口\n",
        encoding="utf-8",
    )
    SYNC_MODULE.sync_workspace(workspace, tmp_path / "empty-repo", apply=True, sync_time="2026-09-11T00:00:00+00:00")
    checked = SYNC_MODULE.sync_workspace(workspace, tmp_path / "empty-repo", apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert checked["status"] == "PASS"
    assert not any("MISSING_PAPER_METADATA" in issue for issue in checked["issues"])
    assert not any("MISSING_ZOTERO" in issue for issue in checked["issues"])

    manual.write_bytes(b"changed manual original")
    checked = SYNC_MODULE.sync_workspace(workspace, tmp_path / "empty-repo", apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert any("PAPER_HASH_MISMATCH" in issue for issue in checked["issues"])


def test_sync_generates_manual_original_hash_without_manual_entry(tmp_path):
    workspace = tmp_path / "workspace"
    papers = workspace / "papers"
    papers.mkdir(parents=True)
    manual = papers / "Manual-2025-Note.pdf"
    manual.write_bytes(b"manual original")
    manual.with_suffix(".md").write_text(
        "---\n"
        "title: 'Manual Note'\n"
        "sha256: ''\n"
        "storage_mode: 'manual_original'\n"
        "---\n\n# 文献阅读入口\n",
        encoding="utf-8",
    )
    SYNC_MODULE.sync_workspace(workspace, tmp_path / "empty-repo", apply=True, sync_time="2026-09-11T00:00:00+00:00")
    sidecar = manual.with_suffix(".md")
    assert "sha256: ''" not in sidecar.read_text(encoding="utf-8")
    expected = hashlib.sha256(manual.read_bytes()).hexdigest()
    assert f"sha256: '{expected}'" in sidecar.read_text(encoding="utf-8")
    checked = SYNC_MODULE.sync_workspace(workspace, tmp_path / "empty-repo", apply=False, sync_time="2026-09-11T00:00:00+00:00")
    assert checked["status"] == "PASS"
