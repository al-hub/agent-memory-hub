#!/usr/bin/env python3
"""agent-memory-hub: dependency-free local L2 memory CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from pathlib import Path

HOME = Path(os.environ.get("AGENT_MEMORY_HUB_HOME", "~/.agent-memory-hub")).expanduser()
STATUSES = ("candidate", "confirmed", "needs_review", "conflict", "superseded", "stale", "rejected")
TYPES = ("fact", "preference", "decision", "constraint", "lesson", "mistake", "project_state", "hypothesis", "temporary", "observation")
QUALITIES = ("clear", "partial", "ambiguous")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories(
 id TEXT PRIMARY KEY, statement TEXT NOT NULL, normalized_hash TEXT NOT NULL,
 type TEXT NOT NULL, status TEXT NOT NULL, confidence REAL NOT NULL,
 context_quality TEXT NOT NULL, source_agent TEXT, source_type TEXT,
 source_pointer TEXT, source_hash TEXT, evidence_group TEXT,
 valid_from TEXT, valid_until TEXT, superseded_by TEXT,
 created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hash ON memories(normalized_hash);
CREATE INDEX IF NOT EXISTS idx_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_type ON memories(type);
CREATE TABLE IF NOT EXISTS relations(
 id INTEGER PRIMARY KEY AUTOINCREMENT, from_id TEXT NOT NULL,
 relation TEXT NOT NULL, to_id TEXT NOT NULL, created_at INTEGER NOT NULL,
 UNIQUE(from_id, relation, to_id)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def root(args):
    return Path(args.home or HOME).expanduser()


def stamp():
    return int(time.time())


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def emit_event(home, kind, **data):
    home.mkdir(parents=True, exist_ok=True)
    with (home / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": kind, "ts": stamp(), **data}, ensure_ascii=False) + "\n")


def connect(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "raw").mkdir(exist_ok=True)
    con = sqlite3.connect(home / "memory.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, statement)")
        con.execute("INSERT OR REPLACE INTO meta VALUES('fts5','1')")
    except sqlite3.OperationalError:
        con.execute("INSERT OR REPLACE INTO meta VALUES('fts5','0')")
    return con


def fts_enabled(con):
    row = con.execute("SELECT value FROM meta WHERE key='fts5'").fetchone()
    return bool(row and row[0] == "1")


def cmd_init(args):
    home = root(args)
    with connect(home) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES('schema_version','1')")
        fts = fts_enabled(con)
    emit_event(home, "store_initialized", schema_version=1, fts5=fts)
    print(f"Initialized: {home}")
    print(f"SQLite FTS5: {'yes' if fts else 'no; LIKE fallback'}")


def insert_memory(args, quiet=False):
    home, statement = root(args), args.statement.strip()
    if not statement:
        raise SystemExit("statement must not be empty")
    if not 0 <= args.confidence <= 1:
        raise SystemExit("confidence must be 0..1")
    nhash, ts = digest(norm(statement)), stamp()
    with connect(home) as con:
        old = con.execute("SELECT id,status,statement FROM memories WHERE normalized_hash=? LIMIT 1", (nhash,)).fetchone()
        if old:
            if not quiet:
                print(f"Duplicate: {old['id']} [{old['status']}] {old['statement']}")
            return old["id"], False
        mid = "mem_" + uuid.uuid4().hex[:12]
        con.execute("""INSERT INTO memories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            mid, statement, nhash, args.type, args.status, args.confidence,
            args.context_quality, args.source_agent, args.source_type,
            args.source_pointer, args.source_hash, args.evidence_group,
            args.valid_from, args.valid_until, None, ts, ts))
        if fts_enabled(con):
            con.execute("INSERT INTO memory_fts(id,statement) VALUES(?,?)", (mid, statement))
        if args.conflicts_with:
            if not con.execute("SELECT 1 FROM memories WHERE id=?", (args.conflicts_with,)).fetchone():
                raise SystemExit(f"memory not found: {args.conflicts_with}")
            for a, b in ((mid, args.conflicts_with), (args.conflicts_with, mid)):
                con.execute("INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)", (a, "conflicts_with", b, ts))
            con.execute("UPDATE memories SET status='conflict',updated_at=? WHERE id IN (?,?)", (ts, mid, args.conflicts_with))
            args.status = "conflict"
    emit_event(home, "memory_created", id=mid, status=args.status, type=args.type, source_agent=args.source_agent)
    if not quiet:
        print(f"Added: {mid} [{args.status}] {statement}")
    return mid, True


def words(q):
    return [x for x in re.findall(r"[\w가-힣.-]+", q.lower()) if len(x) > 1]


def cmd_recall(args):
    home = root(args)
    if not (home / "memory.db").exists():
        raise SystemExit("memory store is not initialized; run init")
    statuses = ["confirmed", "candidate", "needs_review", "conflict", "stale"]
    if args.include_superseded:
        statuses.append("superseded")
    if args.include_rejected:
        statuses.append("rejected")
    terms = words(args.query)
    if not terms:
        raise SystemExit("query needs at least one searchable term")
    limit = max(1, min(args.limit, 50))
    with connect(home) as con:
        marks = ",".join("?" for _ in statuses)
        rows = []
        if fts_enabled(con):
            safe = [t.replace('"', '') for t in terms]
            match = " OR ".join('"' + t + '"' for t in safe if t)
            if match:
                try:
                    rows = con.execute(
                        f"SELECT m.*,bm25(memory_fts) rank FROM memory_fts JOIN memories m ON m.id=memory_fts.id WHERE memory_fts MATCH ? AND m.status IN ({marks}) ORDER BY rank,m.confidence DESC LIMIT ?",
                        [match, *statuses, limit]).fetchall()
                except sqlite3.OperationalError:
                    rows = []
        if not rows:
            clauses = " OR ".join("lower(statement) LIKE ?" for _ in terms)
            rows = con.execute(
                f"SELECT m.*,0 rank FROM memories m WHERE ({clauses}) AND status IN ({marks}) ORDER BY confidence DESC,updated_at DESC LIMIT ?",
                [*[f"%{t}%" for t in terms], *statuses, limit]).fetchall()
        pack = []
        for r in rows:
            rels = [dict(x) for x in con.execute("SELECT relation,to_id FROM relations WHERE from_id=?", (r["id"],))]
            pack.append({"id": r["id"], "statement": r["statement"], "type": r["type"],
                         "status": r["status"], "confidence": r["confidence"],
                         "context_quality": r["context_quality"],
                         "source": {"agent": r["source_agent"], "type": r["source_type"], "pointer": r["source_pointer"], "evidence_group": r["evidence_group"]},
                         "valid_from": r["valid_from"], "valid_until": r["valid_until"], "relations": rels})
    if args.json:
        print(json.dumps({"query": args.query, "count": len(pack), "memories": pack}, ensure_ascii=False, indent=2))
    elif not pack:
        print("No relevant memory found.")
    else:
        print(f"Context pack: {len(pack)} memory(s)")
        for m in pack:
            warn = " !" if m["status"] in ("needs_review", "conflict", "stale") else ""
            print(f"- {m['id']} [{m['status']}{warn}, {m['confidence']:.2f}, {m['type']}] {m['statement']}")
            if m["source"]["pointer"]:
                print(f"  source: {m['source']['pointer']}")


def cmd_status(args):
    home = root(args)
    if not (home / "memory.db").exists():
        print(f"Not initialized: {home}"); return
    with connect(home) as con:
        total = con.execute("SELECT count(*) FROM memories").fetchone()[0]
        grouped = con.execute("SELECT status,count(*) n FROM memories GROUP BY status ORDER BY status").fetchall()
        conflicts = con.execute("SELECT count(*) FROM relations WHERE relation='conflicts_with'").fetchone()[0] // 2
        print(f"Home: {home}\nMemories: {total}\nFTS5: {'yes' if fts_enabled(con) else 'no'}\nConflicts: {conflicts}")
        if grouped:
            print("Status: " + ", ".join(f"{r['status']}={r['n']}" for r in grouped))


def cmd_inspect(args):
    with connect(root(args)) as con:
        r = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
        if not r: raise SystemExit(f"memory not found: {args.id}")
        data = dict(r)
        data["relations"] = [dict(x) for x in con.execute("SELECT relation,to_id,created_at FROM relations WHERE from_id=?", (args.id,))]
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_resolve(args):
    home, ts = root(args), stamp()
    with connect(home) as con:
        if not con.execute("SELECT 1 FROM memories WHERE id=?", (args.id,)).fetchone():
            raise SystemExit(f"memory not found: {args.id}")
        if args.superseded_by and not con.execute("SELECT 1 FROM memories WHERE id=?", (args.superseded_by,)).fetchone():
            raise SystemExit(f"memory not found: {args.superseded_by}")
        con.execute("UPDATE memories SET status=?,superseded_by=?,updated_at=? WHERE id=?", (args.status, args.superseded_by, ts, args.id))
        if args.superseded_by:
            con.execute("INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)", (args.id, "superseded_by", args.superseded_by, ts))
    emit_event(home, "memory_resolved", id=args.id, status=args.status, superseded_by=args.superseded_by)
    print(f"Resolved: {args.id} -> {args.status}")


def discover():
    h, c = Path.home(), Path.cwd()
    candidates = [("claude", h/".claude"/"CLAUDE.md"), ("codex", h/".codex"/"AGENTS.md"),
                  ("gemini", h/".gemini"/"GEMINI.md"), ("generic", c/"AGENTS.md"),
                  ("generic", c/"CLAUDE.md"), ("generic", c/"GEMINI.md")]
    return [(a, p.resolve()) for a, p in candidates if p.is_file()]


def chunks(text, size=1800):
    blocks = re.split(r"\n(?=#{1,6}\s)|\n\s*\n", text.replace("\r\n", "\n"))
    out, buf = [], ""
    for b in (x.strip() for x in blocks if x.strip()):
        if len(buf) + len(b) + 2 <= size: buf = (buf + "\n\n" + b).strip()
        else:
            if buf: out.append(buf)
            if len(b) <= size: buf = b
            else:
                out.extend(b[i:i+size] for i in range(0, len(b), size)); buf = ""
    if buf: out.append(buf)
    return out


def cmd_import(args):
    home, sources = root(args), discover()
    for raw in args.source or []:
        p = Path(raw).expanduser().resolve()
        if p.is_file(): sources.append((args.source_agent or "manual", p))
        elif p.is_dir(): sources.extend((args.source_agent or "manual", x.resolve()) for x in sorted(p.glob("*.md")))
        else: print(f"Skipping missing source: {p}", file=sys.stderr)
    unique, seen = [], set()
    for a, p in sources:
        if str(p) not in seen: seen.add(str(p)); unique.append((a, p))
    if not unique:
        print("No accessible L1 text sources discovered. Use --source PATH."); return
    if args.dry_run: print("Discovered L1 sources (dry run):")
    total = 0
    for agent, path in unique:
        text = path.read_text(encoding="utf-8", errors="replace")
        parts, shash = chunks(text), digest(text)
        if args.dry_run:
            print(f"- {agent}: {path} ({len(parts)} chunk(s))"); total += len(parts); continue
        rawcopy = home / "raw" / f"{shash[:16]}-{path.name}"
        rawcopy.parent.mkdir(parents=True, exist_ok=True)
        if not rawcopy.exists(): shutil.copyfile(path, rawcopy)
        added = 0
        for i, part in enumerate(parts, 1):
            ns = argparse.Namespace(home=str(home), statement=part, type="observation", status="needs_review", confidence=.60,
                context_quality="partial", source_agent=agent, source_type="l1_file", source_pointer=f"{path}#chunk-{i}",
                source_hash=shash, evidence_group=f"file:{shash}", valid_from=None, valid_until=None, conflicts_with=None)
            _, fresh = insert_memory(ns, quiet=True); added += int(fresh)
        total += added
        emit_event(home, "l1_source_imported", source_agent=agent, source_pointer=str(path), source_hash=shash, added=added)
        print(f"Imported {agent}: {path} -> {added}/{len(parts)} new")
    print(f"{'Would examine' if args.dry_run else 'Done:'} {total} {'chunk(s)' if args.dry_run else 'new candidate(s)'}.")
    if not args.dry_run: print("L1 imports are needs_review until deliberately promoted.")


def cmd_doctor(args):
    home = root(args)
    if not (home/"memory.db").exists(): print("[FAIL] memory.db missing"); raise SystemExit(1)
    errors = 0
    with connect(home) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        print(f"[{'OK' if integrity == 'ok' else 'FAIL'}] sqlite integrity: {integrity}")
        errors += integrity != "ok"
        dangling = con.execute("SELECT count(*) FROM relations r LEFT JOIN memories a ON a.id=r.from_id LEFT JOIN memories b ON b.id=r.to_id WHERE a.id IS NULL OR b.id IS NULL").fetchone()[0]
        print(f"[{'OK' if not dangling else 'FAIL'}] dangling relations: {dangling}"); errors += bool(dangling)
        print(f"[OK] FTS5: {'enabled' if fts_enabled(con) else 'unavailable; LIKE fallback active'}")
    ev = home/"events.jsonl"; bad = 0
    if ev.exists():
        for line in ev.read_text(encoding="utf-8").splitlines():
            try: json.loads(line)
            except json.JSONDecodeError: bad += 1
        print(f"[{'OK' if not bad else 'FAIL'}] event log invalid lines: {bad}"); errors += bool(bad)
    else: print("[WARN] event log not created yet")
    if errors: raise SystemExit(1)


def parser():
    p = argparse.ArgumentParser(prog="memory-hub", description="Shared local L2 memory for AI agents")
    p.add_argument("--home")
    sub = p.add_subparsers(dest="cmd", required=True)
    x=sub.add_parser("init"); x.set_defaults(func=cmd_init)
    x=sub.add_parser("add"); x.add_argument("statement"); x.add_argument("--type",choices=TYPES,default="fact"); x.add_argument("--status",choices=STATUSES,default="candidate"); x.add_argument("--confidence",type=float,default=.70); x.add_argument("--context-quality",choices=QUALITIES,default="clear"); x.add_argument("--source-agent"); x.add_argument("--source-type",default="conversation"); x.add_argument("--source-pointer"); x.add_argument("--source-hash"); x.add_argument("--evidence-group"); x.add_argument("--valid-from"); x.add_argument("--valid-until"); x.add_argument("--conflicts-with"); x.set_defaults(func=insert_memory)
    x=sub.add_parser("recall"); x.add_argument("query"); x.add_argument("--limit",type=int,default=8); x.add_argument("--json",action="store_true"); x.add_argument("--include-superseded",action="store_true"); x.add_argument("--include-rejected",action="store_true"); x.set_defaults(func=cmd_recall)
    x=sub.add_parser("status"); x.set_defaults(func=cmd_status)
    x=sub.add_parser("inspect"); x.add_argument("id"); x.set_defaults(func=cmd_inspect)
    x=sub.add_parser("resolve"); x.add_argument("id"); x.add_argument("--status",choices=STATUSES,required=True); x.add_argument("--superseded-by"); x.set_defaults(func=cmd_resolve)
    x=sub.add_parser("import-l1"); x.add_argument("--dry-run",action="store_true"); x.add_argument("--source",action="append"); x.add_argument("--source-agent"); x.set_defaults(func=cmd_import)
    x=sub.add_parser("doctor"); x.set_defaults(func=cmd_doctor)
    return p


def main(argv=None):
    args = parser().parse_args(argv); args.func(args); return 0

if __name__ == "__main__":
    raise SystemExit(main())
