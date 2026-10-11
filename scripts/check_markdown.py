"""Limited Markdown/Obsidian checks; neither a renderer nor a math verifier."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def check(root: Path):
    excluded_roots = {".git", ".runtime", ".venv", "archive", "build"}
    files = sorted(
        path for path in root.rglob("*.md")
        if not (set(path.relative_to(root).parts) & excluded_roots)
    )
    issues = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError:
            issues.append({"file": str(path.relative_to(root)), "issue": "INVALID_UTF8"})
            continue
        # Syntax examples are deliberately excluded; source text is never rewritten.
        body = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
        body = re.sub(r"`[^`\n]*`", "", body)
        def issue(code):
            issues.append({"file": str(path.relative_to(root)), "issue": code})
        if re.search(r"\\[\[\]()]", body):
            issue("NON_DOLLAR_MATH_DELIMITER")
        if body.count("$$") % 2:
            issue("UNBALANCED_DISPLAY_MATH")
        for line in body.splitlines():
            if "$$" in line and line.lstrip("> ").strip() != "$$":
                issue("DISPLAY_DELIMITER_NOT_ON_OWN_LINE")
        for target in re.findall(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)", body):
            target = target.strip("<>")
            if urlsplit(target).scheme:
                continue
            name = unquote(target.split("#", 1)[0])
            if name and not (path.parent / name).exists():
                issue("MISSING_LINK_TARGET:" + target)
        for target in re.findall(r"\[\[([^\]]+)\]\]", body):
            target = target.split("|", 1)[0]
            name, _, anchor = target.partition("#")
            name = name.removesuffix(".md")
            matches = [p for p in files if p.stem == name or p.relative_to(root).with_suffix("").as_posix() == name] if name else [path]
            if len(matches) != 1:
                issue("MISSING_OR_AMBIGUOUS_WIKILINK:" + target)
                continue
            if anchor:
                destination = matches[0].read_text(encoding="utf-8")
                present = (re.search(r"\^" + re.escape(anchor[1:]) + r"\s*$", destination, re.M) if anchor.startswith("^")
                           else re.search(r"^#+\s+" + re.escape(anchor) + r"\s*$", destination, re.M))
                if not present:
                    issue("MISSING_WIKI_ANCHOR:" + target)
    return {"scope": str(root), "files_checked": len(files), "issues": issues,
            "status": "PASS" if files and not issues else "FAIL",
            "actual_obsidian_rendering": "NOT_TESTED",
            "limitations": "Checks a subset of links and math delimiters; no rendering, LaTeX semantics, or mathematical verification."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.root.resolve())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result["status"], result["files_checked"], "files;", len(result["issues"]), "issues")
    raise SystemExit(0 if result["status"] == "PASS" else 1)
