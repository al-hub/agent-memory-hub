from __future__ import annotations

import sqlite3
from pathlib import Path

from memcarry.domain.l1_source import L1SourceFingerprint, ProcessedL1SourceState


class SQLiteL1SourceStateStore:
    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._db_path)
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS l1_source_state (
                source_id TEXT PRIMARY KEY,
                repository_id TEXT,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                digest TEXT,
                cursor TEXT,
                complete INTEGER NOT NULL CHECK (complete IN (0, 1))
            )
            """
        )
        return con

    def load(self, source_id: str) -> ProcessedL1SourceState | None:
        con = self._connect()
        try:
            row = con.execute(
                """
                SELECT repository_id, size, mtime_ns, digest, cursor, complete
                FROM l1_source_state
                WHERE source_id=?
                """,
                (source_id,),
            ).fetchone()
            if row is None:
                return None
            repository_id, size, mtime_ns, digest, cursor, complete = row
            return ProcessedL1SourceState(
                fingerprint=L1SourceFingerprint(
                    source_id=source_id,
                    size=size,
                    mtime_ns=mtime_ns,
                    digest=digest,
                    cursor=cursor,
                ),
                repository_id=repository_id,
                complete=bool(complete),
            )
        finally:
            con.close()

    def save(self, state: ProcessedL1SourceState) -> None:
        fp = state.fingerprint
        con = self._connect()
        try:
            con.execute(
                """
                INSERT INTO l1_source_state(
                    source_id, repository_id, size, mtime_ns, digest, cursor, complete
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    repository_id=excluded.repository_id,
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    digest=excluded.digest,
                    cursor=excluded.cursor,
                    complete=excluded.complete
                """,
                (
                    fp.source_id,
                    state.repository_id,
                    fp.size,
                    fp.mtime_ns,
                    fp.digest,
                    fp.cursor,
                    1 if state.complete else 0,
                ),
            )
            con.commit()
        finally:
            con.close()

    def count(self) -> int:
        con = self._connect()
        try:
            row = con.execute("SELECT COUNT(*) FROM l1_source_state").fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()
