import hashlib
import json
from pathlib import Path
import subprocess

from scripts.audit_fact_change import audit


def _repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Audit Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=tmp_path, check=True)
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts/MANIFEST.json").write_text(
        '{"format": 1, "generated": "base", "files": {}}\n', encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "facts"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _commit(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "facts"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def test_canonical_change_requires_matching_manifest_and_records_lkg(tmp_path):
    repo = _repo(tmp_path)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    body = b"# Audit-only metadata\n"
    (repo / "facts/README.md").write_bytes(body)
    manifest = {"format": 1, "generated": "head", "files": {
        "facts/README.md": hashlib.sha256(body).hexdigest()}}
    (repo / "facts/MANIFEST.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8", newline="\n")
    head = _commit(repo, "canonical change with manifest")
    report = audit(repo, base, head)
    assert report["status"] == "PASS"
    assert report["manifest_pairing"] == "PASS"
    assert report["last_known_good_commit"] == head
    assert report["evidence_scope"] == "paths_hashes_counts_only"
    assert "Audit-only metadata" not in json.dumps(report, ensure_ascii=False)


def test_manifest_only_change_is_rejected(tmp_path):
    repo = _repo(tmp_path)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "facts/MANIFEST.json").write_text(
        '{"format": 1, "generated": "manifest-only", "files": {}}\n', encoding="utf-8", newline="\n")
    head = _commit(repo, "manifest only")
    report = audit(repo, base, head)
    assert report["status"] == "FAILED"
    assert report["errors"] == ["MANIFEST_ONLY_CHANGE"]
