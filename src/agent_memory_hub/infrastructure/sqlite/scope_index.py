from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_memory_hub.infrastructure.sqlite.scope_key import scope_fts_token


_REQUIRED_MEMORY_COLUMNS = {"id", "statement", "scope", "scope_ref"}
_FTS_COLUMNS = {"id", "statement", "scope_key"}


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return bool(
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
    )


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _create_scope_fts(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE VIRTUAL TABLE memory_fts USING fts5("
        "id UNINDEXED, statement, scope_key)"
    )


def _rebuild_scope_fts(con: sqlite3.Connection) -> None:
    if _table_exists(con, "memory_fts"):
        con.execute("DROP TABLE memory_fts")
    _create_scope_fts(con)
    rows = con.execute(
        "SELECT rowid,id,statement,scope,scope_ref FROM memories ORDER BY rowid"
    ).fetchall()
    con.executemany(
        "INSERT INTO memory_fts(rowid,id,statement,scope_key) VALUES(?,?,?,?)",
        [
            (rowid, memory_id, statement, scope_fts_token(scope, scope_ref))
            for rowid, memory_id, statement, scope, scope_ref in rows
        ],
    )


def _install_dirty_tracking(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS scope_fts_dirty(
          memory_id TEXT PRIMARY KEY,
          fts_rowid INTEGER NOT NULL,
          deleted INTEGER NOT NULL DEFAULT 0
        );

        CREATE TRIGGER IF NOT EXISTS trg_scope_fts_dirty_insert
        AFTER INSERT ON memories
        BEGIN
          INSERT INTO scope_fts_dirty(memory_id,fts_rowid,deleted)
          VALUES(new.id,new.rowid,0)
          ON CONFLICT(memory_id) DO UPDATE SET
            fts_rowid=excluded.fts_rowid,
            deleted=0;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_scope_fts_dirty_update
        AFTER UPDATE OF id,statement,scope,scope_ref ON memories
        BEGIN
          INSERT INTO scope_fts_dirty(memory_id,fts_rowid,deleted)
          VALUES(new.id,new.rowid,0)
          ON CONFLICT(memory_id) DO UPDATE SET
            fts_rowid=excluded.fts_rowid,
            deleted=0;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_scope_fts_dirty_delete
        AFTER DELETE ON memories
        BEGIN
          INSERT INTO scope_fts_dirty(memory_id,fts_rowid,deleted)
          VALUES(old.id,old.rowid,1)
          ON CONFLICT(memory_id) DO UPDATE SET
            fts_rowid=excluded.fts_rowid,
            deleted=1;
        END;
        """
    )


def _repair_dirty_rows(con: sqlite3.Connection) -> None:
    dirty = con.execute(
        "SELECT memory_id,fts_rowid,deleted FROM scope_fts_dirty ORDER BY memory_id"
    ).fetchall()
    for memory_id, fts_rowid, deleted in dirty:
        # The legacy writer may have inserted a second row with an auto-assigned
        # FTS rowid and no scope_key. Delete by both rowid and id before repair.
        con.execute(
            "DELETE FROM memory_fts WHERE rowid=? OR id=?",
            (fts_rowid, memory_id),
        )
        if not deleted:
            current = con.execute(
                "SELECT rowid,id,statement,scope,scope_ref FROM memories WHERE id=?",
                (memory_id,),
            ).fetchone()
            if current:
                rowid, current_id, statement, scope, scope_ref = current
                con.execute("DELETE FROM memory_fts WHERE rowid=?", (rowid,))
                con.execute(
                    "INSERT INTO memory_fts(rowid,id,statement,scope_key) VALUES(?,?,?,?)",
                    (
                        rowid,
                        current_id,
                        statement,
                        scope_fts_token(scope, scope_ref),
                    ),
                )
        con.execute("DELETE FROM scope_fts_dirty WHERE memory_id=?", (memory_id,))


def ensure_single_index_scope_fts(db_path: str | Path) -> bool:
    """Ensure the canonical FTS uses one scope-aware index.

    The governed `memories` table is never rewritten. A legacy two-column FTS is
    rebuilt from canonical rows, then small triggers record only changed memory
    rowids. Subsequent calls repair those dirty rows before recall. If SQLite FTS5
    or the expected memory schema is unavailable, return False and let callers use
    their existing broad/LIKE fallback.
    """

    path = Path(db_path)
    if not path.exists():
        return False

    con = sqlite3.connect(path)
    try:
        try:
            if not _table_exists(con, "memories"):
                return False
            if not _REQUIRED_MEMORY_COLUMNS.issubset(_columns(con, "memories")):
                return False

            dirty_tracking_existed = _table_exists(con, "scope_fts_dirty")
            fts_exists = _table_exists(con, "memory_fts")
            fts_columns = _columns(con, "memory_fts") if fts_exists else set()
            needs_rebuild = not fts_exists or not _FTS_COLUMNS.issubset(fts_columns)

            # A pre-existing three-column experimental table without dirty-row
            # tracking is rebuilt once so rowids/tokens are canonicalized.
            if needs_rebuild or not dirty_tracking_existed:
                _rebuild_scope_fts(con)

            _install_dirty_tracking(con)
            _repair_dirty_rows(con)
            con.commit()
            return True
        except sqlite3.OperationalError:
            con.rollback()
            return False
    finally:
        con.close()
