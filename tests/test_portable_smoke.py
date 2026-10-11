from pathlib import Path
import hashlib
import json


def test_portable_template_is_empty_and_generic():
    root = Path(__file__).parents[1]
    assert (root / "templates/facts/MANIFEST.json").exists()
    assert (root / "templates/facts/README.md").exists()
    assert not any((root / "templates").rglob("fact-*.md"))


def test_portable_git_audit_script_is_available():
    root = Path(__file__).parents[1]
    assert (root / "scripts/audit_fact_change.py").exists()
    assert (root / "scripts/install_portable.ps1").exists()


def test_installer_template_matches_its_integrity_manifest():
    root = Path(__file__).parents[1]
    manifest = json.loads((root / "templates/facts/MANIFEST.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["files"].items():
        assert hashlib.sha256((root / "templates" / relative).read_bytes()).hexdigest() == digest
