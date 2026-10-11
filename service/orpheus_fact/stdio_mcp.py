"""Thin stdio MCP entry point backed by the Git Fact history."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from .git_facts import GitFactError, GitFactStore
from .models import Artifact, Candidate, FactRef, Source


def repository_root(value: str | None = None) -> Path:
    root = Path(value or os.environ.get("ORPHEUS_REPO", Path.cwd())).resolve()
    if not (root / ".git").exists():
        raise GitFactError("GIT_REPOSITORY_REQUIRED")
    return root


def _candidate(candidate: dict, artifacts: tuple[Artifact, ...] | None = None) -> Candidate:
    wire = dict(candidate)
    embedded = tuple(Artifact.model_validate(item) for item in wire.get("artifacts", ()))
    if artifacts is not None and embedded:
        raise GitFactError("MIXED_ARTIFACT_INPUT")
    wire["sources"] = tuple(Source.model_validate(item) for item in wire.get("sources", ()))
    wire["dependencies"] = tuple(FactRef.model_validate(item) for item in wire.get("dependencies", ()))
    wire["artifacts"] = artifacts if artifacts is not None else embedded
    return Candidate.model_validate(wire)


def load_file_artifacts(artifact_files: list[dict]) -> tuple[Artifact, ...]:
    artifacts: list[Artifact] = []
    for item in artifact_files:
        if set(item) - {"path", "name", "kind"} or "path" not in item or "kind" not in item:
            raise GitFactError("INVALID_ARTIFACT_FILE_DESCRIPTOR")
        path = Path(str(item["path"])).expanduser().resolve()
        if not path.is_file():
            raise GitFactError(f"ARTIFACT_FILE_NOT_FOUND:{path}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise GitFactError(f"ARTIFACT_FILE_NOT_UTF8:{path}") from exc
        artifacts.append(Artifact(
            name=str(item.get("name") or path.name),
            kind=item["kind"],
            content=content,
        ))
    return tuple(artifacts)


def build_server(store: GitFactStore) -> MCPServer:
    server = MCPServer(
        "Orpheus Fact",
        version="0.3.0",
        instructions="Git-backed Fact history. Candidate submission never edits accepted facts.",
    )

    @server.tool()
    def fact_search(query: str, limit: int = 20) -> dict:
        return {"facts": store.search(query, limit)}

    @server.tool()
    def fact_get(fact_id: str, version: int) -> dict:
        return store.get(FactRef(fact_id=fact_id, version=version))

    @server.tool()
    def candidate_submit(request_key: str, candidate: dict) -> dict:
        """Store a fixed candidate snapshot; it cannot contain a verdict or model."""
        return store.submit(request_key, _candidate(candidate))

    @server.tool()
    def candidate_submit_files(request_key: str, candidate: dict, artifact_files: list[dict]) -> dict:
        """Submit a candidate while the service reads UTF-8 artifacts directly from local files."""
        return store.submit(request_key, _candidate(candidate, load_file_artifacts(artifact_files)))

    @server.tool()
    def submission_get(candidate_digest: str) -> dict:
        candidate = store._candidate(candidate_digest)
        review_path = store.reviews / (candidate_digest + ".json")
        if not review_path.exists():
            return {"candidate_digest": candidate_digest, "status": "SUBMITTED"}
        review = store._review(candidate_digest)
        return {"candidate_digest": candidate.digest(), "status": review.verdict,
                "summary": review.summary, "report_markdown": review.report_markdown}

    @server.tool()
    def fact_issue_report(fact_id: str, version: int, reason: str) -> dict:
        return store.report_issue(FactRef(fact_id=fact_id, version=version), reason)

    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    args = parser.parse_args(argv)
    store = GitFactStore(repository_root(str(args.root) if args.root else None))
    build_server(store).run("stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
