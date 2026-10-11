"""Register one already-selected Zotero attachment in an Obsidian workspace.

This script intentionally does not contact Zotero.  The official Zotero Skill
or its local helper supplies the item JSON, attachment key, and local file path;
this script only creates a project-level ``papers/`` registration sidecar and,
by default, a hardlink reading entry.  Zotero remains the fulltext master.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping


class RegistrationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _data(item: Mapping[str, Any]) -> Mapping[str, Any]:
    nested = item.get("data")
    return nested if isinstance(nested, Mapping) else item


def _creators(data: Mapping[str, Any]) -> list[str]:
    result = []
    for creator in data.get("creators", []) or []:
        if isinstance(creator, str):
            result.append(creator)
            continue
        name = creator.get("name") or " ".join(
            p for p in (creator.get("firstName"), creator.get("lastName")) if p
        )
        if name:
            result.append(str(name))
    return result


def _year(value: Any) -> str:
    match = re.search(r"(\d{4})", str(value or ""))
    return match.group(1) if match else ""


def _item_year(data: Mapping[str, Any]) -> str:
    return _year(data.get("date") or data.get("year"))


def _quote(value: Any) -> str:
    return "'" + str(value if value is not None else "").replace("'", "''") + "'"


def _frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", text)
    if not match:
        return None
    value = re.sub(r"\s+#.*$", "", match.group(1)).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        if value[0] == "'":
            return value[1:-1].replace("''", "'")
        return value[1:-1].replace('""', '"')
    return value


def _safe(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(value or ""))).strip(" .")


def _stem(data: Mapping[str, Any], item_key: str) -> str:
    creators = data.get("creators", []) or []
    author = ""
    if creators:
        first = creators[0]
        if isinstance(first, str):
            author = first
        else:
            author = first.get("lastName") or first.get("name") or first.get("firstName") or ""
    parts = [p for p in (_safe(author), _item_year(data), _safe(data.get("title"))) if p]
    return ("-".join(parts) or f"Zotero-{item_key}")[:150].rstrip(" .")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _citation(data: Mapping[str, Any]) -> str:
    return f"{', '.join(_creators(data)) or 'Unknown author'} ({_item_year(data) or 'n.d.'}). {data.get('title') or 'Untitled'}."


def _sidecar(
    data: Mapping[str, Any], *, item_key: str, attachment_key: str, source: Path,
    paper_file: str, storage_mode: str, digest: str, related_questions: list[str],
) -> str:
    title = data.get("title") or "未命名文献"
    authors = _creators(data)
    doi = data.get("DOI") or data.get("doi") or ""
    url = data.get("url") or (f"https://doi.org/{doi}" if doi else "")
    lines = [
        "---", f"title: {_quote(title)}", "authors:",
        *[f"  - {_quote(author)}" for author in authors],
        f"year: {_quote(_item_year(data))}", "version: ''",
        f"source_url: {_quote(url)}", f"doi: {_quote(doi)}", "arxiv: ''",
        f"downloaded_or_checked: {_quote(date.today().isoformat())}",
        f"sha256: {_quote(digest)}", "license_or_access: 'Zotero 本地附件；许可沿用原始来源。'",
        "source_mode: 'zotero_registration'", "zotero_import_status: 'registered'",
        "related_questions:", *[f"  - {_quote(q)}" for q in related_questions],
        f"zotero_item_key: {_quote(item_key)}", f"zotero_attachment_key: {_quote(attachment_key)}",
        f"storage_mode: {_quote(storage_mode)}", f"attachment_path: {_quote(source)}",
        f"paper_file: {_quote(paper_file)}", "---", "", "# 文献阅读入口", "",
        "## 书目信息", "", f"- 标题：{title}", f"- 作者：{', '.join(authors) or '未知作者'}",
        f"- 年份：{_item_year(data) or '未知'}", f"- 完整 citation：{_citation(data)}",
        f"- 来源 URL：{url or '未记录'}", f"- DOI：{doi or '未记录'}", "",
        "## 文件与访问", "", f"- 原文文件：{paper_file or '未复制；使用 Zotero 本地附件路径'}",
        f"- Zotero 附件路径：`{source}`", f"- SHA-256：`{digest}`", f"- 存储方式：`{storage_mode}`",
        "- Zotero 是全文、附件和批注主库；本文件是项目级登记与阅读入口。", "- Zotero 元数据与附件只作为研究材料入口，不自动成为 Fact。", "", "## 关联问题", "",
        *([f"- {q}" for q in related_questions] or ["- 待研究者补充"]), "",
        "## 精确定位提示", "", "- 待核查 theorem / proposition / section / page / version；正式候选仍须完整 citation 与精确 locator。", "",
    ]
    return "\n".join(lines)


def register_paper(
    metadata: Mapping[str, Any], attachment_path: str | Path, workspace: str | Path,
    *, attachment_key: str | None = None, related_questions: list[str] | None = None,
    storage_mode: str = "hardlink",
) -> dict[str, Any]:
    if storage_mode not in {"hardlink", "path"}:
        raise RegistrationError("INVALID_STORAGE_MODE", "storage_mode must be 'hardlink' or 'path'")
    item = _data(metadata)
    item_key = str(metadata.get("key") or metadata.get("item_key") or item.get("key") or "")
    attachment_key = attachment_key or str(metadata.get("attachment_key") or item.get("attachment_key") or "")
    if not item_key or not attachment_key:
        raise RegistrationError("KEY_REQUIRED", "item metadata must include item key and attachment key")
    workspace_path = Path(workspace).expanduser().resolve()
    source = Path(attachment_path).expanduser().resolve()
    if not workspace_path.is_dir():
        raise RegistrationError("WORKSPACE_NOT_FOUND", f"Workspace directory does not exist: {workspace_path}")
    if not source.is_file():
        raise RegistrationError("ATTACHMENT_MISSING", f"Attachment file does not exist: {source}")
    papers = workspace_path / "papers"
    papers.mkdir(parents=True, exist_ok=True)
    digest = _sha256(source)
    for sidecar in sorted(papers.glob("*.md")):
        text = sidecar.read_text(encoding="utf-8", errors="replace")
        if _frontmatter_value(text, "zotero_item_key") == item_key or _frontmatter_value(text, "zotero_attachment_key") == attachment_key:
            return {"status": "ALREADY_REGISTERED", "item_key": item_key, "attachment_key": attachment_key, "sha256": digest, "sidecar": str(sidecar), "paper_file": _frontmatter_value(text, "paper_file")}
    stem = _stem(item, item_key)
    suffix = source.suffix or ".pdf"
    target, sidecar = papers / f"{stem}{suffix}", papers / f"{stem}.md"
    if target.exists() or sidecar.exists():
        stem = f"{stem}-{item_key}"
        target, sidecar = papers / f"{stem}{suffix}", papers / f"{stem}.md"
    made_target = False
    if storage_mode == "hardlink":
        try:
            os.link(source, target)
            made_target = True
        except OSError as exc:
            raise RegistrationError("HARDLINK_FAILED", f"Could not create hardlink; retry with storage_mode='path': {exc}") from exc
    actual_mode = "hardlink" if made_target else "path_reference"
    try:
        fd = os.open(sidecar, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(_sidecar(item, item_key=item_key, attachment_key=attachment_key, source=source, paper_file=target.name if made_target else "", storage_mode=actual_mode, digest=digest, related_questions=related_questions or []))
    except Exception:
        if made_target and target.exists():
            target.unlink()
        raise
    return {"status": "REGISTERED", "item_key": item_key, "attachment_key": attachment_key, "sha256": digest, "storage_mode": actual_mode, "paper_file": str(target) if made_target else None, "sidecar": str(sidecar), "source_path": str(source)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register an already-selected Zotero attachment in a project")
    parser.add_argument("--metadata-json", type=Path, required=True, help="JSON exported by Zotero Skill/helper")
    parser.add_argument("--attachment-path", type=Path, required=True)
    parser.add_argument("--attachment-key", required=False)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--related-question", action="append", default=[])
    parser.add_argument("--storage-mode", choices=("hardlink", "path"), default="hardlink")
    args = parser.parse_args(argv)
    try:
        result = register_paper(json.loads(args.metadata_json.read_text(encoding="utf-8-sig")), args.attachment_path, args.workspace, attachment_key=args.attachment_key, related_questions=args.related_question, storage_mode=args.storage_mode)
    except (OSError, json.JSONDecodeError, RegistrationError) as exc:
        payload = {"status": "ERROR", "message": str(exc), "error_code": getattr(exc, "code", "INPUT_ERROR")}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
