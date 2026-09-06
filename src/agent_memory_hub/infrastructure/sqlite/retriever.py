from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from agent_memory_hub.application.scope_resolver import ScopeResolver
from agent_memory_hub.application.scope_storage import scope_storage_ref
from agent_memory_hub.domain.recall import MemoryCandidate, RecallQuery


class SQLiteMemoryReader:
    """Fast local retrieval using scope/type filters before lexical ranking."""

    def __init__(self, db_path: str | Path, scope_resolver: ScopeResolver | None = None):
        self._db_path = Path(db_path)
        self._scope_resolver = scope_resolver or ScopeResolver()

    def _terms(self, text: str) -> list[str]:
        return [x for x in re.findall(r"[\w가-힣.-]+", text.lower()) if len(x) > 1]

    def recall(self, query: RecallQuery) -> list[MemoryCandidate]:
        terms = self._terms(query.text)
        if not terms or not self._db_path.exists():
            return []

        resolved = self._scope_resolver.resolve(query.context)
        scope_pairs = [(scope.level.value, scope_storage_ref(scope), idx) for idx, scope in enumerate(resolved)]
        limit = max(1, min(query.limit, 50))

        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        try:
            try:
                table_exists = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memories'"
                ).fetchone()
            except sqlite3.OperationalError:
                return []
            if not table_exists:
                return []

            scope_sql = []
            scope_params: list[object] = []
            rank_case = []
            rank_params: list[object] = []
            for level, ref, idx in scope_pairs:
                if ref is None:
                    scope_sql.append("(m.scope=? AND m.scope_ref IS NULL)")
                    scope_params.append(level)
                    rank_case.append("WHEN m.scope=? AND m.scope_ref IS NULL THEN ?")
                    rank_params.extend([level, idx])
                else:
                    scope_sql.append("(m.scope=? AND m.scope_ref=?)")
                    scope_params.extend([level, ref])
                    rank_case.append("WHEN m.scope=? AND m.scope_ref=? THEN ?")
                    rank_params.extend([level, ref, idx])

            clauses = ["m.lifecycle NOT IN ('quarantined','superseded')", f"({' OR '.join(scope_sql)})"]
            params: list[object] = list(scope_params)
            if query.memory_type:
                clauses.append("m.type=?")
                params.append(query.memory_type)
            where = " AND ".join(clauses)
            scope_rank_expr = "CASE " + " ".join(rank_case) + " ELSE 999 END"

            rows: list[sqlite3.Row] = []
            try:
                fts_exists = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_fts'").fetchone()
                if fts_exists:
                    match = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
                    sql = f"""
                        SELECT m.*, bm25(memory_fts) AS lexical_rank,
                               {scope_rank_expr} AS scope_rank
                        FROM memory_fts
                        JOIN memories m ON m.id=memory_fts.id
                        WHERE memory_fts MATCH ? AND {where}
                        ORDER BY scope_rank ASC, lexical_rank ASC, m.confidence DESC
                        LIMIT ?
                    """
                    rows = con.execute(sql, [*rank_params, match, *params, limit]).fetchall()
            except sqlite3.OperationalError:
                rows = []

            if not rows:
                likes = " OR ".join("lower(m.statement) LIKE ?" for _ in terms)
                sql = f"""
                    SELECT m.*, 0.0 AS lexical_rank,
                           {scope_rank_expr} AS scope_rank
                    FROM memories m
                    WHERE ({likes}) AND {where}
                    ORDER BY scope_rank ASC, m.confidence DESC, m.updated_at DESC
                    LIMIT ?
                """
                try:
                    rows = con.execute(
                        sql,
                        [*rank_params, *[f"%{t}%" for t in terms], *params, limit],
                    ).fetchall()
                except sqlite3.OperationalError:
                    return []

            return [
                MemoryCandidate(
                    id=r["id"],
                    statement=r["statement"],
                    memory_type=r["type"],
                    lifecycle=r["lifecycle"],
                    review_state=r["review_state"],
                    confidence=float(r["confidence"]),
                    scope=r["scope"],
                    scope_ref=r["scope_ref"],
                    lexical_rank=float(r["lexical_rank"]),
                    scope_rank=int(r["scope_rank"]),
                )
                for r in rows
            ]
        finally:
            con.close()
