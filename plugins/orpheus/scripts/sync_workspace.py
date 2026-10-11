"""Deterministic Orpheus workspace structure and Fact projection helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


SYNC_BEGIN = "<!-- ORPHEUS-SYNC-META:BEGIN -->"
SYNC_END = "<!-- ORPHEUS-SYNC-META:END -->"
INDEX_BEGIN = "<!-- ORPHEUS-SYNC-INDEX:BEGIN -->"
INDEX_END = "<!-- ORPHEUS-SYNC-INDEX:END -->"
CANONICAL_BEGIN = "<!-- ORPHEUS-CANONICAL-FACT:BEGIN -->"
CANONICAL_END = "<!-- ORPHEUS-CANONICAL-FACT:END -->"


@dataclass(frozen=True)
class Fact:
    fact_id: str
    version: int
    status: str
    evidence_level: str
    admitted: str
    dependencies: tuple[tuple[str, int], ...]
    candidate_digest: str
    review_digest: str
    markdown: str
    title: str
    source_md: Path
    review_md: Path
    review_json: Path


def default_repo_root() -> Path:
    plugin = Path(__file__).resolve().parents[1]
    config = plugin / ".mcp.json"
    if not config.exists():
        raise RuntimeError(f"missing plugin configuration: {config}")
    payload = json.loads(config.read_text(encoding="utf-8"))
    server = payload.get("mcpServers", {}).get("orpheus-fact", {})
    args = server.get("args")
    if not isinstance(args, list):
        raise RuntimeError(f"invalid orpheus-fact args in {config}")
    entry = next((Path(arg) for arg in args if str(arg).lower().endswith("orpheus_fact_stdio.py")), None)
    if entry is None or not entry.is_absolute() or entry.name != "orpheus_fact_stdio.py":
        raise RuntimeError(f".mcp.json must name an absolute orpheus_fact_stdio.py path: {config}")
    entry = entry.resolve()
    if not entry.exists() or entry.parent.name != "scripts":
        raise RuntimeError(f"configured Fact entry does not exist under a scripts directory: {entry}")
    repo = entry.parent.parent
    if not (repo / "facts").is_dir():
        raise RuntimeError(f"configured Fact entry does not identify an Orpheus repository: {repo}")
    return repo


def _version(path: Path) -> int:
    match = re.fullmatch(r"v(\d+)\.json", path.name)
    if not match:
        raise ValueError(f"invalid Fact metadata filename: {path}")
    return int(match.group(1))


def _first_heading(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# ") and line[2:].strip():
            return line[2:].strip()
    return fallback


def _safe_filename(title: str, fact_id: str) -> str:
    name = re.sub(r'[<>:"/\\\\|?*]', " ", title).strip()
    name = re.sub(r"\s+", " ", name)
    return (name or fact_id) + ".md"


def discover_facts(repo_root: Path, *, fact_id: str | None = None, version: int | None = None) -> list[Fact]:
    facts: list[Fact] = []
    requested_fact_id = fact_id
    requested_version = version
    fact_dirs = [repo_root / "facts" / requested_fact_id] if requested_fact_id else sorted((repo_root / "facts").glob("fact-*"))
    for fact_dir in fact_dirs:
        if not fact_dir.is_dir():
            continue
        metadata_files = sorted(fact_dir.glob("v*.json"), key=_version)
        if not metadata_files:
            continue
        metadata_path = fact_dir / f"v{requested_version}.json" if requested_version is not None else metadata_files[-1]
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata_fact_id = metadata["fact_id"]
        metadata_version = int(metadata["version"])
        source_md = fact_dir / f"v{metadata_version}.md"
        if not source_md.exists():
            raise RuntimeError(f"missing Fact Markdown: {source_md}")
        candidate_digest = metadata["candidate_digest"]
        review_digest = metadata["review_digest"]
        review_md = repo_root / "reviews" / f"{candidate_digest}.md"
        review_json = repo_root / "reviews" / f"{candidate_digest}.json"
        if not review_md.exists() or not review_json.exists():
            raise RuntimeError(f"missing review for {metadata_fact_id} v{metadata_version}: {candidate_digest}")
        markdown = source_md.read_text(encoding="utf-8")
        dependencies = tuple(
            (item["fact_id"], int(item["version"]))
            for item in metadata.get("dependencies", [])
        )
        facts.append(
            Fact(
                fact_id=metadata_fact_id,
                version=metadata_version,
                status=metadata["status"],
                evidence_level=metadata["evidence_level"],
                admitted=metadata["admitted"],
                dependencies=dependencies,
                candidate_digest=candidate_digest,
                review_digest=review_digest,
                markdown=markdown,
                title=_first_heading(markdown, metadata_fact_id),
                source_md=source_md,
                review_md=review_md,
                review_json=review_json,
            )
        )
    return facts


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _metadata_block(fact: Fact, sync_time: str) -> str:
    deps = "无" if not fact.dependencies else "；".join(
        f"{fact_id} v{version}" for fact_id, version in fact.dependencies
    )
    return "\n".join(
        [
            SYNC_BEGIN,
            f"- Fact ID：{fact.fact_id}",
            f"- 版本：{fact.version}",
            f"- 状态：{fact.status}",
            f"- 证据等级：{fact.evidence_level}",
            f"- 接纳时间：{fact.admitted}",
            f"- 最后同步时间：{sync_time}",
            f"- 依赖：{deps}",
            f"- 候选摘要：{fact.candidate_digest}",
            f"- 审查摘要：{fact.review_digest}",
            f"- 正式审查：[Markdown]({_file_uri(fact.review_md)})；[JSON]({_file_uri(fact.review_json)})",
            SYNC_END,
        ]
    )


def _canonical_metadata(fact: Fact) -> list[str]:
    deps = "无" if not fact.dependencies else "；".join(
        f"{fact_id} v{version}" for fact_id, version in fact.dependencies
    )
    return [
        f"- Fact ID：{fact.fact_id}", f"- 版本：{fact.version}", f"- 状态：{fact.status}",
        f"- 证据等级：{fact.evidence_level}", f"- 接纳时间：{fact.admitted}",
        f"- 依赖：{deps}", f"- 候选摘要：{fact.candidate_digest}",
        f"- 审查摘要：{fact.review_digest}",
    ]


def _canonical_body(fact: Fact) -> str:
    rendered = re.sub(
        r"\]\(\.\./\.\./reviews/([^)]*)\)",
        lambda match: f"]({_file_uri(fact.review_md.parent / match.group(1))})",
        fact.markdown.rstrip(),
    )
    rendered = re.sub(
        rf"\]\(v{fact.version}-artifacts/([^)]*)\)",
        lambda match: f"]({_file_uri(fact.source_md.parent / f'v{fact.version}-artifacts' / match.group(1))})",
        rendered,
    )
    return f"{CANONICAL_BEGIN}\n{rendered}\n{CANONICAL_END}"


def _replace_block(text: str, begin: str, end: str, block: str) -> str:
    pattern = re.compile(rf"\n?{re.escape(begin)}.*?{re.escape(end)}\n?", re.DOTALL)
    if pattern.search(text):
        return pattern.sub("\n" + block + "\n", text, count=1)
    return text.rstrip() + "\n\n" + block + "\n"


def _projection_path(fact: Fact, fact_dir: Path) -> Path:
    candidate = fact_dir / _safe_filename(fact.title, fact.fact_id)
    matches: list[Path] = []
    for path in sorted(fact_dir.glob("*.md")):
        if path.name == "Fact索引.md":
            continue
        text = path.read_text(encoding="utf-8")
        main_fact_id = re.search(
            r"(?m)^(?:> )?- Fact ID[：:]\s*`?(fact-[A-Za-z0-9_-]+)`?\s*$",
            text,
        )
        if main_fact_id and main_fact_id.group(1) == fact.fact_id:
            matches.append(path)
    if candidate in matches:
        return candidate
    if matches:
        return matches[0]
    if not candidate.exists():
        return candidate
    existing = candidate.read_text(encoding="utf-8")
    if "fact-" not in existing:
        return candidate
    return fact_dir / f"{candidate.stem} ({fact.fact_id[:8]}).md"


def _sync_projection(fact: Fact, fact_dir: Path, sync_time: str, apply: bool) -> tuple[Path, str, bool]:
    path = _projection_path(fact, fact_dir)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    metadata = _metadata_block(fact, sync_time)
    canonical_stale = (
        old is None
        or SYNC_BEGIN not in (old or "")
        or any(line not in (old or "") for line in _canonical_metadata(fact))
        or _canonical_body(fact) not in (old or "")
    )
    residual = old or ""
    residual = re.sub(rf"\n?{re.escape(CANONICAL_BEGIN)}.*?{re.escape(CANONICAL_END)}\n?", "\n", residual, flags=re.DOTALL)
    residual = re.sub(rf"\n?## Canonical Fact 正文\s*\n?", "\n", residual)
    residual = re.sub(rf"\n?## Orpheus 同步元数据\s*\n?{re.escape(SYNC_BEGIN)}.*?{re.escape(SYNC_END)}\n?", "\n", residual, flags=re.DOTALL)
    residual = residual.strip()
    if residual and not re.search(r"用户批注|用户备注|批注|历史投影", residual):
        residual = ""
    updated = _canonical_body(fact) + "\n\n"
    if residual:
        updated += "## 历史投影/用户批注（非正式 Fact 正文）\n\n" + residual + "\n\n"
    updated += "## Orpheus 同步元数据\n" + metadata + "\n"
    if apply and updated != old:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return path, "updated" if updated != old else "unchanged", canonical_stale


def _problem_dirs(workspace: Path) -> list[Path]:
    reserved = {"Orpheus研究", ".obsidian"}
    return sorted(
        path for path in workspace.iterdir()
        if path.is_dir() and path.name not in reserved and not path.name.startswith(".")
        and any((path / name).exists() for name in ("README.md", "Fact候选.md", "研究结论与证明.md"))
    )


def _set_frontmatter_value(text: str, key: str, value: str) -> str:
    replacement = f"{key}: '{value}'"
    pattern = re.compile(rf"(?m)^{re.escape(key)}:.*$")
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    if text.startswith("---\n"):
        return text.replace("---\n", f"---\n{replacement}\n", 1)
    return text


def _paper_metadata_issues(
    papers: Path,
    workspace: Path,
    *,
    apply: bool,
    actions: list[str],
) -> list[str]:
    if not papers.exists():
        return []
    suffixes = {".pdf", ".html", ".htm", ".epub", ".djvu"}
    issues = [
        f"MISSING_PAPER_METADATA: {paper.relative_to(workspace)}"
        for paper in sorted(papers.rglob("*"))
        if paper.is_file() and paper.suffix.lower() in suffixes
        and not paper.with_suffix(".md").exists()
    ]
    # The project papers/ directory is a registration layer.  Path references
    # intentionally do not copy a large attachment into papers/; they remain
    # valid only while the referenced local file exists.  Hardlink registrations
    # expose a normal reading file while sharing the source data.  Registration
    # and sync generate missing integrity metadata; an existing mismatch stays
    # visible so a changed source is never silently accepted.
    for sidecar in sorted(papers.rglob("*.md")):
        text = sidecar.read_text(encoding="utf-8", errors="replace")
        storage_mode = _frontmatter_value(text, "storage_mode")
        if storage_mode == "manual_original":
            paper_file = _frontmatter_value(text, "paper_file")
            if paper_file:
                paper_path = sidecar.parent / paper_file
            else:
                candidates = sorted(
                    path for path in sidecar.parent.iterdir()
                    if path.is_file()
                    and path.stem == sidecar.stem
                    and path.suffix.lower() in suffixes
                )
                paper_path = candidates[0] if candidates else None
            relative_sidecar = sidecar.relative_to(workspace)
            if paper_path is None or not paper_path.is_file():
                issues.append(f"MISSING_MANUAL_ORIGINAL: {relative_sidecar}")
                continue
            try:
                actual_hash = _sha256_file(paper_path)
            except OSError:
                issues.append(f"PAPER_HASH_UNREADABLE: {relative_sidecar}")
                continue
            expected_hash = _frontmatter_value(text, "sha256")
            if not expected_hash:
                if apply:
                    updated = _set_frontmatter_value(text, "sha256", actual_hash)
                    if updated != text:
                        sidecar.write_text(updated, encoding="utf-8", newline="\n")
                        actions.append(f"generated paper integrity metadata {relative_sidecar}")
                    expected_hash = actual_hash
                else:
                    issues.append(f"PAPER_HASH_NOT_GENERATED: {relative_sidecar}")
                    continue
            if actual_hash != expected_hash:
                issues.append(f"PAPER_HASH_MISMATCH: {relative_sidecar}")
            continue
        if "zotero_item_key:" not in text:
            continue
        if storage_mode == "path_reference":
            attachment_path = _frontmatter_value(text, "attachment_path")
            if not attachment_path or not Path(attachment_path).is_file():
                issues.append(f"MISSING_ZOTERO_ATTACHMENT: {sidecar.relative_to(workspace)}")
            else:
                relative_sidecar = sidecar.relative_to(workspace)
                try:
                    actual_hash = _sha256_file(Path(attachment_path))
                except OSError:
                    issues.append(f"PAPER_HASH_UNREADABLE: {relative_sidecar}")
                    continue
                expected_hash = _frontmatter_value(text, "sha256")
                if not expected_hash:
                    if apply:
                        updated = _set_frontmatter_value(text, "sha256", actual_hash)
                        if updated != text:
                            sidecar.write_text(updated, encoding="utf-8", newline="\n")
                            actions.append(f"generated paper integrity metadata {relative_sidecar}")
                        expected_hash = actual_hash
                    else:
                        issues.append(f"PAPER_HASH_NOT_GENERATED: {relative_sidecar}")
                        continue
                if actual_hash != expected_hash:
                    issues.append(f"PAPER_HASH_MISMATCH: {relative_sidecar}")
        elif storage_mode == "hardlink":
            paper_file = _frontmatter_value(text, "paper_file")
            paper_path = sidecar.parent / paper_file if paper_file else None
            if paper_path is None or not paper_path.is_file():
                issues.append(f"MISSING_ZOTERO_HARDLINK: {sidecar.relative_to(workspace)}")
            else:
                relative_sidecar = sidecar.relative_to(workspace)
                try:
                    actual_hash = _sha256_file(paper_path)
                except OSError:
                    issues.append(f"PAPER_HASH_UNREADABLE: {relative_sidecar}")
                    continue
                expected_hash = _frontmatter_value(text, "sha256")
                if not expected_hash:
                    if apply:
                        updated = _set_frontmatter_value(text, "sha256", actual_hash)
                        if updated != text:
                            sidecar.write_text(updated, encoding="utf-8", newline="\n")
                            actions.append(f"generated paper integrity metadata {relative_sidecar}")
                        expected_hash = actual_hash
                    else:
                        issues.append(f"PAPER_HASH_NOT_GENERATED: {relative_sidecar}")
                        continue
                if actual_hash != expected_hash:
                    issues.append(f"PAPER_HASH_MISMATCH: {relative_sidecar}")
    return issues


def _frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", text)
    if not match:
        return None
    value = re.sub(r"\s+#.*$", "", match.group(1)).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        if value[0] == "'":
            value = value[1:-1].replace("''", "'")
        else:
            value = value[1:-1].replace('""', '"')
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _migrate_problem(workspace: Path, research: Path, source: Path, apply: bool, actions: list[str], issues: list[str]) -> None:
    target = research / source.name
    if source.exists():
        if target.exists():
            issues.append(f"CONFLICT: both legacy and standard problem directories exist: {source.name}")
            return
        actions.append(f"move {source.relative_to(workspace)} -> {target.relative_to(workspace)}")
        if apply:
            shutil.move(str(source), str(target))
    elif not target.exists():
        issues.append(f"MISSING_PROBLEM: {source.name}")
        return
    for old, new in (("README.md", "问题与进展.md"), ("研究结论与证明.md", "证明草稿.md"), ("Fact候选.md", "提交与审查.md")):
        old_path = target / old
        new_path = target / new
        if old_path.exists():
            if new_path.exists():
                issues.append(f"CONFLICT: both {old} and {new} exist in {target.name}")
                continue
            actions.append(f"rename {old_path.relative_to(workspace)} -> {new_path.relative_to(workspace)}")
            if apply:
                shutil.move(str(old_path), str(new_path))
                text = new_path.read_text(encoding="utf-8")
                text = text.replace("[[研究结论与证明]]", "[[证明草稿]]").replace("[[Fact候选]]", "[[提交与审查]]")
                text = text.replace("../Orpheus研究/", "../")
                new_path.write_text(text, encoding="utf-8", newline="\n")
    if apply:
        index = research / "研究索引.md"
        if index.exists():
            text = index.read_text(encoding="utf-8")
            text = text.replace(f"[[{source.name}/README", f"[[{source.name}/问题与进展")
            index.write_text(text, encoding="utf-8", newline="\n")


def _upsert_index(path: Path, header: str, block: str, apply: bool) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    updated = _replace_block(old, INDEX_BEGIN, INDEX_END, block) if old is not None else header.rstrip() + "\n\n" + block + "\n"
    if apply and updated != old:
        path.write_text(updated, encoding="utf-8", newline="\n")


def _index_current(path: Path, block: str) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(INDEX_BEGIN)}.*?{re.escape(INDEX_END)}", text, re.DOTALL)
    return bool(match and match.group(0) == block)


def _fact_index_block(entries: list[str]) -> str:
    return "\n".join([
        INDEX_BEGIN,
        "## 机械同步条目",
        "",
        "以下条目由结构脚本维护；投影是可编辑副本，不是 Fact 存储。",
        "",
        *sorted(entries),
        INDEX_END,
    ])


def _incremental_fact_index(fact_index: Path, fact: Fact, projection: Path) -> str | None:
    if not fact_index.exists():
        return None
    text = fact_index.read_text(encoding="utf-8")
    match = re.search(rf"{re.escape(INDEX_BEGIN)}.*?{re.escape(INDEX_END)}", text, re.DOTALL)
    if not match:
        return None
    lines = [line for line in match.group(0).splitlines() if line.startswith("- [[")]
    lines = [line for line in lines if f" — {fact.fact_id} " not in line]
    lines.append(f"- [[{projection.stem}]] — {fact.fact_id} v{fact.version}，{fact.status} / {fact.evidence_level}")
    return _fact_index_block(lines)


def sync_workspace(
    workspace: Path,
    repo_root: Path,
    *,
    apply: bool,
    sync_time: str,
    fact_id: str | None = None,
    version: int | None = None,
) -> dict:
    workspace = workspace.resolve()
    repo_root = repo_root.resolve()
    if version is not None and fact_id is None:
        raise ValueError("version requires fact_id")
    facts = discover_facts(repo_root, fact_id=fact_id, version=version)
    if fact_id and not facts:
        requested = f"{fact_id} v{version}" if version is not None else fact_id
        raise RuntimeError(f"Fact not found: {requested}")
    research = workspace / "Orpheus研究"
    fact_dir = research / "Fact参考"
    papers = workspace / "papers"
    actions: list[str] = []
    issues: list[str] = []
    incremental = fact_id is not None
    if apply:
        research.mkdir(parents=True, exist_ok=True)
        fact_dir.mkdir(parents=True, exist_ok=True)
        papers.mkdir(parents=True, exist_ok=True)
    elif not incremental and not papers.exists():
        issues.append("MISSING_DIRECTORY: papers")
    if not incremental:
        issues.extend(_paper_metadata_issues(papers, workspace, apply=apply, actions=actions))
        for problem in _problem_dirs(workspace):
            _migrate_problem(workspace, research, problem, apply, actions, issues)
    if not research.exists():
        issues.append("MISSING_DIRECTORY: Orpheus研究")
    if research.exists() and not fact_dir.exists():
        issues.append("MISSING_DIRECTORY: Orpheus研究/Fact参考")
    problems = sorted(
        path for path in research.iterdir()
        if path.is_dir() and path.name != "Fact参考" and (path / "问题与进展.md").exists()
    ) if research.exists() else []
    index_lines = [INDEX_BEGIN, "## 机械同步条目", "", "以下条目由结构脚本维护；研究内容仍由 Codex 编写。", ""]
    index_lines.extend(f"- [[Orpheus研究/{problem.name}/问题与进展|{problem.name}]]" for problem in problems)
    index_lines.append(INDEX_END)
    if research.exists() and not incremental:
        research_index = research / "研究索引.md"
        expected_index = "\n".join(index_lines)
        if not apply and not _index_current(research_index, expected_index):
            issues.append("STALE_INDEX: Orpheus研究/研究索引.md")
        _upsert_index(research_index, "# Orpheus 研究索引\n\n本索引连接当前项目中的研究问题与 Fact 参考。", expected_index, apply)
        if not (research / "研究索引.md").exists():
            issues.append("MISSING_FILE: Orpheus研究/研究索引.md")
    if fact_dir.exists():
        projection_paths: list[Path] = []
        for fact in facts:
            path, state, canonical_stale = _sync_projection(fact, fact_dir, sync_time, apply)
            projection_paths.append(path)
            if apply:
                display_state = state
            else:
                display_state = "would update" if canonical_stale else "current"
            actions.append(f"{display_state} Fact projection {path.relative_to(workspace)}")
            if not apply and canonical_stale:
                issues.append(f"STALE_FACT_PROJECTION: {path.relative_to(workspace)}")
                if not path.exists() or _canonical_body(fact) not in path.read_text(encoding="utf-8"):
                    issues.append(f"STALE_FACT_PROOF: {path.relative_to(workspace)}")
            if not path.exists():
                issues.append(f"MISSING_FACT_PROJECTION: {path.relative_to(workspace)}")
        fact_index = fact_dir / "Fact索引.md"
        expected_fact_index = None
        if incremental:
            expected_fact_index = _incremental_fact_index(fact_index, facts[0], projection_paths[0])
        if expected_fact_index is None:
            all_facts = discover_facts(repo_root)
            all_paths = [_projection_path(fact, fact_dir) for fact in all_facts]
            expected_fact_index = _fact_index_block([
                f"- [[{path.stem}]] — {fact.fact_id} v{fact.version}，{fact.status} / {fact.evidence_level}"
                for fact, path in zip(all_facts, all_paths)
            ])
        if not apply and not _index_current(fact_index, expected_fact_index):
            issues.append("STALE_INDEX: Orpheus研究/Fact参考/Fact索引.md")
        _upsert_index(fact_index, "# Fact 索引\n\n本索引列出当前项目同步的有效 Fact 阅读投影。", expected_fact_index, apply)
        if not (fact_dir / "Fact索引.md").exists():
            issues.append("MISSING_FILE: Orpheus研究/Fact参考/Fact索引.md")
    result = {"status": "PASS" if not issues else "CONFLICT", "mode": "sync" if apply else "check", "scope": "incremental" if incremental else "full", "workspace": str(workspace), "repo": str(repo_root), "papers": str(papers), "total_facts": len(facts), "active_facts": sum(fact.status == "ACTIVE" for fact in facts), "fact_ids": [fact.fact_id for fact in facts], "actions": actions, "issues": issues, "sync_time": sync_time}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize/check/sync an Orpheus Markdown workspace")
    parser.add_argument("mode", nargs="?", choices=("check", "sync"), default="check")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sync-time", default=None)
    parser.add_argument("--fact-id", default=None, help="sync/check only one newly accepted Fact")
    parser.add_argument("--version", type=int, default=None, help="exact Fact version; requires --fact-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo.resolve() if args.repo else default_repo_root()
    result = sync_workspace(args.workspace, repo, apply=args.mode == "sync" and not args.dry_run, sync_time=args.sync_time or datetime.now(timezone.utc).isoformat(), fact_id=args.fact_id, version=args.version)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"{result['status']} {result['mode']}: {len(result['actions'])} actions, {len(result['issues'])} issues")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
