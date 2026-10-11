"""Audit canonical Fact changes between two Git commits.

The report contains paths, hashes, counts, and integrity results only. It does
not copy Fact statements, proofs, prompts, or source excerpts into the report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service"))

from orpheus_fact.git_facts import GitFactStore  # noqa: E402


CANONICAL_PREFIXES = ("facts/", "candidates/", "reviews/", "requests/")
MATERIALIZED_PREFIXES = CANONICAL_PREFIXES + ("issues/", "incidents/")


def _git(root: Path, args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=False,
                            capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode:
        raise RuntimeError("GIT_COMMAND_FAILED:" + " ".join(args[:3]))
    return result.stdout.strip()


def _resolve_commit(root: Path, value: str) -> str:
    return _git(root, ["rev-parse", "--verify", value + "^{commit}"])


def _changed_paths(root: Path, base: str | None, head: str) -> list[str]:
    if not base or set(base) == {"0"}:
        output = _git(root, ["diff-tree", "--root", "--no-commit-id", "--name-status", "-r", head])
    else:
        output = _git(root, ["diff", "--name-status", "--find-renames", base, head])
    paths = set()
    for line in output.splitlines():
        fields = line.split("\t")
        for path in fields[1:]:
            if any(path.startswith(prefix) for prefix in CANONICAL_PREFIXES):
                paths.add(path)
    return sorted(paths)


def _integrity_at_commit(root: Path, commit: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="orpheus-fact-audit-") as temp:
        target = Path(temp)
        subprocess.run(["git", "init", "-q"], cwd=target, check=True,
                       capture_output=True)
        names = _git(root, ["ls-tree", "-r", "--name-only", commit]).splitlines()
        for name in names:
            if not any(name.startswith(prefix) for prefix in MATERIALIZED_PREFIXES):
                continue
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=root))
        return GitFactStore(target).integrity_check(record_incident=False)


def audit(root: Path, base: str | None, head: str) -> dict:
    resolved_head = _resolve_commit(root, head)
    resolved_base = None
    if base and set(base) != {"0"}:
        resolved_base = _resolve_commit(root, base)
    changed = _changed_paths(root, resolved_base, resolved_head)
    canonical = [path for path in changed if path != "facts/MANIFEST.json"]
    manifest_changed = "facts/MANIFEST.json" in changed
    pairing_errors = []
    if canonical and not manifest_changed:
        pairing_errors.append("CANONICAL_CHANGE_WITHOUT_MANIFEST")
    if manifest_changed and not canonical:
        pairing_errors.append("MANIFEST_ONLY_CHANGE")
    head_integrity = _integrity_at_commit(root, resolved_head)
    base_integrity = (_integrity_at_commit(root, resolved_base) if resolved_base else
                      {"status": "UNAVAILABLE", "errors": [], "facts": None})
    errors = pairing_errors + (["HEAD_INTEGRITY_FAILED"] if head_integrity["status"] != "PASS" else [])
    last_known_good = (resolved_head if head_integrity["status"] == "PASS" else
                       resolved_base if base_integrity["status"] == "PASS" else None)
    return {
        "format": 1,
        "status": "PASS" if not errors else "FAILED",
        "base_commit": resolved_base,
        "head_commit": resolved_head,
        "changed_canonical_paths": changed,
        "canonical_change": bool(canonical),
        "manifest_changed": manifest_changed,
        "manifest_pairing": "PASS" if not pairing_errors else "FAILED",
        "base_integrity": base_integrity,
        "head_integrity": head_integrity,
        "errors": errors,
        "last_known_good_commit": last_known_good,
        "evidence_scope": "paths_hashes_counts_only",
    }


def _markdown(report: dict) -> str:
    lkg = report["last_known_good_commit"] or "NONE"
    errors = ", ".join(report["errors"]) or "none"
    return ("# Fact integrity audit\n\n"
            f"- Status: `{report['status']}`\n"
            f"- Base commit: `{report['base_commit'] or 'NONE'}`\n"
            f"- Head commit: `{report['head_commit']}`\n"
            f"- Canonical change: `{report['canonical_change']}`\n"
            f"- Manifest pairing: `{report['manifest_pairing']}`\n"
            f"- Last known good commit: `{lkg}`\n"
            f"- Errors: `{errors}`\n\n"
            "This summary contains paths, hashes, counts, and statuses only; it does not contain Fact text, proofs, prompts, or source excerpts.\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit canonical Fact changes without exporting Fact content")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base", required=True, help="base commit, or all-zero push SHA")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.root.resolve(), args.base, args.head)
    except Exception as exc:
        report = {"format": 1, "status": "FAILED", "errors": [str(exc)],
                  "evidence_scope": "paths_hashes_counts_only"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(_markdown(report), encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "output": str(args.output),
                      "last_known_good_commit": report.get("last_known_good_commit")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
