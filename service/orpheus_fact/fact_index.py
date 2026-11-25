"""Disposable discovery index over a committed Git facts tree."""
from __future__ import annotations

from contextlib import closing, contextmanager
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import subprocess


def _git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], cwd=root, input=data, capture_output=True, check=True).stdout


def _version_blobs(root: Path, tree: str) -> dict:
    versions = {}
    if tree:
        for entry in _git(root, "ls-tree", "-rz", tree).split(b"\0"):
            match = re.fullmatch(rb"[0-7]+ blob ([a-f0-9]+)\t(fact-[a-f0-9]+)/v([1-9][0-9]*)\.(md|json)", entry)
            if match:
                oid, fact_id, version, ext = match.groups()
                versions.setdefault((fact_id.decode(), int(version)), {})[ext] = oid
    return versions


def _read_blobs(root: Path, ids: set[bytes]) -> dict:
    if not ids:
        return {}
    stream = BytesIO(_git(root, "cat-file", "--batch", data=b"\n".join(ids) + b"\n"))
    blobs = {}
    for _ in ids:
        oid, kind, size = stream.readline().split()
        if kind != b"blob":
            raise ValueError("Fact index expected a Git blob")
        blobs[oid] = stream.read(int(size)).decode("utf-8")
        stream.read(1)
    return blobs


def _refresh(db, root, tree, force):
    db.execute("CREATE TABLE IF NOT EXISTS cache_state(tree TEXT)")
    if force or db.execute("PRAGMA user_version").fetchone()[0] != 1:
        for table in ("facts", "edges", "cache_state"):
            db.execute(f"DROP TABLE IF EXISTS {table}")
        db.execute("CREATE TABLE cache_state(tree TEXT)")
        db.execute("""CREATE TABLE facts(fact_id TEXT, version INTEGER, title TEXT, status TEXT,
            evidence TEXT, body TEXT, folded TEXT, stamp TEXT, PRIMARY KEY(fact_id,version))""")
        db.execute("""CREATE TABLE edges(parent TEXT, pv INTEGER, child TEXT, cv INTEGER,
            PRIMARY KEY(child,cv,parent,pv))""")
        db.execute("CREATE INDEX dependents ON edges(parent,pv)")
        db.execute("PRAGMA user_version=1")
    if db.execute("SELECT tree FROM cache_state").fetchone() == (tree,):
        return

    versions = _version_blobs(root, tree)
    previous = {(i, v): stamp for i, v, stamp in db.execute("SELECT fact_id,version,stamp FROM facts")}
    stamps = {k: (v[b"md"] + b":" + v[b"json"]).decode() for k, v in versions.items()}
    changed = [k for k, stamp in stamps.items() if previous.get(k) != stamp]
    removed = previous.keys() - versions.keys()
    for key in [*removed, *changed]:
        db.execute("DELETE FROM edges WHERE child=? AND cv=?", key)
        db.execute("DELETE FROM facts WHERE fact_id=? AND version=?", key)

    blobs = _read_blobs(root, {oid for key in changed for oid in versions[key].values()})
    for key in changed:
        pair = versions[key]
        meta = json.loads(blobs[pair[b"json"]])
        body = blobs[pair[b"md"]].replace("\r\n", "\n")
        db.execute("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?)",
                   (*key, body.partition("\n")[0].removeprefix("# "), meta["status"],
                    meta["evidence_level"], body, body.casefold(), stamps[key]))
        db.executemany("INSERT OR IGNORE INTO edges VALUES(?,?,?,?)",
                       [(d["fact_id"], d["version"], *key) for d in meta["dependencies"]])
    db.execute("DELETE FROM cache_state")
    db.execute("INSERT INTO cache_state VALUES(?)", (tree,))


@contextmanager
def index_connection(root: Path, tree: str, target: Path, *, force=False):
    """Synchronize against one immutable snapshot and query in the same transaction."""
    def prepare(path):
        db = sqlite3.connect(path, timeout=30)
        try:
            if not force and db.execute("PRAGMA user_version").fetchone()[0] == 1:
                db.execute("BEGIN")
                if db.execute("SELECT tree FROM cache_state").fetchone() == (tree,):
                    return db
                db.rollback()
            db.execute("BEGIN IMMEDIATE")
            _refresh(db, root, tree, force)
            return db
        except BaseException:
            db.close()
            raise

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        db = prepare(target)
    except (OSError, sqlite3.DatabaseError):
        if force:
            raise
        db = prepare(":memory:")
    with closing(db), db:
        yield db


def _fields(body: str, title: str):
    # Delimit only canonical headings. Other headings inside a proof stay in that field.
    parts = re.split(r"(?m)^## (命题|假设|证明|审查与证据|计算附件|依赖|来源)[ \t]*$", body)
    sections = dict(zip(parts[1::2], parts[2::2]))
    return [("title", title), ("statement", sections.get("命题", "").strip()),
            ("assumptions", sections.get("假设", "").strip()), ("proof", sections.get("证明", "").strip()),
            ("body", body)]


def search(db, query, limit, dependency=None):
    terms = tuple(dict.fromkeys(query.casefold().split()))
    where = ["status='ACTIVE'"]
    args = []
    if terms:
        where.append("instr(folded, ?) > 0")
        args.append(max(terms, key=len))
    if dependency:
        where.append("""EXISTS (SELECT 1 FROM edges WHERE parent=? AND pv=?
                       AND child=facts.fact_id AND cv=facts.version)""")
        args.extend((dependency.fact_id, dependency.version))
    sql = "SELECT fact_id, version, title, evidence, body FROM facts WHERE " + " AND ".join(where)
    if not terms:
        sql += " ORDER BY fact_id,version DESC LIMIT ?"
        args.append(limit)
    results = []
    for fact_id, version, title, evidence, body in db.execute(sql, args):
        locations = {}
        field_name, snippet = "title", title[:160]
        for priority, (field, value) in enumerate(_fields(body, title) if terms else []):
            folded = value.casefold()
            hits = [(t, folded.find(t)) for t in terms if t not in locations and t in folded]
            if hits and not locations:
                field_name = field
                pos = min(offset for _, offset in hits)
                # Case folding may expand characters before a match (e.g. ß).
                if len(folded) != len(value):
                    offset = 0
                    for i, char in enumerate(value):
                        offset += len(char.casefold())
                        if offset > pos:
                            pos = i
                            break
                snippet = " ".join(value[max(0, pos-35):pos+125].split())
            locations.update((t, priority) for t, _ in hits)
            if len(locations) == len(terms):
                break
        if len(locations) != len(terms):
            continue
        rank = (max(locations.values(), default=0), sum(locations.values()), fact_id, -version)
        results.append((rank, dict(fact_id=fact_id, version=version, title=title, status="ACTIVE",
                                   evidence_level=evidence, matched_field=field_name, snippet=snippet)))
    results.sort(key=lambda item: item[0])
    return [fact for _, fact in results[:limit]]
