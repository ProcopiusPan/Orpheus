"""Build a portable source archive without repository state or private Facts."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import zipfile


def select_release_files(root: Path) -> list[Path]:
    """Select generic portable source; never select canonical data or Git state."""
    selected = []
    for directory, pattern in (("service/orpheus_fact", "*.py"), ("plugins/orpheus", "*"),
                               ("templates", "*"), ("marketplace", "*")):
        selected.extend(p for p in (root / directory).rglob(pattern) if p.is_file() and "__pycache__" not in p.parts and p.name != "release-package.json")
    for name in ("test_portable_smoke.py", "test_git_facts.py", "test_audit_fact_change.py"):
        selected.append(root / "tests" / name)
    for name in ("README.md", "README.en.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", ".gitignore", ".gitattributes", "pyproject.toml", "requirements.lock.txt"):
        selected.append(root / name)
    for name in ("audit_fact_change.py", "check_markdown.py", "fact_admin.py", "orpheus_fact_stdio.py", "install_portable.ps1"):
        selected.append(root / "scripts" / name)
    selected.append(root / ".github" / "workflows" / "fact-integrity.yml")
    for name in ("快速开始.md", "安装便携包.md", "Zotero适配与使用.md", "Fact维护说明.md"):
        selected.append(root / "docs" / name)
    return sorted(set(selected))


def portable_blobs(root: Path, selected: list[Path]) -> dict[str, bytes]:
    """Read selected files and scrub the development machine's MCP path."""
    blobs = {}
    for path in selected:
        name = path.relative_to(root).as_posix()
        if name == "README.md":
            data = path.read_bytes()
        elif name == "plugins/orpheus/.mcp.json":
            data = (json.dumps({"mcpServers": {"orpheus-fact": {
                "command": "__GENERATED_BY_INSTALLER__",
                "args": ["__GENERATED_BY_INSTALLER__"]}}}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        else:
            data = path.read_bytes()
        blobs[name] = data
    return blobs


def private_payload_markers(root: Path) -> set[str]:
    """Return private strings that must not survive extraction in any text encoding."""
    markers = set(os.environ.get("ORPHEUS_PRIVATE_MARKERS", "").splitlines())
    home = str(Path.home())
    if home:
        markers.add(home)
        markers.add(home.replace("\\", "/"))
    for path in (root / "facts").glob("fact-*/v*.md"):
        text = path.read_text(encoding="utf-8")
        markers.add(text)
        markers.update(re.findall(r"fact-[0-9a-f]{16,}", text))
    for path in (root / "facts").glob("fact-*/v*.json"):
        text = path.read_text(encoding="utf-8")
        markers.update(re.findall(r"fact-[0-9a-f]{16,}", text))
    return {marker for marker in markers if marker}


def payload_texts(data: bytes) -> list[str]:
    """Decode common Unicode forms so package scans cannot rely on ASCII bytes."""
    texts = []
    for encoding in ("utf-8", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            texts.append(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    return texts


def main():
    root = Path(__file__).resolve().parents[1]
    if (root / "研究文档与Obsidian规范.md").read_bytes() != (root / "plugins/orpheus/references/obsidian.md").read_bytes():
        raise SystemExit("Obsidian normative copy differs; reconcile it before packaging.")
    check = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=root,
                           capture_output=True, encoding="utf-8", timeout=120,
                           env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    if check.returncode:
        raise SystemExit("Tests failed; no release archive created.\n" + check.stdout + check.stderr)
    selected = select_release_files(root)
    blobs = portable_blobs(root, selected)
    forbidden = ("facts/", "candidates/", "reviews/", "requests/", "issues/", "incidents/", ".git/")
    if any(name.startswith(forbidden) for name in blobs):
        raise SystemExit("private or repository state selected for portable package")
    markers = private_payload_markers(root)
    if any(marker in text for data in blobs.values() for text in payload_texts(data) for marker in markers):
        raise SystemExit("machine-specific path or private Fact content selected for portable package")
    manifest = {"kind":"ORPHEUS_PORTABLE_DISTRIBUTION", "remote_protection_verified":False,
                "private_data_excluded":True,
                "test_result":check.stdout.strip(),
                "files":{name:hashlib.sha256(data).hexdigest() for name,data in blobs.items()}}
    target = root / ".runtime/releases" / ("orpheus-" + uuid.uuid4().hex + ".zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in blobs.items():
            archive.writestr(name, data)
        archive.writestr("release-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name,digest in manifest["files"].items())
    result = {"archive":target.relative_to(root).as_posix(), "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
              "files":len(blobs), "archive_integrity":"PASS", "test_result":check.stdout.strip(),
              "deployment":"LOCAL_STDIO_ONLY", "scope":"Portable source package with empty Fact templates; install creates a new local Git history."}
    (root / "dist").mkdir(exist_ok=True)
    (root / "dist/release-package.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
