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
    """Experimental FTS reader that intersects scope postings before statement postings.

    `memory_fts_scoped` indexes two searchable columns: statement and scope_key.
    The scope key is a deterministic token derived from (scope, scope_ref), so the
    FTS engine can intersect visible scopes with lexical terms before joining the
    governed `memories` rows. Missing/unsupported scoped FTS falls back to the
    existing broad reader so the experiment is safe to deploy alongside v0.2.
    """

    def __init__(self, db_path: str | Path, scope_resolver: ScopeResolver | None = None):
        self._db_path = Path(db_path)
        self._scope_resolver = scope_resolver or ScopeResolver()
        self._fallback = SQLiteMemoryReader(self._db_path, self._scope_resolver)

    def _terms(self, text: str) -> list[str]:
        return [x for x in re.findall(r"[\w가-힣.-]+", text.lower()) if len(x) > 1]

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

        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        try:
            try:
                scoped_fts_exists = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_fts_scoped'"
                ).fetchone()
                if not scoped_fts_exists:
                    return self._fallback.recall(query)

                sql = f"""
                    SELECT m.*, bm25(memory_fts_scoped, 0.0, 1.0, 0.0) AS lexical_rank,
                           {scope_rank_expr} AS scope_rank
                    FROM memory_fts_scoped
                    JOIN memories m ON m.id=memory_fts_scoped.id
                    WHERE memory_fts_scoped MATCH ? AND {where}
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
