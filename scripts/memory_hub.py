#!/usr/bin/env python3
"""agent-memory-hub: local-first shared L2 memory CLI.

Schema v2 adds evidence/raw-source separation and orthogonal governance while
keeping v0.1 columns readable for a non-destructive migration path.
"""
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
LEGACY_STATUSES = ("candidate", "confirmed", "needs_review", "conflict", "superseded", "stale", "rejected")
TYPES = ("identity", "preference", "decision", "constraint", "project_state", "episode", "lesson", "fact", "procedure", "mistake", "hypothesis", "temporary", "observation")
QUALITIES = ("clear", "partial", "ambiguous")
LIFECYCLES = ("candidate", "active", "superseded", "archived", "quarantined")
REVIEW_STATES = ("verified", "unverified", "needs_review", "conflict")
SCOPES = ("global", "user", "project", "repository", "task", "agent", "session")

BASE_SCHEMA = """
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

V2_SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_sources(
 id TEXT PRIMARY KEY,
 source_agent TEXT,
 source_type TEXT NOT NULL,
 source_pointer TEXT,
 content_hash TEXT NOT NULL,
 evidence_group TEXT,
 local_snapshot TEXT,
 extraction_state TEXT NOT NULL DEFAULT 'cold',
 captured_at INTEGER NOT NULL,
 UNIQUE(content_hash, source_pointer)
);
CREATE INDEX IF NOT EXISTS idx_raw_hash ON raw_sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_raw_state ON raw_sources(extraction_state);

CREATE TABLE IF NOT EXISTS evidence(
 id TEXT PRIMARY KEY,
 memory_id TEXT NOT NULL,
 raw_source_id TEXT,
 source_agent TEXT,
 source_type TEXT,
 source_pointer TEXT,
 source_hash TEXT,
 evidence_group TEXT,
 excerpt TEXT,
 confidence REAL,
 created_at INTEGER NOT NULL,
 UNIQUE(memory_id, source_hash, source_pointer),
 FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE,
 FOREIGN KEY(raw_source_id) REFERENCES raw_sources(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_memory ON evidence(memory_id);
CREATE INDEX IF NOT EXISTS idx_evidence_raw ON evidence(raw_source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_group ON evidence(evidence_group);
"""


def root(args): return Path(args.home or HOME).expanduser()
def stamp(): return int(time.time())
def norm(s): return re.sub(r"\s+", " ", s.strip().lower())
def digest(s): return hashlib.sha256(s.encode("utf-8")).hexdigest()
def new_id(prefix): return prefix + uuid.uuid4().hex[:12]


def emit_event(home, kind, **data):
    home.mkdir(parents=True, exist_ok=True)
    with (home / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"event": kind, "ts": stamp(), **data}, ensure_ascii=False) + "\n")


def columns(con, table):
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def add_column(con, table, definition):
    name = definition.split()[0]
    if name not in columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def legacy_to_v2(status):
    mapping = {
        "candidate": ("candidate", "unverified"),
        "confirmed": ("active", "verified"),
        "needs_review": ("candidate", "needs_review"),
        "conflict": ("active", "conflict"),
        "superseded": ("superseded", "verified"),
        "stale": ("archived", "needs_review"),
        "rejected": ("quarantined", "unverified"),
    }
    return mapping.get(status, ("candidate", "unverified"))


def v2_to_legacy(lifecycle, review_state):
    if lifecycle == "superseded": return "superseded"
    if lifecycle == "quarantined": return "rejected"
    if lifecycle == "archived": return "stale"
    if review_state == "conflict": return "conflict"
    if review_state == "needs_review": return "needs_review"
    if lifecycle == "active" and review_state == "verified": return "confirmed"
    return "candidate"


def migrate_v2(con):
    """Idempotent, non-destructive v1 -> v2 migration."""
    con.executescript(V2_SCHEMA)
    add_column(con, "memories", "lifecycle TEXT")
    add_column(con, "memories", "review_state TEXT")
    add_column(con, "memories", "scope TEXT")
    add_column(con, "memories", "scope_ref TEXT")

    for r in con.execute("SELECT id,status,lifecycle,review_state,scope FROM memories").fetchall():
        lifecycle, review = legacy_to_v2(r["status"])
        con.execute(
            "UPDATE memories SET lifecycle=COALESCE(lifecycle,?),review_state=COALESCE(review_state,?),scope=COALESCE(scope,'global') WHERE id=?",
            (lifecycle, review, r["id"]),
        )

    # Backfill legacy source fields into first-class evidence exactly once.
    rows = con.execute("""
        SELECT id,source_agent,source_type,source_pointer,source_hash,evidence_group,confidence
        FROM memories
        WHERE source_agent IS NOT NULL OR source_type IS NOT NULL OR source_pointer IS NOT NULL OR source_hash IS NOT NULL
    """).fetchall()
    ts = stamp()
    for r in rows:
        sh = r["source_hash"] or digest((r["source_pointer"] or "") + "|" + (r["source_agent"] or ""))
        con.execute("""
            INSERT OR IGNORE INTO evidence(
              id,memory_id,raw_source_id,source_agent,source_type,source_pointer,
              source_hash,evidence_group,excerpt,confidence,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, (new_id("ev_"), r["id"], None, r["source_agent"], r["source_type"],
              r["source_pointer"], sh, r["evidence_group"], None, r["confidence"], ts))
    con.execute("INSERT OR REPLACE INTO meta VALUES('schema_version','2')")


def connect(home):
    home.mkdir(parents=True, exist_ok=True)
    (home / "raw").mkdir(exist_ok=True)
    con = sqlite3.connect(home / "memory.db")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(BASE_SCHEMA)
    migrate_v2(con)
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, statement)")
        con.execute("INSERT OR REPLACE INTO meta VALUES('fts5','1')")
    except sqlite3.OperationalError:
        con.execute("INSERT OR REPLACE INTO meta VALUES('fts5','0')")
    return con


def fts_enabled(con):
    row = con.execute("SELECT value FROM meta WHERE key='fts5'").fetchone()
    return bool(row and row[0] == "1")


def register_raw_source(con, *, agent, source_type, pointer, content_hash, evidence_group=None, snapshot=None, extraction_state="cold"):
    old = con.execute("SELECT id FROM raw_sources WHERE content_hash=? AND source_pointer IS ?", (content_hash, pointer)).fetchone()
    if old: return old["id"]
    rid = new_id("raw_")
    con.execute("""
      INSERT INTO raw_sources(id,source_agent,source_type,source_pointer,content_hash,evidence_group,local_snapshot,extraction_state,captured_at)
      VALUES(?,?,?,?,?,?,?,?,?)
    """, (rid, agent, source_type, pointer, content_hash, evidence_group, snapshot, extraction_state, stamp()))
    return rid


def add_evidence(con, memory_id, *, raw_source_id=None, source_agent=None, source_type=None,
                 source_pointer=None, source_hash=None, evidence_group=None, excerpt=None, confidence=None):
    if not any((raw_source_id, source_agent, source_type, source_pointer, source_hash, evidence_group, excerpt)):
        return None
    source_hash = source_hash or digest((source_pointer or "") + "|" + (source_agent or "") + "|" + (excerpt or ""))
    eid = new_id("ev_")
    con.execute("""
      INSERT OR IGNORE INTO evidence(id,memory_id,raw_source_id,source_agent,source_type,source_pointer,
        source_hash,evidence_group,excerpt,confidence,created_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)
    """, (eid, memory_id, raw_source_id, source_agent, source_type, source_pointer,
          source_hash, evidence_group, excerpt, confidence, stamp()))
    row = con.execute("SELECT id FROM evidence WHERE memory_id=? AND source_hash=? AND source_pointer IS ?",
                      (memory_id, source_hash, source_pointer)).fetchone()
    return row["id"] if row else eid


def cmd_init(args):
    home = root(args)
    existed = (home / "memory.db").exists()
    with connect(home) as con:
        fts = fts_enabled(con)
        version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
    emit_event(home, "store_opened" if existed else "store_initialized", schema_version=int(version), fts5=fts)
    print(f"{'Opened' if existed else 'Initialized'}: {home}")
    print(f"Schema: v{version}")
    print(f"SQLite FTS5: {'yes' if fts else 'no; LIKE fallback'}")


def insert_memory(args, quiet=False, raw_source_id=None):
    home, statement = root(args), args.statement.strip()
    if not statement: raise SystemExit("statement must not be empty")
    if not 0 <= args.confidence <= 1: raise SystemExit("confidence must be 0..1")
    nhash, ts = digest(norm(statement)), stamp()
    lifecycle = getattr(args, "lifecycle", None)
    review_state = getattr(args, "review_state", None)
    if not lifecycle or not review_state:
        lifecycle, review_state = legacy_to_v2(args.status)
    scope = getattr(args, "scope", None) or "global"
    scope_ref = getattr(args, "scope_ref", None)
    legacy_status = v2_to_legacy(lifecycle, review_state)

    with connect(home) as con:
        old = con.execute("SELECT id,status,statement FROM memories WHERE normalized_hash=? LIMIT 1", (nhash,)).fetchone()
        if old:
            add_evidence(con, old["id"], raw_source_id=raw_source_id, source_agent=args.source_agent,
                         source_type=args.source_type, source_pointer=args.source_pointer,
                         source_hash=args.source_hash, evidence_group=args.evidence_group,
                         excerpt=statement, confidence=args.confidence)
            if not quiet: print(f"Duplicate: {old['id']} [{old['status']}] {old['statement']} (evidence merged)")
            return old["id"], False

        mid = new_id("mem_")
        con.execute("""INSERT INTO memories(
          id,statement,normalized_hash,type,status,confidence,context_quality,source_agent,source_type,
          source_pointer,source_hash,evidence_group,valid_from,valid_until,superseded_by,created_at,updated_at,
          lifecycle,review_state,scope,scope_ref
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
          mid, statement, nhash, args.type, legacy_status, args.confidence, args.context_quality,
          args.source_agent, args.source_type, args.source_pointer, args.source_hash, args.evidence_group,
          args.valid_from, args.valid_until, None, ts, ts, lifecycle, review_state, scope, scope_ref))
        if fts_enabled(con): con.execute("INSERT INTO memory_fts(id,statement) VALUES(?,?)", (mid, statement))
        add_evidence(con, mid, raw_source_id=raw_source_id, source_agent=args.source_agent,
                     source_type=args.source_type, source_pointer=args.source_pointer,
                     source_hash=args.source_hash, evidence_group=args.evidence_group,
                     excerpt=statement, confidence=args.confidence)
        if args.conflicts_with:
            if not con.execute("SELECT 1 FROM memories WHERE id=?", (args.conflicts_with,)).fetchone():
                raise SystemExit(f"memory not found: {args.conflicts_with}")
            for a, b in ((mid, args.conflicts_with), (args.conflicts_with, mid)):
                con.execute("INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)", (a, "conflicts_with", b, ts))
            con.execute("UPDATE memories SET status='conflict',review_state='conflict',updated_at=? WHERE id IN (?,?)", (ts, mid, args.conflicts_with))
            legacy_status, review_state = "conflict", "conflict"
    emit_event(home, "memory_created", id=mid, status=legacy_status, lifecycle=lifecycle,
               review_state=review_state, type=args.type, scope=scope)
    if not quiet: print(f"Added: {mid} [{legacy_status}] {statement}")
    return mid, True


def words(q): return [x for x in re.findall(r"[\w가-힣.-]+", q.lower()) if len(x) > 1]


def cmd_recall(args):
    home = root(args)
    if not (home / "memory.db").exists(): raise SystemExit("memory store is not initialized; run init")
    terms = words(args.query)
    if not terms: raise SystemExit("query needs at least one searchable term")
    limit = max(1, min(args.limit, 50))
    with connect(home) as con:
        clauses = ["m.lifecycle != 'quarantined'"]
        params = []
        if not args.include_superseded: clauses.append("m.lifecycle != 'superseded'")
        if not args.include_rejected: clauses.append("m.lifecycle != 'quarantined'")
        if args.type: clauses.append("m.type=?"); params.append(args.type)
        if args.scope: clauses.append("m.scope=?"); params.append(args.scope)
        if args.scope_ref: clauses.append("m.scope_ref=?"); params.append(args.scope_ref)
        filt = " AND ".join(clauses)
        rows = []
        if fts_enabled(con):
            match = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
            try:
                rows = con.execute(f"""SELECT m.*,bm25(memory_fts) rank FROM memory_fts
                  JOIN memories m ON m.id=memory_fts.id WHERE memory_fts MATCH ? AND {filt}
                  ORDER BY rank,m.confidence DESC LIMIT ?""", [match, *params, limit]).fetchall()
            except sqlite3.OperationalError: rows = []
        if not rows:
            likes = " OR ".join("lower(m.statement) LIKE ?" for _ in terms)
            rows = con.execute(f"SELECT m.*,0 rank FROM memories m WHERE ({likes}) AND {filt} ORDER BY confidence DESC,updated_at DESC LIMIT ?",
                               [*[f"%{t}%" for t in terms], *params, limit]).fetchall()
        pack = []
        for r in rows:
            rels = [dict(x) for x in con.execute("SELECT relation,to_id FROM relations WHERE from_id=?", (r["id"],))]
            evs = [dict(x) for x in con.execute("""SELECT id,raw_source_id,source_agent,source_type,source_pointer,
                       source_hash,evidence_group,confidence FROM evidence WHERE memory_id=? ORDER BY created_at LIMIT 8""", (r["id"],))]
            pack.append({"id": r["id"], "statement": r["statement"], "type": r["type"],
                         "status": r["status"], "lifecycle": r["lifecycle"], "review_state": r["review_state"],
                         "confidence": r["confidence"], "context_quality": r["context_quality"],
                         "scope": r["scope"], "scope_ref": r["scope_ref"],
                         "source": {"agent": r["source_agent"], "type": r["source_type"], "pointer": r["source_pointer"], "evidence_group": r["evidence_group"]},
                         "evidence": evs, "valid_from": r["valid_from"], "valid_until": r["valid_until"], "relations": rels})
    if args.json: print(json.dumps({"query": args.query, "count": len(pack), "memories": pack}, ensure_ascii=False, indent=2))
    elif not pack: print("No relevant memory found.")
    else:
        print(f"Context pack: {len(pack)} memory(s)")
        for m in pack:
            warn = " !" if m["review_state"] in ("needs_review", "conflict") else ""
            print(f"- {m['id']} [{m['lifecycle']}/{m['review_state']}{warn}, {m['confidence']:.2f}, {m['type']}, {m['scope']}] {m['statement']}")
            if m["evidence"]: print(f"  evidence: {len(m['evidence'])}")


def cmd_status(args):
    home = root(args)
    if not (home / "memory.db").exists(): print(f"Not initialized: {home}"); return
    with connect(home) as con:
        version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        total = con.execute("SELECT count(*) FROM memories").fetchone()[0]
        evidence = con.execute("SELECT count(*) FROM evidence").fetchone()[0]
        raw = con.execute("SELECT count(*) FROM raw_sources").fetchone()[0]
        grouped = con.execute("SELECT lifecycle,review_state,count(*) n FROM memories GROUP BY lifecycle,review_state ORDER BY lifecycle,review_state").fetchall()
        conflicts = con.execute("SELECT count(*) FROM relations WHERE relation='conflicts_with'").fetchone()[0] // 2
        print(f"Home: {home}\nSchema: v{version}\nMemories: {total}\nEvidence: {evidence}\nRaw sources: {raw}\nFTS5: {'yes' if fts_enabled(con) else 'no'}\nConflicts: {conflicts}")
        if grouped: print("Governance: " + ", ".join(f"{r['lifecycle']}/{r['review_state']}={r['n']}" for r in grouped))


def cmd_inspect(args):
    with connect(root(args)) as con:
        r = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
        if not r: raise SystemExit(f"memory not found: {args.id}")
        data = dict(r)
        data["relations"] = [dict(x) for x in con.execute("SELECT relation,to_id,created_at FROM relations WHERE from_id=?", (args.id,))]
        data["evidence"] = [dict(x) for x in con.execute("SELECT * FROM evidence WHERE memory_id=? ORDER BY created_at", (args.id,))]
        print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_resolve(args):
    home, ts = root(args), stamp()
    with connect(home) as con:
        r = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
        if not r: raise SystemExit(f"memory not found: {args.id}")
        if args.superseded_by and not con.execute("SELECT 1 FROM memories WHERE id=?", (args.superseded_by,)).fetchone():
            raise SystemExit(f"memory not found: {args.superseded_by}")
        lifecycle = args.lifecycle or legacy_to_v2(args.status or r["status"])[0]
        review_state = args.review_state or legacy_to_v2(args.status or r["status"])[1]
        if args.superseded_by: lifecycle = "superseded"
        legacy = v2_to_legacy(lifecycle, review_state)
        con.execute("UPDATE memories SET status=?,lifecycle=?,review_state=?,superseded_by=?,updated_at=? WHERE id=?",
                    (legacy, lifecycle, review_state, args.superseded_by, ts, args.id))
        if args.superseded_by:
            con.execute("INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)", (args.id, "superseded_by", args.superseded_by, ts))
    emit_event(home, "memory_resolved", id=args.id, lifecycle=lifecycle, review_state=review_state, superseded_by=args.superseded_by)
    print(f"Resolved: {args.id} -> {lifecycle}/{review_state}")


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
            else: out.extend(b[i:i+size] for i in range(0, len(b), size)); buf = ""
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
    if not unique: print("No accessible L1 text sources discovered. Use --source PATH."); return
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
        with connect(home) as con:
            raw_id = register_raw_source(con, agent=agent, source_type="l1_file", pointer=str(path), content_hash=shash,
                                         evidence_group=f"file:{shash}", snapshot=str(rawcopy), extraction_state="indexed")
        added = 0
        for i, part in enumerate(parts, 1):
            ns = argparse.Namespace(home=str(home), statement=part, type="observation", status="needs_review", confidence=.60,
                context_quality="partial", source_agent=agent, source_type="l1_file", source_pointer=f"{path}#chunk-{i}",
                source_hash=shash, evidence_group=f"file:{shash}", valid_from=None, valid_until=None, conflicts_with=None,
                lifecycle="candidate", review_state="needs_review", scope=args.scope or "global", scope_ref=args.scope_ref)
            _, fresh = insert_memory(ns, quiet=True, raw_source_id=raw_id); added += int(fresh)
        total += added
        emit_event(home, "l1_source_imported", raw_source_id=raw_id, source_agent=agent, source_pointer=str(path), source_hash=shash, added=added)
        print(f"Imported {agent}: {path} -> {added}/{len(parts)} new")
    print(f"{'Would examine' if args.dry_run else 'Done:'} {total} {'chunk(s)' if args.dry_run else 'new candidate(s)'}.")
    if not args.dry_run: print("L1 imports remain candidate/needs_review until deliberately promoted.")


def cmd_doctor(args):
    home = root(args)
    if not (home/"memory.db").exists(): print("[FAIL] memory.db missing"); raise SystemExit(1)
    errors = 0
    with connect(home) as con:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        version = con.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        print(f"[{'OK' if integrity == 'ok' else 'FAIL'}] sqlite integrity: {integrity}"); errors += integrity != "ok"
        print(f"[OK] schema: v{version}")
        dangling = con.execute("SELECT count(*) FROM relations r LEFT JOIN memories a ON a.id=r.from_id LEFT JOIN memories b ON b.id=r.to_id WHERE a.id IS NULL OR b.id IS NULL").fetchone()[0]
        print(f"[{'OK' if not dangling else 'FAIL'}] dangling relations: {dangling}"); errors += bool(dangling)
        de = con.execute("SELECT count(*) FROM evidence e LEFT JOIN memories m ON m.id=e.memory_id WHERE m.id IS NULL").fetchone()[0]
        print(f"[{'OK' if not de else 'FAIL'}] dangling evidence: {de}"); errors += bool(de)
        print(f"[OK] FTS5: {'enabled' if fts_enabled(con) else 'unavailable; LIKE fallback active'}")
    ev = home / "events.jsonl"
    print(f"[{'OK' if ev.exists() else 'WARN'}] event log: {ev}")
    if errors: raise SystemExit(1)


def parser():
    p = argparse.ArgumentParser(prog="memory-hub")
    p.add_argument("--home")
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("init"); q.set_defaults(fn=cmd_init)

    q = sub.add_parser("add"); q.add_argument("statement"); q.add_argument("--type", choices=TYPES, default="fact")
    q.add_argument("--status", choices=LEGACY_STATUSES, default="candidate"); q.add_argument("--lifecycle", choices=LIFECYCLES)
    q.add_argument("--review-state", choices=REVIEW_STATES); q.add_argument("--confidence", type=float, default=.7)
    q.add_argument("--context-quality", choices=QUALITIES, default="partial"); q.add_argument("--scope", choices=SCOPES, default="global"); q.add_argument("--scope-ref")
    q.add_argument("--source-agent"); q.add_argument("--source-type"); q.add_argument("--source-pointer"); q.add_argument("--source-hash"); q.add_argument("--evidence-group")
    q.add_argument("--valid-from"); q.add_argument("--valid-until"); q.add_argument("--conflicts-with"); q.set_defaults(fn=lambda a: insert_memory(a))

    q = sub.add_parser("recall"); q.add_argument("query"); q.add_argument("--limit", type=int, default=5); q.add_argument("--json", action="store_true")
    q.add_argument("--include-superseded", action="store_true"); q.add_argument("--include-rejected", action="store_true")
    q.add_argument("--type", choices=TYPES); q.add_argument("--scope", choices=SCOPES); q.add_argument("--scope-ref"); q.set_defaults(fn=cmd_recall)

    q = sub.add_parser("status"); q.set_defaults(fn=cmd_status)
    q = sub.add_parser("inspect"); q.add_argument("id"); q.set_defaults(fn=cmd_inspect)
    q = sub.add_parser("resolve"); q.add_argument("id"); q.add_argument("--status", choices=LEGACY_STATUSES); q.add_argument("--lifecycle", choices=LIFECYCLES); q.add_argument("--review-state", choices=REVIEW_STATES); q.add_argument("--superseded-by"); q.set_defaults(fn=cmd_resolve)
    q = sub.add_parser("import-l1"); q.add_argument("--source", action="append"); q.add_argument("--source-agent"); q.add_argument("--dry-run", action="store_true"); q.add_argument("--scope", choices=SCOPES); q.add_argument("--scope-ref"); q.set_defaults(fn=cmd_import)
    q = sub.add_parser("doctor"); q.set_defaults(fn=cmd_doctor)
    return p


def main():
    args = parser().parse_args()
    result = args.fn(args)
    return 0 if result is None else result


if __name__ == "__main__": raise SystemExit(main())
