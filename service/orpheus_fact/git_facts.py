"""Git-backed canonical Fact history.

The Git tree is authoritative. Markdown is the user-readable Fact, adjacent
JSON is machine metadata, and SQLite (when requested) is only a rebuildable
search index. Every mutation first checks the tree and then creates an
explicit commit; no MCP method can edit an accepted Fact in place.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import uuid

from .models import Artifact, Candidate, FactRef, Finding, Review, Source


class GitFactError(ValueError):
    pass


class IntegrityError(GitFactError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _flat(value: str) -> str:
    return " ".join(value.splitlines())


def _submitted_result(**values) -> dict:
    return {
        **values,
        "required_next_action": "START_FRESH_COLD_REVIEW",
        "review_status": "NOT_STARTED",
        "research_checks_do_not_replace_review": True,
    }


def _nested_markdown(value: str, level: int) -> str:
    """Keep a Markdown fragment below its owning section in Obsidian outlines."""
    lines = value.strip().splitlines()
    fenced = False
    headings: list[int] = []
    for line in lines:
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        elif not fenced and (match := re.match(r"^(#{1,6})\s+", line)):
            headings.append(len(match.group(1)))
    shift = max(0, level - min(headings)) if headings else 0
    if not shift:
        return "\n".join(lines)
    fenced = False
    result = []
    for line in lines:
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
        if not fenced and (match := re.match(r"^(#{1,6})(\s+.*)$", line)):
            line = "#" * min(6, len(match.group(1)) + shift) + match.group(2)
        result.append(line)
    return "\n".join(result)


class GitFactStore:
    """Canonical Fact history rooted at a Git working tree."""

    FACT_ID = re.compile(r"^fact-[0-9a-f]{32}$")
    VERSION = re.compile(r"^v([1-9][0-9]*)$")

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.facts = self.root / "facts"
        self.candidates = self.root / "candidates"
        self.reviews = self.root / "reviews"
        self.requests = self.root / "requests"
        self.issues = self.root / "issues"
        self.incidents = self.root / "incidents"
        self.manifest = self.facts / "MANIFEST.json"
        git_root = Path(self._git(["rev-parse", "--show-toplevel"])).resolve()
        if git_root != self.root:
            raise GitFactError("GIT_ROOT_MISMATCH")

    def _git(self, args: list[str], *, check=True) -> str:
        try:
            result = subprocess.run(["git", *args], cwd=self.root, check=check,
                                    capture_output=True, text=True, encoding="utf-8")
        except (OSError, subprocess.CalledProcessError) as exc:
            raise GitFactError("GIT_COMMAND_FAILED") from exc
        return result.stdout.strip()

    def _push_main(self, remote: str = "origin") -> dict:
        """Best-effort fast-forward backup after acceptance; never prompt or force-push."""
        if not self._git(["remote", "get-url", remote], check=False):
            return {"status": "NOT_CONFIGURED", "remote": remote}
        environment = os.environ.copy()
        environment.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
        result = subprocess.run(
            ["git", "push", remote, "HEAD:main"], cwd=self.root,
            capture_output=True, text=True, encoding="utf-8", env=environment,
        )
        if result.returncode:
            return {"status": "REMOTE_PENDING", "remote": remote, "reason": "PUSH_FAILED"}
        remote_head = self._git(["ls-remote", remote, "refs/heads/main"], check=False).split()
        local_head = self._git(["rev-parse", "HEAD"])
        if not remote_head or remote_head[0] != local_head:
            return {"status": "REMOTE_PENDING", "remote": remote, "reason": "HEAD_NOT_CONFIRMED"}
        return {"status": "SYNCED", "remote": remote, "commit": local_head}

    def _tracked_dirty(self) -> list[str]:
        output = self._git(["status", "--porcelain", "--", "facts", "candidates", "reviews", "issues", "requests"])
        return [line[3:] for line in output.splitlines() if len(line) >= 4]

    def _record_incident(self, code: str, details: dict) -> str:
        incident_id = "incident-" + uuid.uuid4().hex
        patch = self._git(["diff", "--binary", "--", "facts", "candidates", "reviews", "issues", "requests"], check=False)
        payload = {"incident_id": incident_id, "created": _now(), "code": code,
                   "details": {k: details[k] for k in sorted(details)},
                   "patch_sha256": _sha(patch), "patch_bytes": len(patch.encode("utf-8"))}
        _json(self.incidents / (incident_id + ".json"), payload)
        (self.incidents / (incident_id + ".patch")).write_text(
            patch or "# No tracked patch; see incident metadata for the affected paths.\n", encoding="utf-8", newline="\n")
        (self.incidents / (incident_id + ".md")).write_text(
            f"# Orpheus 完整性事件\n\n事件：`{incident_id}`  \n代码：`{code}`  \n记录时间：{payload['created']}\n\n"
            "已保存事件元数据和现场 patch。工作区在继续操作前需要显式审查和恢复；此文件不代表已恢复。\n",
            encoding="utf-8", newline="\n")
        self._commit_incident(incident_id)
        return incident_id

    def _commit_incident(self, incident_id: str) -> str:
        if not self._git(["config", "user.name"], check=False) or not self._git(["config", "user.email"], check=False):
            raise GitFactError("GIT_AUTHOR_NOT_CONFIGURED")
        paths = [f"incidents/{incident_id}{suffix}" for suffix in (".json", ".patch", ".md")]
        self._git(["add", "--", *paths])
        self._git(["commit", "-m", f"incident: {incident_id}"])
        return self._git(["rev-parse", "HEAD"])

    def _require_clean(self) -> None:
        dirty = self._tracked_dirty()
        if dirty:
            incident = self._record_incident("WORKTREE_DIRECT_MODIFICATION", {"paths": dirty})
            raise IntegrityError("INTEGRITY_INCIDENT_RECORDED:" + incident)
        self.integrity_check()

    def _fact_paths(self):
        return sorted(self.facts.glob("fact-*/v*.json")) if self.facts.exists() else []

    def _load_metadata(self, path: Path) -> dict:
        value = _read_json(path)
        if not isinstance(value, dict):
            raise IntegrityError("INVALID_FACT_METADATA")
        return value

    def _candidate(self, digest: str) -> Candidate:
        try:
            raw = _read_json(self.candidates / (digest + ".json"))
            legacy_digest = raw.get("legacy_digest") if isinstance(raw, dict) else None
            body = raw.get("candidate") if legacy_digest else raw
            # JSON arrays are the wire representation of the immutable tuple
            # fields in Candidate; normalize them before strict validation.
            body = dict(body)
            body["sources"] = tuple(Source.model_validate(item) for item in body.get("sources", ()))
            body["dependencies"] = tuple(FactRef.model_validate(item) for item in body.get("dependencies", ()))
            body["artifacts"] = tuple(Artifact.model_validate(item) for item in body.get("artifacts", ()))
            value = Candidate.model_validate(body)
        except Exception as exc:
            raise IntegrityError("CANDIDATE_SNAPSHOT_INVALID") from exc
        if value.digest() != digest and legacy_digest != digest:
            raise IntegrityError("CANDIDATE_HASH_MISMATCH")
        if legacy_digest:
            if raw.get("body_sha256") != _sha(value.canonical()):
                raise IntegrityError("LEGACY_CANDIDATE_HASH_MISMATCH")
        return value

    def _review(self, digest: str) -> Review:
        try:
            raw = _read_json(self.reviews / (digest + ".json"))
            raw = dict(raw)
            raw["errors"] = tuple(Finding.model_validate(item) for item in raw.get("errors", ()))
            raw["gaps"] = tuple(Finding.model_validate(item) for item in raw.get("gaps", ()))
            raw["references_checked"] = tuple(raw.get("references_checked", ()))
            return Review.model_validate(raw)
        except Exception as exc:
            raise IntegrityError("REVIEW_SNAPSHOT_INVALID") from exc

    def _write_manifest(self) -> None:
        entries = {}
        for directory in (self.facts, self.candidates, self.reviews, self.requests):
            if directory.exists():
                for path in sorted(path for path in directory.rglob("*") if path.is_file()):
                    if path != self.manifest and path.is_file():
                        entries[path.relative_to(self.root).as_posix()] = _sha(path.read_bytes())
        _json(self.manifest, {"format": 1, "generated": _now(), "files": entries})

    def _commit(self, message: str) -> str:
        # Author identity is required only when this path is about to mutate
        # the Git tree. Read-only integrity and query operations never call it.
        self._require_author()
        for directory in (self.facts, self.candidates, self.reviews, self.requests, self.issues, self.incidents):
            directory.mkdir(parents=True, exist_ok=True)
        self._write_manifest()
        self._git(["add", "facts", "candidates", "reviews", "requests", "issues", "incidents"])
        staged = self._git(["diff", "--cached", "--name-only"])
        if not staged:
            raise GitFactError("NOTHING_TO_COMMIT")
        self._git(["commit", "-m", message])
        return self._git(["rev-parse", "HEAD"])

    def _require_author(self) -> None:
        if not self._git(["config", "user.name"], check=False) or not self._git(["config", "user.email"], check=False):
            raise GitFactError("GIT_AUTHOR_NOT_CONFIGURED")

    def integrity_check(self, *, record_incident: bool = True) -> dict:
        """Verify hashes, versions, dependencies and the committed manifest."""
        errors = []
        if self.manifest.exists():
            try:
                manifest = _read_json(self.manifest).get("files", {})
                actual = set()
                for directory in (self.facts, self.candidates, self.reviews, self.requests):
                    if directory.exists():
                        actual.update(path.relative_to(self.root).as_posix() for path in directory.rglob("*")
                                     if path.is_file() and path != self.manifest)
                for name, expected in manifest.items():
                    path = self.root / name
                    if not path.exists() or _sha(path.read_bytes()) != expected:
                        errors.append("MANIFEST_HASH_MISMATCH:" + name)
                errors.extend("MANIFEST_ENTRY_MISSING:" + name for name in sorted(actual - set(manifest)))
            except (OSError, ValueError, AttributeError):
                errors.append("MANIFEST_INVALID")
        issue_paths = self.issues.glob("*.md") if self.issues.exists() else ()
        for path in issue_paths:
            if not path.read_text(encoding="utf-8").strip():
                errors.append("ISSUE_EVIDENCE_EMPTY:" + path.name)
        incident_paths = self.incidents.glob("*.json") if self.incidents.exists() else ()
        for path in incident_paths:
            try:
                incident = _read_json(path)
                patch_path = path.with_suffix(".patch")
                if incident.get("incident_id") != path.stem or not patch_path.exists():
                    errors.append("INCIDENT_EVIDENCE_INVALID:" + path.name)
            except (OSError, ValueError, AttributeError):
                errors.append("INCIDENT_EVIDENCE_INVALID:" + path.name)
        if self.requests.exists():
            for path in self.requests.glob("*.json"):
                try:
                    mapping = _read_json(path)
                    request_hash = path.stem
                    if (not re.fullmatch(r"[0-9a-f]{64}", request_hash)
                            or mapping.get("format") != 1
                            or mapping.get("request_key_sha256") != request_hash
                            or not re.fullmatch(r"[0-9a-f]{64}", mapping.get("candidate_digest", ""))):
                        errors.append("REQUEST_MAPPING_INVALID:" + path.name)
                    else:
                        self._candidate(mapping["candidate_digest"])
                except Exception:
                    errors.append("REQUEST_MAPPING_INVALID:" + path.name)
        for path in self._fact_paths():
            try:
                metadata = self._load_metadata(path)
                fact_id = path.parent.name
                match = self.VERSION.match(path.stem)
                version = int(match.group(1)) if match else 0
                if not self.FACT_ID.fullmatch(fact_id) or not version:
                    errors.append("FACT_PATH_INVALID:" + path.name)
                    continue
                if metadata.get("fact_id") != fact_id or metadata.get("version") != version:
                    errors.append("FACT_VERSION_MISMATCH:" + path.as_posix())
                candidate_digest = metadata.get("candidate_digest")
                if not isinstance(candidate_digest, str):
                    errors.append("FACT_CANDIDATE_MISSING:" + path.as_posix())
                else:
                    self._candidate(candidate_digest)
                review_digest = metadata.get("review_digest")
                review_path = self.reviews / (candidate_digest + ".json")
                if not isinstance(review_digest, str) or not review_path.exists():
                    errors.append("FACT_REVIEW_MISSING:" + path.as_posix())
                elif _sha(review_path.read_bytes()) != review_digest:
                    errors.append("REVIEW_HASH_MISMATCH:" + path.as_posix())
                artifact_items = metadata.get("artifacts", [])
                if not isinstance(artifact_items, list):
                    errors.append("FACT_ARTIFACT_METADATA_INVALID:" + path.as_posix())
                else:
                    artifact_dir = path.parent / f"v{version}-artifacts"
                    expected_names = set()
                    for item in artifact_items:
                        if (not isinstance(item, dict)
                                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", item.get("name", ""))
                                or item.get("kind") not in {"script", "report", "data", "certificate"}
                                or not re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", ""))):
                            errors.append("FACT_ARTIFACT_METADATA_INVALID:" + path.as_posix())
                            continue
                        expected_names.add(item["name"])
                        artifact_path = artifact_dir / item["name"]
                        if not artifact_path.is_file() or _sha(artifact_path.read_bytes()) != item["sha256"]:
                            errors.append("FACT_ARTIFACT_HASH_MISMATCH:" + artifact_path.as_posix())
                    actual_names = ({item.name for item in artifact_dir.iterdir() if item.is_file()}
                                    if artifact_dir.exists() else set())
                    if actual_names != expected_names:
                        errors.append("FACT_ARTIFACT_SET_MISMATCH:" + path.as_posix())
                for dependency in metadata.get("dependencies", []):
                    self.get(FactRef.model_validate(dependency))
            except Exception:
                errors.append("FACT_METADATA_INVALID:" + path.as_posix())
        result = {"status": "PASS" if not errors else "FAILED", "errors": errors,
                  "facts": len(self._fact_paths())}
        if errors:
            if not record_incident:
                result["incident_recorded"] = False
                return result
            incident = self._record_incident("CANONICAL_INTEGRITY_FAILURE", {"errors": errors})
            result["incident_id"] = incident
            raise IntegrityError("INTEGRITY_INCIDENT_RECORDED:" + incident)
        return result

    @staticmethod
    def _request_hash(request_key: str) -> str:
        return _sha(request_key)

    def submit(self, request_key: str, candidate: Candidate) -> dict:
        if not request_key.strip() or len(request_key) > 200:
            raise GitFactError("INVALID_REQUEST_KEY")
        self._require_clean()
        digest = candidate.digest()
        request_hash = self._request_hash(request_key)
        request_path = self.requests / (request_hash + ".json")
        if request_path.exists():
            try:
                mapping = _read_json(request_path)
            except Exception as exc:
                raise IntegrityError("REQUEST_MAPPING_INVALID") from exc
            if mapping.get("candidate_digest") != digest:
                raise GitFactError("REQUEST_CONFLICT")
            if mapping.get("request_key_sha256") != request_hash:
                raise IntegrityError("REQUEST_MAPPING_INVALID")
            commit = mapping.get("commit") or self._git(
                ["log", "-1", "--format=%H", "--", str(request_path.relative_to(self.root))])
            return _submitted_result(status="SUBMITTED", candidate_digest=digest,
                                     request_key_sha256=request_hash, commit=commit, idempotent=True)
        self._require_computation_artifacts(candidate)
        self._require_author()
        target = self.candidates / (digest + ".json")
        for dependency in candidate.dependencies:
            if self.get(dependency)["status"] != "ACTIVE":
                raise GitFactError("INVALID_DEPENDENCY")
        if not target.exists():
            _json(target, candidate.model_dump(mode="json"))
        _json(request_path, {"format": 1, "request_key_sha256": request_hash,
                             "candidate_digest": digest})
        commit = self._commit(f"candidate: {digest} request:{request_key}")
        return _submitted_result(status="SUBMITTED", candidate_digest=digest,
                                 request_key_sha256=request_hash, commit=commit, idempotent=False)

    def record_review(self, candidate_digest: str, review: Review) -> dict:
        self._require_clean()
        if review.candidate_digest != candidate_digest or not (self.candidates / (candidate_digest + ".json")).exists():
            raise GitFactError("REVIEW_BINDING_MISMATCH")
        review_path = self.reviews / (candidate_digest + ".json")
        if review_path.exists():
            existing = self._review(candidate_digest)
            if existing != review:
                raise GitFactError("REVIEW_IMMUTABLE")
            commit = self._git(["log", "-1", "--format=%H", "--", str(review_path.relative_to(self.root))])
            return {"status": "REVIEW_RECORDED", "candidate_digest": candidate_digest,
                    "verdict": existing.verdict, "commit": commit, "idempotent": True}
        self._require_author()
        candidate = self._candidate(candidate_digest)
        _json(self.reviews / (candidate_digest + ".json"), review.model_dump(mode="json"))
        report = _nested_markdown(review.report_markdown, 2)
        repair = ""
        if review.repair_hints.strip() and not re.search(r"^#{2,6}\s+.*修补建议", report, re.MULTILINE):
            repair = f"\n\n## 修补建议\n\n{review.repair_hints.strip()}"
        (self.reviews / (candidate_digest + ".md")).write_text(
            f"# 审查报告：{_flat(candidate.title)}\n\n"
            f"> [!info] 审查元数据\n> - 候选摘要：`{candidate_digest}`\n"
            f"> - 结论：`{review.verdict}`\n> - 规则摘要：`{review.rule_digest}`\n\n"
            f"{report}{repair}\n", encoding="utf-8", newline="\n")
        commit = self._commit(f"review: {candidate_digest} verdict:{review.verdict}")
        return {"status": "REVIEW_RECORDED", "candidate_digest": candidate_digest,
                "verdict": review.verdict, "commit": commit, "idempotent": False}

    def accept(self, candidate_digest: str) -> dict:
        self._require_clean()
        candidate = self._candidate(candidate_digest)
        self._require_computation_artifacts(candidate)
        review = self._review(candidate_digest)
        if review.candidate_digest != candidate_digest or review.verdict != "PASS":
            raise GitFactError("FACT_REQUIRES_BOUND_PASS")
        existing = []
        for path in self._fact_paths():
            metadata = self._load_metadata(path)
            if metadata.get("candidate_digest") == candidate_digest:
                existing.append((path, metadata))
        if len(existing) > 1:
            raise IntegrityError("MULTIPLE_FACTS_FOR_CANDIDATE")
        if existing:
            path, metadata = existing[0]
            commit = self._git(["log", "-1", "--format=%H", "--", str(path.relative_to(self.root))])
            return {"status": "ACCEPTED", "fact_id": metadata["fact_id"],
                    "version": metadata["version"], "commit": commit, "idempotent": True,
                    "remote_sync": self._push_main()}
        self._require_author()
        for dependency in candidate.dependencies:
            if self.get(dependency)["status"] != "ACTIVE":
                raise GitFactError("INVALID_DEPENDENCY")
        if candidate.revises:
            latest = self._latest(candidate.revises.fact_id)
            if latest != candidate.revises.version:
                raise GitFactError("STALE_REVISION")
            fact_id, version = candidate.revises.fact_id, latest + 1
        else:
            fact_id, version = "fact-" + uuid.uuid4().hex, 1
        metadata = {
            "fact_id": fact_id, "version": version, "status": "ACTIVE",
            "candidate_digest": candidate_digest,
            "review_digest": _sha((self.reviews / (candidate_digest + ".json")).read_bytes()),
            "dependencies": [ref.model_dump(mode="json") for ref in candidate.dependencies],
            "revises": candidate.revises.model_dump(mode="json") if candidate.revises else None,
            "evidence_level": "AI_REVIEWED", "admitted": _now(),
            "artifacts": [
                {"name": artifact.name, "kind": artifact.kind,
                 "sha256": _sha(artifact.content.encode("utf-8"))}
                for artifact in candidate.artifacts
            ],
        }
        directory = self.facts / fact_id
        directory.mkdir(parents=True, exist_ok=True)
        if candidate.artifacts:
            artifact_directory = directory / f"v{version}-artifacts"
            artifact_directory.mkdir()
            for artifact in candidate.artifacts:
                (artifact_directory / artifact.name).write_text(
                    artifact.content, encoding="utf-8", newline="")
        (directory / f"v{version}.md").write_text(self._markdown(candidate, metadata), encoding="utf-8", newline="\n")
        _json(directory / f"v{version}.json", metadata)
        commit = self._commit(f"fact: {fact_id} v{version} candidate:{candidate_digest} review:{metadata['review_digest']}")
        return {"status": "ACCEPTED", "fact_id": fact_id, "version": version,
                "commit": commit, "idempotent": False,
                "remote_sync": self._push_main()}

    @staticmethod
    def _require_computation_artifacts(candidate: Candidate) -> None:
        kinds = {artifact.kind for artifact in candidate.artifacts}
        if "script" not in kinds:
            return
        missing = {"report"} - kinds
        if not ({"data", "certificate"} & kinds):
            missing.add("data_or_certificate")
        if missing:
            raise GitFactError("COMPUTATION_ARTIFACTS_INCOMPLETE:" + ",".join(sorted(missing)))

    def _latest(self, fact_id: str) -> int:
        versions = [int(match.group(1)) for path in self._fact_paths()
                    if path.parent.name == fact_id and (match := self.VERSION.match(path.stem))]
        if not versions:
            raise GitFactError("FACT_NOT_FOUND")
        return max(versions)

    def get(self, ref: FactRef) -> dict:
        if not self.FACT_ID.fullmatch(ref.fact_id):
            raise GitFactError("FACT_NOT_FOUND")
        metadata_path = self.facts / ref.fact_id / f"v{ref.version}.json"
        markdown_path = self.facts / ref.fact_id / f"v{ref.version}.md"
        if not metadata_path.exists() or not markdown_path.exists():
            raise GitFactError("FACT_NOT_FOUND")
        return {**self._load_metadata(metadata_path), "markdown": markdown_path.read_text(encoding="utf-8")}

    def search(self, query: str, limit: int = 20) -> list[dict]:
        if not isinstance(query, str) or not 1 <= limit <= 100:
            raise GitFactError("INVALID_QUERY")
        result = []
        for path in self._fact_paths():
            metadata = self._load_metadata(path)
            body = path.with_suffix(".md").read_text(encoding="utf-8")
            if metadata.get("status") == "ACTIVE" and query.casefold() in body.casefold():
                result.append({"fact_id": metadata["fact_id"], "version": metadata["version"],
                               "title": body.splitlines()[0].removeprefix("# "),
                               "status": metadata["status"], "evidence_level": metadata["evidence_level"]})
        return result[:limit]

    def report_issue(self, ref: FactRef, reason: str) -> dict:
        if not reason.strip():
            raise GitFactError("INVALID_ISSUE")
        self._require_clean()
        self._require_author()
        self.get(ref)
        issue_id = "issue-" + uuid.uuid4().hex
        path = self.issues / (issue_id + ".md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Fact 问题报告\n\nFact：`{ref.fact_id}` 版本 {ref.version}\n\n{reason}\n", encoding="utf-8", newline="\n")
        commit = self._commit(f"issue: {ref.fact_id} v{ref.version} {issue_id}")
        return {"issue_id": issue_id, "status": "REPORTED", "commit": commit, "fact_unchanged": True}

    def revoke(self, ref: FactRef, reason: str) -> dict:
        """Append status events and invalidate every dependent version transitively."""
        if not reason.strip():
            raise GitFactError("REASON_REQUIRED")
        self._require_clean()
        self._require_author()
        self.get(ref)
        affected = {(ref.fact_id, ref.version)}
        changed = True
        metadata_paths = self._fact_paths()
        while changed:
            changed = False
            for path in metadata_paths:
                metadata = self._load_metadata(path)
                key = (metadata.get("fact_id"), metadata.get("version"))
                dependencies = {(item.get("fact_id"), item.get("version"))
                                for item in metadata.get("dependencies", [])}
                if key not in affected and dependencies & affected:
                    affected.add(key)
                    changed = True
        created = _now()
        for path in metadata_paths:
            metadata = self._load_metadata(path)
            key = (metadata.get("fact_id"), metadata.get("version"))
            if key not in affected:
                continue
            status = "REVOKED" if key == (ref.fact_id, ref.version) else "INVALIDATED_BY_DEP"
            if metadata.get("status") == status:
                continue
            metadata["status"] = status
            metadata.setdefault("status_events", []).append({"status": status, "reason": reason, "created": created})
            _json(path, metadata)
            markdown = path.with_suffix(".md")
            body = markdown.read_text(encoding="utf-8")
            body = re.sub(r"^状态：.*$", "状态：" + status, body, count=1, flags=re.MULTILINE)
            markdown.write_text(body, encoding="utf-8", newline="\n")
        commit = self._commit(f"revoke: {ref.fact_id} v{ref.version} affected:{len(affected)}")
        return {"status": "REVOKED", "affected": len(affected), "commit": commit}

    def rebuild_index(self, target: str | Path) -> Path:
        """Rebuild an optional SQLite search index solely from Git Fact files."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as db:
            db.execute("DROP TABLE IF EXISTS facts")
            db.execute("CREATE TABLE facts(fact_id TEXT, version INTEGER, title TEXT, status TEXT, body TEXT, PRIMARY KEY(fact_id,version))")
            for path in self._fact_paths():
                metadata = self._load_metadata(path)
                body = path.with_suffix(".md").read_text(encoding="utf-8")
                db.execute("INSERT INTO facts VALUES(?,?,?,?,?)", (metadata["fact_id"], metadata["version"], body.splitlines()[0], metadata["status"], body))
        return target

    def remote_protection_status(self, remote: str = "origin") -> dict:
        """Report local knowledge only; never creates, contacts, or pushes a remote.

        Hosting-side branch protection cannot be proven from a local checkout.
        The report therefore records the local branch/upstream/head and the
        user actions still required without exposing a configured URL.
        """
        configured = bool(self._git(["remote", "get-url", remote], check=False))
        branch = self._git(["branch", "--show-current"], check=False) or None
        upstream = self._git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], check=False) or None
        head = self._git(["rev-parse", "HEAD"], check=False) or None
        missing = (["user-provided remote URL", "protected main branch", "no-force-push rule",
                    "hosting review and backup policy"] if not configured else
                   ["hosting-side protected main branch verification", "no-force-push rule",
                    "hosting review and backup policy"])
        return {"remote": remote, "configured": configured,
                "protection_verified": False,
                "status": "REMOTE_NOT_CONFIGURED" if not configured else "PROTECTION_UNVERIFIED",
                "verification_scope": "LOCAL_ONLY",
                "local_branch": branch, "upstream": upstream, "local_head": head,
                "missing_user_actions": missing}

    def _restore_inputs(self, incident_id: str, commit: str, paths: list[str]) -> tuple[str, list[str]]:
        if not (self.incidents / (incident_id + ".json")).exists():
            raise GitFactError("INCIDENT_NOT_FOUND")
        if not paths or any(Path(path).is_absolute() or ".." in Path(path).parts for path in paths):
            raise GitFactError("INVALID_RESTORE_PATH")
        return self._git(["rev-parse", "--verify", commit + "^{commit}"]), paths

    def preview_restore(self, incident_id: str, commit: str, paths: list[str]) -> dict:
        """Describe a restore without changing the worktree."""
        resolved, paths = self._restore_inputs(incident_id, commit, paths)
        changes = self._git(["diff", "--name-status", "HEAD", resolved, "--", *paths], check=False)
        return {"status": "DRY_RUN", "operation": "RESTORE", "incident_id": incident_id,
                "source_commit": resolved, "paths": paths,
                "changed_paths": [line for line in changes.splitlines() if line]}

    def restore_from_commit(self, incident_id: str, commit: str, paths: list[str]) -> dict:
        """Restore selected paths only after an explicit incident decision."""
        resolved, paths = self._restore_inputs(incident_id, commit, paths)
        self._git(["restore", "--source", resolved, "--", *paths])
        self.integrity_check()
        return {"status": "RESTORED_EXPLICITLY", "incident_id": incident_id,
                "commit": resolved}

    def revert_commit(self, commit: str, *, apply: bool = False) -> dict:
        """Preview or explicitly apply a whole-commit Git revert."""
        resolved = self._git(["rev-parse", "--verify", commit + "^{commit}"])
        if self._git(["status", "--porcelain"], check=False):
            raise GitFactError("WORKTREE_NOT_CLEAN")
        changed = self._git(["diff-tree", "--no-commit-id", "--name-status", "-r", resolved], check=False)
        if not apply:
            return {"status": "DRY_RUN", "operation": "REVERT", "commit": resolved,
                    "changed_paths": [line for line in changed.splitlines() if line]}
        self._require_author()
        self._git(["revert", "--no-edit", resolved])
        return {"status": "REVERTED", "reverted_commit": resolved,
                "commit": self._git(["rev-parse", "HEAD"]),
                "changed_paths": [line for line in changed.splitlines() if line]}

    @staticmethod
    def _markdown(candidate: Candidate, metadata: dict) -> str:
        dependencies = "\n".join(
            f"- [{ref.fact_id} v{ref.version}](../{ref.fact_id}/v{ref.version}.md)"
            for ref in candidate.dependencies) or "- 无"
        sources = "\n".join(f"- {source.citation}；定位：{source.locator}" for source in candidate.sources) or "- 无"
        artifacts = "\n".join(
            f"- [{artifact.name}](v{metadata['version']}-artifacts/{artifact.name})"
            f"（{artifact.kind}；SHA-256：`{item['sha256']}`）"
            for artifact, item in zip(candidate.artifacts, metadata.get("artifacts", []))
        ) or "- 无"
        proof = _nested_markdown(candidate.proof, 3)
        digest = metadata["candidate_digest"]
        return (f"# {_flat(candidate.title)}\n\n"
                f"> [!info] Fact 元数据\n> - Fact ID：`{metadata['fact_id']}`\n"
                f"> - 版本：{metadata['version']}\n> - 状态：`{metadata['status']}`\n"
                f"> - 证据等级：`{metadata['evidence_level']}`\n> - 接纳时间：{metadata['admitted']}\n"
                f"> - 候选摘要：`{digest}`\n\n"
                f"> [!note] 证据范围\n> `AI_REVIEWED` 表示独立模型审查未发现错误或缺口，不等同于形式化证明。\n\n"
                f"## 命题\n\n{candidate.statement}\n\n## 假设\n\n{candidate.assumptions or '无额外假设。'}\n\n"
                f"## 证明\n\n{proof}\n\n## 审查与证据\n\n"
                f"- [独立审查报告](../../reviews/{digest}.md)\n"
                f"- 审查摘要：`{metadata['review_digest']}`\n\n"
                f"## 计算附件\n\n{artifacts}\n\n"
                f"## 依赖\n\n{dependencies}\n\n## 来源\n\n{sources}\n")
