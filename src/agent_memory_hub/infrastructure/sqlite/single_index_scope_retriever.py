from __future__ import annotations

from pathlib import Path

from agent_memory_hub.application.scope_resolver import ScopeResolver
from agent_memory_hub.infrastructure.sqlite.scope_first_retriever import (
    ScopeFirstSQLiteMemoryReader,
)


class SingleIndexScopeSQLiteMemoryReader(ScopeFirstSQLiteMemoryReader):
    """Scope-first retrieval over the canonical `memory_fts` table.

    This candidate expects `memory_fts(id UNINDEXED, statement, scope_key)`.
    Legacy two-column FTS databases remain readable because the shared parent
    falls back to `SQLiteMemoryReader` when `scope_key` is absent.
    """

    def __init__(self, db_path: str | Path, scope_resolver: ScopeResolver | None = None):
        super().__init__(
            db_path,
            scope_resolver,
            table_name="memory_fts",
        )
