import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from orpheus_fact.git_facts import GitFactError, GitFactStore, IntegrityError
from orpheus_fact.models import Artifact, Candidate, FactRef, Review
from scripts import fact_admin


def init_repo(path: Path):
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=path, check=True)


def make_candidate(title="Square"):
    return Candidate(title=title, statement="$x^2\\geq0$", assumptions="x is real", proof="$x^2$ is nonnegative.")


def make_review(candidate, verdict="PASS"):
    return Review(candidate_digest=candidate.digest(), rule_digest="a" * 64, verdict=verdict,
                  summary="Checked", report_markdown="# Review\n\nChecked.", repair_hints="" if verdict == "PASS" else "Repair proof.")


@pytest.fixture
def git_store(tmp_path):
    init_repo(tmp_path)
    return GitFactStore(tmp_path)


def test_candidate_review_accept_are_bound_to_git_and_readable(git_store):
    candidate = make_candidate()
    submitted = git_store.submit("request-1", candidate)
    reviewed = git_store.record_review(candidate.digest(), make_review(candidate))
    accepted = git_store.accept(candidate.digest())
    assert submitted["commit"] != reviewed["commit"]
    assert accepted["status"] == "ACCEPTED"
    assert accepted["remote_sync"]["status"] == "NOT_CONFIGURED"
    fact = git_store.get(FactRef(fact_id=accepted["fact_id"], version=1))
    assert "x^2" in fact["markdown"]
    assert "> [!info] Fact 元数据" in fact["markdown"]
    assert "> [!note] 证据范围" in fact["markdown"]
    assert f"[独立审查报告](../../reviews/{candidate.digest()}.md)" in fact["markdown"]
    commit_text = subprocess.run(["git", "show", "--format=%B", "--no-patch", accepted["commit"]], cwd=git_store.root, check=True, capture_output=True, text=True).stdout
    assert candidate.digest() in commit_text
    assert fact["dependencies"] == []


def test_embedded_markdown_keeps_obsidian_heading_hierarchy(git_store):
    candidate = Candidate(title="Readable", statement="$x=x$", assumptions="无。",
                          proof="# 重复标题\n\n## 引理\n\n证明。")
    git_store.submit("readable", candidate)
    git_store.record_review(candidate.digest(), make_review(candidate))
    accepted = git_store.accept(candidate.digest())
    fact = git_store.get(FactRef(fact_id=accepted["fact_id"], version=1))["markdown"]
    review = (git_store.reviews / f"{candidate.digest()}.md").read_text(encoding="utf-8")
    assert "\n# 重复标题" not in fact
    assert "\n### 重复标题" in fact
    assert "\n#### 引理" in fact
    assert review.count("\n# ") == 0
    assert "\n## Review" in review
    assert review.count("修补建议") == 0


def test_computational_fact_versions_script_report_and_hashes(git_store):
    candidate = Candidate(
        title="Exact enumeration",
        statement="The finite search returns three cases.",
        assumptions="Python integer arithmetic.",
        proof="The attached script exhausts range(3); the report records every output.",
        artifacts=(
            Artifact(name="enumerate.py", kind="script",
                     content="print(list(range(3)))\n"),
            Artifact(name="experiment.md", kind="report",
                     content="# Experiment\n\nOutput: `[0, 1, 2]`.\n"),
            Artifact(name="result.json", kind="data",
                     content='{"outputs":[0,1,2]}\n'),
        ),
    )
    submitted = git_store.submit("exact-enumeration", candidate)
    snapshot = git_store._candidate(submitted["candidate_digest"])
    assert snapshot.artifacts == candidate.artifacts
    git_store.record_review(candidate.digest(), make_review(candidate))
    accepted = git_store.accept(candidate.digest())
    directory = git_store.facts / accepted["fact_id"]
    script = directory / "v1-artifacts/enumerate.py"
    report = directory / "v1-artifacts/experiment.md"
    assert script.read_text(encoding="utf-8") == "print(list(range(3)))\n"
    assert report.read_text(encoding="utf-8") == "# Experiment\n\nOutput: `[0, 1, 2]`.\n"
    fact = git_store.get(FactRef(fact_id=accepted["fact_id"], version=1))
    assert fact["artifacts"][0]["sha256"] == __import__("hashlib").sha256(script.read_bytes()).hexdigest()
    assert "v1-artifacts/enumerate.py" in fact["markdown"]
    assert git_store.integrity_check()["status"] == "PASS"


def test_new_computational_candidate_requires_script_report_and_machine_result(git_store):
    candidate = Candidate(
        title="Incomplete computation",
        statement="The run succeeds.",
        assumptions="Python.",
        proof="See the attached script and report.",
        artifacts=(
            Artifact(name="run.py", kind="script", content="print(1)\n"),
            Artifact(name="report.md", kind="report", content="# Report\n\nResult: 1.\n"),
        ),
    )
    with pytest.raises(GitFactError, match="COMPUTATION_ARTIFACTS_INCOMPLETE:data_or_certificate"):
        git_store.submit("incomplete-computation", candidate)


def test_empty_artifact_field_preserves_legacy_candidate_digest():
    candidate = make_candidate()
    legacy = {
        "title": candidate.title,
        "statement": candidate.statement,
        "assumptions": candidate.assumptions,
        "proof": candidate.proof,
        "sources": [],
        "dependencies": [],
        "revises": None,
    }
    import hashlib
    canonical = json.dumps(legacy, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert candidate.digest() == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_request_key_binding_is_idempotent_and_conflicts_are_rejected(git_store):
    first = make_candidate("First")
    initial = git_store.submit("same-request", first)
    repeated = git_store.submit("same-request", first)
    assert repeated["idempotent"] is True
    for result in (initial, repeated):
        assert result["required_next_action"] == "START_FRESH_COLD_REVIEW"
        assert result["review_status"] == "NOT_STARTED"
        assert result["research_checks_do_not_replace_review"] is True
    assert repeated["commit"] == initial["commit"]
    with pytest.raises(GitFactError, match="REQUEST_CONFLICT"):
        git_store.submit("same-request", make_candidate("Different"))
    mappings = list(git_store.requests.glob("*.json"))
    assert len(mappings) == 1
    assert mappings[0].stem == repeated["request_key_sha256"]
    assert mappings[0].relative_to(git_store.root).as_posix() in (git_store.facts / "MANIFEST.json").read_text(encoding="utf-8")


def test_review_is_immutable_but_same_content_is_idempotent(git_store):
    candidate = make_candidate("Review")
    git_store.submit("review-request", candidate)
    review = make_review(candidate)
    initial = git_store.record_review(candidate.digest(), review)
    repeated = git_store.record_review(candidate.digest(), review)
    assert repeated["idempotent"] is True
    assert repeated["commit"] == initial["commit"]
    changed = Review(candidate_digest=candidate.digest(), rule_digest="b" * 64, verdict="PASS",
                     summary="Changed", report_markdown="# Changed", repair_hints="")
    with pytest.raises(GitFactError, match="REVIEW_IMMUTABLE"):
        git_store.record_review(candidate.digest(), changed)


def test_accept_is_idempotent_for_an_already_accepted_candidate(git_store):
    candidate = make_candidate("Accept")
    git_store.submit("accept-request", candidate)
    git_store.record_review(candidate.digest(), make_review(candidate))
    initial = git_store.accept(candidate.digest())
    repeated = git_store.accept(candidate.digest())
    assert repeated["idempotent"] is True
    assert repeated["fact_id"] == initial["fact_id"]
    assert repeated["version"] == initial["version"]
    assert repeated["commit"] == initial["commit"]
    assert len(list(git_store.facts.glob("fact-*/v1.json"))) == 1


def test_accept_pushes_to_configured_origin_and_idempotent_accept_retries(git_store, tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=git_store.root, check=True)
    candidate = make_candidate("Remote backup")
    git_store.submit("remote-backup", candidate)
    git_store.record_review(candidate.digest(), make_review(candidate))

    accepted = git_store.accept(candidate.digest())
    assert accepted["remote_sync"]["status"] == "SYNCED"
    assert accepted["remote_sync"]["commit"] == subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=git_store.root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    assert subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/main"],
        check=True, capture_output=True, text=True,
    ).stdout.strip() == accepted["commit"]

    repeated = git_store.accept(candidate.digest())
    assert repeated["idempotent"] is True
    assert repeated["remote_sync"]["status"] == "SYNCED"


def test_push_failure_keeps_local_fact_accepted(git_store, tmp_path):
    missing_remote = tmp_path / "missing.git"
    subprocess.run(["git", "remote", "add", "origin", str(missing_remote)],
                   cwd=git_store.root, check=True)
    candidate = make_candidate("Pending remote")
    git_store.submit("pending-remote", candidate)
    git_store.record_review(candidate.digest(), make_review(candidate))
    accepted = git_store.accept(candidate.digest())
    assert accepted["status"] == "ACCEPTED"
    assert accepted["remote_sync"] == {
        "status": "REMOTE_PENDING", "remote": "origin", "reason": "PUSH_FAILED"
    }
    assert git_store.get(FactRef(fact_id=accepted["fact_id"], version=1))["status"] == "ACTIVE"


def test_explicit_cli_review_then_accept_is_the_admission_path(git_store, tmp_path, capsys):
    candidate = make_candidate("CLI")
    git_store.submit("cli-request", candidate)
    review_path = tmp_path / "review.json"
    review_path.write_text(make_review(candidate).model_dump_json(), encoding="utf-8")
    assert fact_admin.main(["--root", str(git_store.root), "review", candidate.digest(), "--file", str(review_path)]) == 0
    assert fact_admin.main(["--root", str(git_store.root), "accept", candidate.digest()]) == 0
    assert git_store.search("CLI")[0]["status"] == "ACTIVE"


def test_admin_cli_integrity_rebuild_and_remote_status(git_store, tmp_path, capsys):
    candidate = make_candidate("Admin paths")
    git_store.submit("admin-paths", candidate)
    assert fact_admin.main(["--root", str(git_store.root), "integrity"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    index = tmp_path / "rebuilt.sqlite"
    assert fact_admin.main(["--root", str(git_store.root), "rebuild-index", str(index)]) == 0
    assert index.exists()
    capsys.readouterr()
    audit = tmp_path / "remote-audit.json"
    assert fact_admin.main(["--root", str(git_store.root), "remote-status", "--output", str(audit)]) == 0
    output = json.loads(capsys.readouterr().out)
    report = json.loads(audit.read_text(encoding="utf-8"))
    assert output["status"] == report["status"] == "REMOTE_NOT_CONFIGURED"
    assert report["verification_scope"] == "LOCAL_ONLY"
    assert "user-provided remote URL" in report["missing_user_actions"]
    assert "remote_url" not in report


def test_admin_cli_restore_is_explicit_and_uses_incident_evidence(git_store, tmp_path, capsys):
    candidate = make_candidate("Restore CLI")
    submitted = git_store.submit("restore-cli", candidate)
    path = git_store.candidates / (candidate.digest() + ".json")
    path.write_text(path.read_text(encoding="utf-8").replace("Restore CLI", "Tampered"), encoding="utf-8")
    with pytest.raises(IntegrityError) as failure:
        git_store.submit("blocked-cli", make_candidate("Blocked"))
    incident_id = str(failure.value).split(":", 1)[1]
    assert fact_admin.main(["--root", str(git_store.root), "restore", incident_id,
                            submitted["commit"], "candidates/" + path.name]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "DRY_RUN"
    assert fact_admin.main(["--root", str(git_store.root), "restore", incident_id,
                            submitted["commit"], "candidates/" + path.name, "--apply"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "RESTORED_EXPLICITLY"
    assert git_store._candidate(candidate.digest()).title == "Restore CLI"


def test_revision_adds_version_and_revoke_dependency_is_explicit(git_store):
    first = make_candidate()
    git_store.submit("first", first)
    git_store.record_review(first.digest(), make_review(first))
    accepted = git_store.accept(first.digest())
    ref = FactRef(fact_id=accepted["fact_id"], version=1)
    child = Candidate(title="Child", statement="Child statement", assumptions="", proof="Child proof.", dependencies=(ref,))
    git_store.submit("child", child)
    git_store.record_review(child.digest(), make_review(child))
    child_result = git_store.accept(child.digest())
    revision = Candidate(title="Square revised", statement=first.statement, assumptions=first.assumptions,
                         proof="A revised proof.", revises=ref)
    git_store.submit("revision", revision)
    git_store.record_review(revision.digest(), make_review(revision))
    second = git_store.accept(revision.digest())
    assert second["fact_id"] == ref.fact_id and second["version"] == 2
    assert git_store.get(FactRef(fact_id=ref.fact_id, version=1))["status"] == "ACTIVE"
    revoked = git_store.revoke(ref, "counterexample")
    assert revoked["affected"] == 2
    assert git_store.get(ref)["status"] == "REVOKED"
    assert git_store.get(FactRef(fact_id=child_result["fact_id"], version=1))["status"] == "INVALIDATED_BY_DEP"
    assert git_store.get(FactRef(fact_id=ref.fact_id, version=2))["status"] == "ACTIVE"


def test_integrity_records_incident_before_rejecting_direct_edit(git_store):
    candidate = make_candidate()
    git_store.submit("request", candidate)
    path = git_store.candidates / (candidate.digest() + ".json")
    path.write_text(path.read_text(encoding="utf-8").replace("Square", "Tampered"), encoding="utf-8")
    with pytest.raises(IntegrityError, match="INTEGRITY_INCIDENT_RECORDED"):
        git_store.submit("another", make_candidate("Other"))
    incidents = list((git_store.incidents).glob("*.json"))
    assert incidents
    assert "WORKTREE_DIRECT_MODIFICATION" in incidents[-1].read_text(encoding="utf-8")


def test_restore_requires_incident_and_is_explicit(git_store):
    candidate = make_candidate()
    submitted = git_store.submit("request", candidate)
    path = git_store.candidates / (candidate.digest() + ".json")
    path.write_text(path.read_text(encoding="utf-8").replace("Square", "Tampered"), encoding="utf-8")
    with pytest.raises(IntegrityError) as failure:
        git_store.submit("blocked", make_candidate("Other"))
    incident_id = str(failure.value).split(":", 1)[1]
    restored = git_store.restore_from_commit(incident_id, submitted["commit"], ["candidates/" + path.name])
    assert restored["status"] == "RESTORED_EXPLICITLY"
    assert git_store._candidate(candidate.digest()).title == "Square"


def test_admin_revert_defaults_to_dry_run(git_store, capsys):
    candidate = make_candidate("Revert preview")
    submitted = git_store.submit("revert-preview", candidate)
    head_before = git_store._git(["rev-parse", "HEAD"])
    assert fact_admin.main(["--root", str(git_store.root), "revert", submitted["commit"]]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "DRY_RUN"
    assert git_store._git(["rev-parse", "HEAD"]) == head_before


def test_manifest_hash_and_rebuildable_sqlite_index(git_store, tmp_path):
    candidate = make_candidate()
    git_store.submit("request", candidate)
    git_store.record_review(candidate.digest(), make_review(candidate))
    git_store.accept(candidate.digest())
    index = git_store.rebuild_index(tmp_path / "index.sqlite")
    assert index.exists()
    with subprocess.Popen(["git", "status", "--porcelain", "--", "facts", "candidates", "reviews"], cwd=git_store.root, stdout=subprocess.PIPE, text=True) as process:
        assert process.communicate()[0] == ""
    metadata = next(git_store.facts.glob("fact-*/v1.json"))
    metadata.write_text(metadata.read_text(encoding="utf-8").replace('"version": 1', '"version": 9'), encoding="utf-8")
    with pytest.raises(IntegrityError, match="INTEGRITY_INCIDENT_RECORDED"):
        git_store.integrity_check()


def test_remote_status_does_not_claim_unconfigured_protection(git_store):
    result = git_store.remote_protection_status()
    assert result["remote"] == "origin"
    assert result["configured"] is False
    assert result["protection_verified"] is False
    assert result["status"] == "REMOTE_NOT_CONFIGURED"
    assert result["verification_scope"] == "LOCAL_ONLY"


def test_read_only_integrity_does_not_require_git_author(tmp_path, monkeypatch):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "NUL")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "NUL")
    store = GitFactStore(tmp_path)
    assert store.integrity_check() == {"status": "PASS", "errors": [], "facts": 0}
    with pytest.raises(GitFactError, match="GIT_AUTHOR_NOT_CONFIGURED"):
        store.submit("mutation-without-author", make_candidate())
    assert not (tmp_path / "candidates").exists()
    assert not (tmp_path / "requests").exists()


def test_read_only_cli_reports_integrity_errors_without_incident_commit(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "NUL")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "NUL")
    (tmp_path / "facts").mkdir()
    (tmp_path / "facts/MANIFEST.json").write_text(
        '{"format": 1, "files": {"facts/missing.md": "deadbeef"}}\n', encoding="utf-8", newline="\n")
    assert fact_admin.main(["--root", str(tmp_path), "integrity"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "FAILED"
    assert result["incident_recorded"] is False
    assert not (tmp_path / "incidents").exists()


def test_fresh_linux_style_checkout_integrity_is_cross_platform(tmp_path, monkeypatch):
    source = Path(__file__).parents[1]
    expected_facts = len(list((source / "facts").glob("fact-*/v*.json")))
    for name in ("facts", "candidates", "reviews", "requests", "incidents"):
        source_dir = source / name
        if source_dir.exists():
            shutil.copytree(source_dir, tmp_path / name)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=tmp_path, check=True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "NUL")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "NUL")
    result = GitFactStore(tmp_path).integrity_check()
    assert result["status"] == "PASS"
    assert result["facts"] == expected_facts
