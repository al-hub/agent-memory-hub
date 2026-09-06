from __future__ import annotations

from pathlib import Path

from agent_memory_hub.application.context_projector import ContextProjector
from agent_memory_hub.application.continuity_context import ContinuityContextService
from agent_memory_hub.application.continuity_state_detector import ContinuityStateDetector
from agent_memory_hub.application.seamless_continuity import SeamlessContinuityService
from agent_memory_hub.cli.continuity_command import ContinuityCommand
from agent_memory_hub.continuity.gate import ContinuityGate
from agent_memory_hub.infrastructure.filesystem.continuity_state_store import JsonContinuityStateStore
from agent_memory_hub.infrastructure.git.repository_inspector import GitRepositoryInspector
from agent_memory_hub.infrastructure.sqlite.repository_knowledge import SQLiteRepositoryKnowledgeReader
from agent_memory_hub.infrastructure.sqlite.retriever import SQLiteMemoryReader


def build_session_start_command(home: str | Path, *, token_budget: int = 1000) -> ContinuityCommand:
    """Compose the SessionStart path without prompt-only scope-index imports.

    SessionStart has an empty lexical query by design, so it uses bounded visible-
    scope browse directly from `memories`. Prompt-facing continuity keeps the
    single-index scope-first FTS path in `cli.continuity`.
    """
    home = Path(home).expanduser()
    db_path = home / "memory.db"
    state_path = home / "continuity-state.json"

    memory_reader = SQLiteMemoryReader(db_path)
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
