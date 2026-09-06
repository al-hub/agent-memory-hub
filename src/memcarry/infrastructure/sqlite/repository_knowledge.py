from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteRepositoryKnowledgeReader:
    """Answer whether governed L2 contains usable memory for a repository family."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)

    def has_repository(self, repository_id: str) -> bool:
        if not self._db_path.exists():
            return False
        con = sqlite3.connect(self._db_path)
        try:
            try:
                row = con.execute(
                    """
                    SELECT 1
                    FROM memories
                    WHERE lifecycle NOT IN ('quarantined')
                      AND (
                        (scope='repository' AND scope_ref=?)
                        OR (scope IN ('branch','worktree','task') AND scope_ref LIKE ?)
                      )
                    LIMIT 1
                    """,
                    (repository_id, repository_id + "::%"),
                ).fetchone()
            except sqlite3.OperationalError:
                return False
            return row is not None
        finally:
            con.close()
