from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from agent_memory_hub.application.scope_resolver import ScopeResolver
from agent_memory_hub.application.scope_storage import scope_storage_ref
from agent_memory_hub.domain.recall import MemoryCandidate, RecallQuery
from agent_memory_hub.infrastructure.sqlite.retriever import SQLiteMemoryReader
from agent_memory_hub.infrastructure.sqlite.scope_key import scope_fts_token


class ScopeFirstSQLiteMemoryReader:
    """FTS reader that intersects scope postings before statement postings.

    The default experimental layout uses `memory_fts_scoped`. A compatible
    single-index layout can reuse this implementation by selecting `memory_fts`
    when that table contains a searchable `scope_key` column.

    If the requested scoped FTS layout is unavailable or incompatible, recall
    falls back to the existing broad reader so migrations remain fail-safe.
    """

    def __init__(
        self,
        db_path: str | Path,
        scope_resolver: ScopeResolver | None = None,
        *,
        table_name: str = "memory_fts_scoped",
    ):
        if table_name not in {"memory_fts_scoped", "memory_fts"}:
            raise ValueError("unsupported scoped FTS table")
        self._db_path = Path(db_path)
        self._scope_resolver = scope_resolver or ScopeResolver()
        self._fallback = SQLiteMemoryReader(self._db_path, self._scope_resolver)
        self._table_name = table_name

    def _terms(self, text: str) -> list[str]:
        return [x for x in re.findall(r"[\w가-힣.-]+", text.lower()) if len(x) > 1]

    def _supports_scope_key(self, con: sqlite3.Connection) -> bool:
        try:
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (self._table_name,),
            ).fetchone()
            if not exists:
                return False
            columns = {
                row[1]
                for row in con.execute(f"PRAGMA table_info({self._table_name})").fetchall()
            }
            return {"id", "statement", "scope_key"}.issubset(columns)
        except sqlite3.OperationalError:
            return False

    def recall(self, query: RecallQuery) -> list[MemoryCandidate]:
        terms = self._terms(query.text)
        if not terms:
            return self._fallback.recall(query)
        if not self._db_path.exists():
            return []

        resolved = self._scope_resolver.resolve(query.context)
        scope_pairs = [
            (scope.level.value, scope_storage_ref(scope), idx)
            for idx, scope in enumerate(resolved)
        ]
        if not scope_pairs:
            return self._fallback.recall(query)

        limit = max(1, min(query.limit, 50))
        scope_tokens = [scope_fts_token(level, ref) for level, ref, _ in scope_pairs]
        scope_match = " OR ".join(f'"{token}"' for token in scope_tokens)
        term_match = " OR ".join('"' + term.replace('"', '') + '"' for term in terms)
        match = f"scope_key:({scope_match}) AND statement:({term_match})"

        scope_sql: list[str] = []
        scope_params: list[object] = []
        rank_case: list[str] = []
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

        clauses = [
            "m.lifecycle NOT IN ('quarantined','superseded')",
            f"({' OR '.join(scope_sql)})",
        ]
        params: list[object] = list(scope_params)
        if query.memory_type:
            clauses.append("m.type=?")
            params.append(query.memory_type)
        where = " AND ".join(clauses)
        scope_rank_expr = "CASE " + " ".join(rank_case) + " ELSE 999 END"
        table = self._table_name

        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        try:
            try:
                if not self._supports_scope_key(con):
                    return self._fallback.recall(query)

                sql = f"""
                    SELECT m.*, bm25({table}, 0.0, 1.0, 0.0) AS lexical_rank,
                           {scope_rank_expr} AS scope_rank
                    FROM {table}
                    JOIN memories m ON m.id={table}.id
                    WHERE {table} MATCH ? AND {where}
                    ORDER BY scope_rank ASC, lexical_rank ASC, m.confidence DESC
                    LIMIT ?
                """
                rows = con.execute(
                    sql,
                    [*rank_params, match, *params, limit],
                ).fetchall()
            except sqlite3.OperationalError:
                return self._fallback.recall(query)

            return [
                MemoryCandidate(
                    id=row["id"],
                    statement=row["statement"],
                    memory_type=row["type"],
                    lifecycle=row["lifecycle"],
                    review_state=row["review_state"],
                    confidence=float(row["confidence"]),
                    scope=row["scope"],
                    scope_ref=row["scope_ref"],
                    lexical_rank=float(row["lexical_rank"]),
                    scope_rank=int(row["scope_rank"]),
                )
                for row in rows
            ]
        finally:
            con.close()
