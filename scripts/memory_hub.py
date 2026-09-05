#!/usr/bin/env python3
"""agent-memory-hub v0.1: local-first shared L2 memory CLI.

Python standard library only. SQLite FTS5 is used when available.
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
import textwrap
import time
import uuid
from pathlib import Path
from typing import Iterable

DEFAULT_HOME = Path(os.environ.get("AGENT_MEMORY_HUB_HOME", "~/.agent-memory-hub")).expanduser()
STATUSES = {
    "candidate", "confirmed", "needs_review", "conflict",
    "superseded", "stale", "rejected",
}
TYPES = {
    "fact", "preference", "decision", "constraint", "lesson", "mistake",
    "project_state", "hypothesis", "temporary", "observation",
}
QUALITIES = {"clear", "partial", "ambiguous"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    normalized_hash TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    context_quality TEXT NOT NULL,
    source_agent TEXT,
    source_type TEXT,
    source_pointer TEXT,
    source_hash TEXT,
    evidence_group TEXT,
    valid_from TEXT,
    valid_until TEXT,
    superseded_by TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_hash ON memories(normalized_hash);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(source_agent);
CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    to_id TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    UNIQUE(from_id, relation, to_id)
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def home_from(args) -> Path:
    return Path(getattr(args, "home", None) or DEFAULT_HOME).expanduser()


def db_path(home: Path) -> Path:
    return home / "memory.db"


def events_path(home: Path) -> Path:
    return home / "events.jsonl"


def now() -> int:
    return int(time.time())


def normalize_statement(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip().lower())
    return text


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def memory_id() -> str:
    return "mem_" + uuid.uuid4().hex[:12]


def connect(home: Path, create: bool = True) -> sqlite3.Connection:
    if create:
        home.mkdir(parents=True, exist_ok=True)
        (home / "raw").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path(home))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    ensure_fts(con)
    return con


def ensure_fts(con: sqlite3.Connection) -> bool:
    try:
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, statement)")
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts5','1')")
        return True
    except sqlite3.OperationalError:
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('fts5','0')")
        return False


def has_fts(con: sqlite3.Connection) -> bool:
    row = con.execute("SELECT value FROM meta WHERE key='fts5'").fetchone()
    return bool(row and row[0] == "1")


def event(home: Path, kind: str, **payload) -> None:
    home.mkdir(parents=True, exist_ok=True)
    record = {"event": kind, "ts": now(), **payload}
    with events_path(home).open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def validate_choice(value: str, choices: set[str], label: str) -> str:
    if value not in choices:
        raise SystemExit(f"invalid {label}: {value}; choose from {', '.join(sorted(choices))}")
    return value


def init_store(args) -> None:
    home = home_from(args)
    with connect(home) as con:
        fts = has_fts(con)
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','1')")
    event(home, "store_initialized", schema_version=1, fts5=fts)
    print(f"Initialized: {home}")
    print(f"SQLite FTS5: {'yes' if fts else 'no (LIKE fallback)'}")


def add_memory(args, *, quiet: bool = False) -> str:
    home = home_from(args)
    statement = args.statement.strip()
    if not statement:
        raise SystemExit("statement must not be empty")
    mtype = validate_choice(args.type, TYPES, "type")
    status = validate_choice(args.status, STATUSES, "status")
    quality = validate_choice(args.context_quality, QUALITIES, "context quality")
    confidence = float(args.confidence)
    if not 0.0 <= confidence <= 1.0:
        raise SystemExit("confidence must be between 0 and 1")

    normalized = normalize_statement(statement)
    nhash = sha256_text(normalized)
    ts = now()

    with connect(home) as con:
        existing = con.execute(
            "SELECT id,status,statement FROM memories WHERE normalized_hash=? ORDER BY created_at LIMIT 1",
            (nhash,),
        ).fetchone()
        if existing:
            if not quiet:
                print(f"Duplicate: {existing['id']} [{existing['status']}] {existing['statement']}")
            return existing["id"]

        mid = memory_id()
        con.execute(
            """INSERT INTO memories(
                id,statement,normalized_hash,type,status,confidence,context_quality,
                source_agent,source_type,source_pointer,source_hash,evidence_group,
                valid_from,valid_until,superseded_by,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                mid, statement, nhash, mtype, status, confidence, quality,
                args.source_agent, args.source_type, args.source_pointer,
                args.source_hash, args.evidence_group, args.valid_from,
                args.valid_until, None, ts, ts,
            ),
        )
        if has_fts(con):
            con.execute("INSERT INTO memory_fts(id,statement) VALUES(?,?)", (mid, statement))

        if getattr(args, "conflicts_with", None):
            other = con.execute("SELECT id FROM memories WHERE id=?", (args.conflicts_with,)).fetchone()
            if not other:
                raise SystemExit(f"conflicting memory not found: {args.conflicts_with}")
            con.execute(
                "INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)",
                (mid, "conflicts_with", args.conflicts_with, ts),
            )
            con.execute(
                "INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)",
                (args.conflicts_with, "conflicts_with", mid, ts),
            )
            con.execute("UPDATE memories SET status='conflict',updated_at=? WHERE id IN (?,?)", (ts, mid, args.conflicts_with))
            status = "conflict"

    event(home, "memory_created", id=mid, type=mtype, status=status, source_agent=args.source_agent)
    if not quiet:
        print(f"Added: {mid} [{status}] {statement}")
    return mid


def tokenize_query(query: str) -> list[str]:
    return [t for t in re.findall(r"[\w가-힣.-]+", query.lower()) if len(t) > 1]


def recall(args) -> None:
    home = home_from(args)
    if not db_path(home).exists():
        raise SystemExit(f"memory store not initialized: {home}; run init first")
    query = args.query.strip()
    if not query:
        raise SystemExit("query must not be empty")
    limit = max(1, min(int(args.limit), 50))
    allowed_status = ["confirmed", "candidate", "needs_review", "conflict", "stale"]
    if args.include_superseded:
        allowed_status.append("superseded")
    if args.include_rejected:
        allowed_status.append("rejected")

    with connect(home) as con:
        placeholders = ",".join("?" for _ in allowed_status)
        rows = []
        if has_fts(con):
            terms = tokenize_query(query)
            if terms:
                match = " OR ".join(f'"{t.replace(chr(34), "")}"' for t in terms)
                sql = f"""
                    SELECT m.*, bm25(memory_fts) AS rank
                    FROM memory_fts JOIN memories m ON m.id=memory_fts.id
                    WHERE memory_fts MATCH ? AND m.status IN ({placeholders})
                    ORDER BY rank ASC, m.confidence DESC, m.updated_at DESC
                    LIMIT ?
                """
                try:
                    rows = con.execute(sql, [match, *allowed_status, limit]).fetchall()
                except sqlite3.OperationalError:
                    rows = []
        if not rows:
            terms = tokenize_query(query)
            where = " OR ".join("lower(statement) LIKE ?" for _ in terms) or "1=1"
            params = [f"%{t}%" for t in terms]
            sql = f"""
                SELECT m.*, 0.0 AS rank FROM memories m
                WHERE ({where}) AND m.status IN ({placeholders})
                ORDER BY m.confidence DESC, m.updated_at DESC
                LIMIT ?
            """
            rows = con.execute(sql, [*params, *allowed_status, limit]).fetchall()

        result = []
        for r in rows:
            rels = con.execute(
                "SELECT relation,to_id FROM relations WHERE from_id=? ORDER BY id", (r["id"],)
            ).fetchall()
            result.append({
                "id": r["id"],
                "statement": r["statement"],
                "type": r["type"],
                "status": r["status"],
                "confidence": r["confidence"],
                "context_quality": r["context_quality"],
                "source": {
                    "agent": r["source_agent"],
                    "type": r["source_type"],
                    "pointer": r["source_pointer"],
                    "evidence_group": r["evidence_group"],
                },
                "valid_from": r["valid_from"],
                "valid_until": r["valid_until"],
                "relations": [dict(x) for x in rels],
            })

    pack = {"query": query, "count": len(result), "memories": result}
    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
        return
    if not result:
        print("No relevant memory found.")
        return
    print(f"Context pack: {len(result)} memory(s)")
    for m in result:
        warning = " !" if m["status"] in {"needs_review", "conflict", "stale"} else ""
        print(f"- {m['id']} [{m['status']}{warning}, {m['confidence']:.2f}, {m['type']}] {m['statement']}")
        if m["source"]["pointer"]:
            print(f"  source: {m['source']['pointer']}")


def status_cmd(args) -> None:
    home = home_from(args)
    if not db_path(home).exists():
        print(f"Not initialized: {home}")
        return
    with connect(home) as con:
        total = con.execute("SELECT count(*) FROM memories").fetchone()[0]
        grouped = con.execute("SELECT status,count(*) n FROM memories GROUP BY status ORDER BY status").fetchall()
        agents = con.execute("SELECT coalesce(source_agent,'unknown') agent,count(*) n FROM memories GROUP BY agent ORDER BY n DESC").fetchall()
        conflicts = con.execute("SELECT count(*) FROM relations WHERE relation='conflicts_with'").fetchone()[0] // 2
        print(f"Home: {home}")
        print(f"Memories: {total}")
        print(f"FTS5: {'yes' if has_fts(con) else 'no'}")
        print(f"Conflicts: {conflicts}")
        if grouped:
            print("Status: " + ", ".join(f"{r['status']}={r['n']}" for r in grouped))
        if agents:
            print("Sources: " + ", ".join(f"{r['agent']}={r['n']}" for r in agents[:8]))


def inspect_cmd(args) -> None:
    home = home_from(args)
    with connect(home) as con:
        row = con.execute("SELECT * FROM memories WHERE id=?", (args.id,)).fetchone()
        if not row:
            raise SystemExit(f"memory not found: {args.id}")
        rels = con.execute("SELECT relation,to_id,created_at FROM relations WHERE from_id=?", (args.id,)).fetchall()
        data = dict(row)
        data["relations"] = [dict(r) for r in rels]
        print(json.dumps(data, ensure_ascii=False, indent=2))


def resolve_cmd(args) -> None:
    home = home_from(args)
    status = validate_choice(args.status, STATUSES, "status")
    ts = now()
    with connect(home) as con:
        row = con.execute("SELECT id FROM memories WHERE id=?", (args.id,)).fetchone()
        if not row:
            raise SystemExit(f"memory not found: {args.id}")
        if args.superseded_by:
            newer = con.execute("SELECT id FROM memories WHERE id=?", (args.superseded_by,)).fetchone()
            if not newer:
                raise SystemExit(f"superseding memory not found: {args.superseded_by}")
        con.execute(
            "UPDATE memories SET status=?,superseded_by=?,updated_at=? WHERE id=?",
            (status, args.superseded_by, ts, args.id),
        )
        if args.superseded_by:
            con.execute(
                "INSERT OR IGNORE INTO relations(from_id,relation,to_id,created_at) VALUES(?,?,?,?)",
                (args.id, "superseded_by", args.superseded_by, ts),
            )
    event(home, "memory_resolved", id=args.id, status=status, superseded_by=args.superseded_by)
    print(f"Resolved: {args.id} -> {status}")


def candidate_l1_paths() -> list[tuple[str, Path]]:
    h = Path.home()
    paths = [
        ("claude", h / ".claude" / "CLAUDE.md"),
        ("codex", h / ".codex" / "AGENTS.md"),
        ("gemini", h / ".gemini" / "GEMINI.md"),
        ("cursor", h / ".cursor" / "rules"),
        ("generic", Path.cwd() / "AGENTS.md"),
        ("generic", Path.cwd() / "CLAUDE.md"),
        ("generic", Path.cwd() / "GEMINI.md"),
    ]
    return paths


def split_text_chunks(text: str, max_chars: int = 1800) -> Iterable[str]:
    # Split markdown/text into useful reviewable chunks while retaining headings with bodies.
    blocks = re.split(r"\n(?=#{1,6}\s)|\n\s*\n", text.replace("\r\n", "\n"))
    buf = ""
    for raw in blocks:
        block = raw.strip()
        if not block:
            continue
        if len(buf) + len(block) + 2 <= max_chars:
            buf = f"{buf}\n\n{block}".strip()
        else:
            if buf:
                yield buf
            if len(block) <= max_chars:
                buf = block
            else:
                for i in range(0, len(block), max_chars):
                    yield block[i:i + max_chars].strip()
                buf = ""
    if buf:
        yield buf


def import_one(home: Path, agent: str, path: Path, dry_run: bool) -> tuple[int, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    shash = sha256_text(text)
    chunks = list(split_text_chunks(text))
    if dry_run:
        print(f"- {agent}: {path} ({len(chunks)} chunk(s))")
        return len(chunks), 0

    raw_dir = home / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_copy = raw_dir / f"{shash[:16]}-{path.name}"
    if not raw_copy.exists():
        shutil.copyfile(path, raw_copy)

    added = 0
    for idx, chunk in enumerate(chunks):
        ns = argparse.Namespace(
            home=str(home), statement=chunk, type="observation", status="needs_review",
            confidence=0.60, context_quality="partial", source_agent=agent,
            source_type="l1_file", source_pointer=f"{path}#chunk-{idx+1}",
            source_hash=shash, evidence_group=f"file:{shash}", valid_from=None,
            valid_until=None, conflicts_with=None,
        )
        before = None
        with connect(home) as con:
            before = con.execute("SELECT count(*) FROM memories").fetchone()[0]
        add_memory(ns, quiet=True)
        with connect(home) as con:
            after = con.execute("SELECT count(*) FROM memories").fetchone()[0]
        if after > before:
            added += 1
    event(home, "l1_source_imported", source_agent=agent, source_pointer=str(path), source_hash=shash, added=added)
    print(f"Imported {agent}: {path} -> {added}/{len(chunks)} new")
    return len(chunks), added


def import_l1(args) -> None:
    home = home_from(args)
    sources: list[tuple[str, Path]] = []
    for agent, path in candidate_l1_paths():
        if path.exists() and path.is_file():
            sources.append((agent, path.resolve()))
    for raw in args.source or []:
        p = Path(raw).expanduser().resolve()
        if p.is_file():
            sources.append((args.source_agent or "manual", p))
        elif p.is_dir():
            for child in sorted(p.glob("*.md")):
                sources.append((args.source_agent or "manual", child.resolve()))
        else:
            print(f"Skipping missing source: {p}", file=sys.stderr)

    # Deduplicate paths while preserving order.
    seen = set()
    unique = []
    for agent, p in sources:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append((agent, p))

    if not unique:
        print("No accessible L1 text sources discovered.")
        print("Use --source PATH to import an explicit file or directory.")
        return

    if args.dry_run:
        print("Discovered L1 sources (dry run):")
    total_chunks = total_added = 0
    for agent, p in unique:
        chunks, added = import_one(home, agent, p, args.dry_run)
        total_chunks += chunks
        total_added += added
    if args.dry_run:
        print(f"Would examine {total_chunks} chunk(s) from {len(unique)} source(s).")
    else:
        print(f"Done: {total_added} new memory candidate(s) from {len(unique)} source(s).")
        print("Imported L1 content is marked needs_review by design; promote only durable context.")


def doctor(args) -> None:
    home = home_from(args)
    errors = 0
    print(f"Home: {home}")
    if not db_path(home).exists():
        print("[FAIL] memory.db missing")
        raise SystemExit(1)
    try:
        with connect(home) as con:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            print(f"[{'OK' if integrity == 'ok' else 'FAIL'}] sqlite integrity: {integrity}")
            if integrity != "ok":
                errors += 1
            print(f"[OK] FTS5: {'enabled' if has_fts(con) else 'unavailable; LIKE fallback active'}")
            dangling = con.execute(
                """SELECT count(*) FROM relations r
                LEFT JOIN memories a ON a.id=r.from_id
                LEFT JOIN memories b ON b.id=r.to_id
                WHERE a.id IS NULL OR b.id IS NULL"""
            ).fetchone()[0]
            print(f"[{'OK' if dangling == 0 else 'FAIL'}] dangling relations: {dangling}")
            if dangling:
                errors += 1
            rows = con.execute("SELECT source_pointer FROM memories WHERE source_type='l1_file' AND source_pointer IS NOT NULL").fetchall()
            missing = 0
            for r in rows:
                pointer = r[0].split("#chunk-", 1)[0]
                if pointer and not Path(pointer).exists():
                    missing += 1
            print(f"[{'OK' if missing == 0 else 'WARN'}] imported source paths missing: {missing}")
    except sqlite3.Error as e:
        print(f"[FAIL] sqlite: {e}")
        errors += 1
    if events_path(home).exists():
        bad = 0
        for line in events_path(home).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad += 1
        print(f"[{'OK' if bad == 0 else 'FAIL'}] event log invalid lines: {bad}")
        errors += bool(bad)
    else:
        print("[WARN] event log not created yet")
    if errors:
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="memory-hub",
        description="Local-first shared L2 memory for AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          memory-hub init
          memory-hub import-l1 --dry-run
          memory-hub add "Use separate Rust repository" --type decision --status confirmed
          memory-hub recall "Rust repository"
        """),
    )
    p.add_argument("--home", help="storage directory (default: ~/.agent-memory-hub)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="initialize L2 storage")
    s.set_defaults(func=init_store)

    s = sub.add_parser("add", help="add one governed memory")
    s.add_argument("statement")
    s.add_argument("--type", default="fact", choices=sorted(TYPES))
    s.add_argument("--status", default="candidate", choices=sorted(STATUSES))
    s.add_argument("--confidence", type=float, default=0.70)
    s.add_argument("--context-quality", default="clear", choices=sorted(QUALITIES))
    s.add_argument("--source-agent")
    s.add_argument("--source-type", default="conversation")
    s.add_argument("--source-pointer")
    s.add_argument("--source-hash")
    s.add_argument("--evidence-group")
    s.add_argument("--valid-from")
    s.add_argument("--valid-until")
    s.add_argument("--conflicts-with")
    s.set_defaults(func=add_memory)

    s = sub.add_parser("recall", help="retrieve a compact context pack")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=8)
    s.add_argument("--include-superseded", action="store_true")
    s.add_argument("--include-rejected", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=recall)

    s = sub.add_parser("status", help="show memory store statistics")
    s.set_defaults(func=status_cmd)

    s = sub.add_parser("inspect", help="inspect one memory and provenance")
    s.add_argument("id")
    s.set_defaults(func=inspect_cmd)

    s = sub.add_parser("resolve", help="update memory governance state")
    s.add_argument("id")
    s.add_argument("--status", required=True, choices=sorted(STATUSES))
    s.add_argument("--superseded-by")
    s.set_defaults(func=resolve_cmd)

    s = sub.add_parser("import-l1", help="discover/import accessible L1 text memory")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--source", action="append", help="explicit file/directory; repeatable")
    s.add_argument("--source-agent", help="agent label for explicit --source")
    s.set_defaults(func=import_l1)

    s = sub.add_parser("doctor", help="validate DB, relations and event log")
    s.set_defaults(func=doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
