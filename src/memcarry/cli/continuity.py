from __future__ import annotations

from pathlib import Path

from memcarry.application.context_projector import ContextProjector
from memcarry.application.continuity_context import ContinuityContextService
from memcarry.application.continuity_state_detector import ContinuityStateDetector
from memcarry.application.seamless_continuity import SeamlessContinuityService
from memcarry.cli.continuity_command import ContinuityCommand
from memcarry.continuity.gate import ContinuityGate
from memcarry.infrastructure.filesystem.continuity_state_store import JsonContinuityStateStore
from memcarry.infrastructure.git.repository_inspector import GitRepositoryInspector
from memcarry.infrastructure.sqlite.repository_knowledge import SQLiteRepositoryKnowledgeReader
from memcarry.infrastructure.sqlite.scope_index import ensure_single_index_scope_fts
from memcarry.infrastructure.sqlite.single_index_scope_retriever import (
    SingleIndexScopeSQLiteMemoryReader,
)


def build_continuity_command(home: str | Path, *, token_budget: int = 1000) -> ContinuityCommand:
    """Compose prompt-facing Git + scope-first SQLite + checkpoint adapters."""
    home = Path(home).expanduser()
    db_path = home / "memory.db"
    state_path = home / "continuity-state.json"

    # Prompt recall uses the scope-aware single index. Migration is rebuildable
    # and fail-safe, with broad/LIKE fallback if the store is incompatible.
    ensure_single_index_scope_fts(db_path)
    memory_reader = SingleIndexScopeSQLiteMemoryReader(db_path)
    knowledge_reader = SQLiteRepositoryKnowledgeReader(db_path)
    state_store = JsonContinuityStateStore(state_path)
    state_detector = ContinuityStateDetector(knowledge_reader, state_store)
    context_service = ContinuityContextService(
        ContinuityGate(),
        memory_reader,
        ContextProjector(),
        token_budget=token_budget,
    )
    seamless = SeamlessContinuityService(state_detector, context_service)
    return ContinuityCommand(GitRepositoryInspector(), seamless)
