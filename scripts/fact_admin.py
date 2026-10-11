"""Explicit human/host entry points for Git Fact review and admission."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service"))

from orpheus_fact.git_facts import GitFactError, GitFactStore  # noqa: E402
from orpheus_fact.models import FactRef, Review  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Explicit Git Fact maintenance")
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review")
    review.add_argument("candidate_digest")
    review.add_argument("--file", type=Path, required=True)
    accept = commands.add_parser("accept")
    accept.add_argument("candidate_digest")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("fact_id")
    revoke.add_argument("version", type=int)
    revoke.add_argument("--reason", required=True)
    commands.add_parser("integrity")
    restore = commands.add_parser("restore")
    restore.add_argument("incident_id")
    restore.add_argument("commit")
    restore.add_argument("paths", nargs="+")
    restore.add_argument("--apply", action="store_true",
                         help="执行恢复；默认只预览，不修改工作区")
    revert = commands.add_parser("revert")
    revert.add_argument("commit")
    revert.add_argument("--apply", action="store_true",
                        help="执行 Git revert；默认只预览，不修改工作区")
    rebuild = commands.add_parser("rebuild-index")
    rebuild.add_argument("target", type=Path)
    remote = commands.add_parser("remote-status")
    remote.add_argument("--remote", default="origin")
    remote.add_argument("--output", type=Path,
                        help="写出不含 remote URL 或凭据的本地审计 JSON")
    args = parser.parse_args(argv)
    store = GitFactStore(args.root)
    try:
        if args.command == "review":
            review = Review.model_validate_json(args.file.read_text(encoding="utf-8"))
            result = store.record_review(args.candidate_digest, review)
        elif args.command == "accept":
            result = store.accept(args.candidate_digest)
        elif args.command == "revoke":
            result = store.revoke(FactRef(fact_id=args.fact_id, version=args.version), args.reason)
        elif args.command == "integrity":
            # CI/reporting is explicitly read-only: expose underlying errors
            # without trying to commit an incident from an unconfigured runner.
            result = store.integrity_check(record_incident=False)
        elif args.command == "restore":
            result = (store.restore_from_commit(args.incident_id, args.commit, args.paths)
                      if args.apply else store.preview_restore(args.incident_id, args.commit, args.paths))
        elif args.command == "revert":
            result = store.revert_commit(args.commit, apply=args.apply)
        elif args.command == "rebuild-index":
            result = {"status": "REBUILT", "index": str(store.rebuild_index(args.target))}
        else:
            result = store.remote_protection_status(args.remote)
    except (GitFactError, OSError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    if args.command == "remote-status" and args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = {**result, "audit_file": str(args.output)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == "integrity" and result.get("status") != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
