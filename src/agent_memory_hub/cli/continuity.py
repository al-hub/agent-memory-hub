from __future__ import annotations

import json
from pathlib import Path

from agent_memory_hub.application.context_projector import ContextProjector
from agent_memory_hub.application.continuity_context import ContinuityContextService
from agent_memory_hub.application.continuity_state_detector import ContinuityStateDetector
from agent_memory_hub.application.seamless_continuity import SeamlessContinuityService
from agent_memory_hub.continuity.gate import ContinuityGate
from agent_memory_hub.domain.continuity_state import ContinuityObservation
from agent_memory_hub.infrastructure.filesystem.continuity_state_store import JsonContinuityStateStore
from agent_memory_hub.infrastructure.git.repository_inspector import GitRepositoryInspector
from agent_memory_hub.infrastructure.sqlite.repository_knowledge import SQLiteRepositoryKnowledgeReader
from agent_memory_hub.infrastructure.sqlite.scope_index import ensure_single_index_scope_fts
from agent_memory_hub.infrastructure.sqlite.single_index_scope_retriever import (
    SingleIndexScopeSQLiteMemoryReader,
)


class ContinuityCommand:
    """Thin CLI adapter around the seamless continuity application service."""

    def __init__(self, repository_inspector, seamless_service):
        self._repository_inspector = repository_inspector
        self._seamless_service = seamless_service

    def _payload(self, result) -> dict:
        pack = result.context.pack
        return {
            "mode": result.context.decision.mode.value,
            "reason": result.context.decision.reason,
            "state": {
                "repository_known": result.state.repository_known,
                "session_reset": result.state.session_reset,
                "session_has_context": result.state.session_has_context,
                "stale_head": result.state.stale_head,
                "agent_changed": result.state.agent_changed,
                "previous_agent": result.state.previous_agent,
                "current_agent": result.state.current_agent,
            },
            "estimated_tokens": pack.estimated_tokens if pack else 0,
            "token_budget": pack.token_budget if pack else 0,
            "truncated": pack.truncated if pack else False,
            "items": [
                {
                    "memory_id": item.memory_id,
                    "type": item.memory_type,
                    "scope": item.scope,
                    "review_state": item.review_state,
                    "confidence": item.confidence,
                    "statement": item.statement,
                    "warning": item.warning,
                }
                for item in (pack.items if pack else ())
            ],
        }

    def _render_text(self, payload: dict) -> str:
        lines = [
            f"mode: {payload['mode']}",
            f"reason: {payload['reason']}",
        ]
        state = payload["state"]
        flags = [
            name
            for name in ("repository_known", "session_reset", "stale_head", "agent_changed")
            if state[name]
        ]
        if flags:
            lines.append("state: " + ", ".join(flags))
        if not payload["items"]:
            return "\n".join(lines)

        lines.append(
            f"context: {payload['estimated_tokens']}/{payload['token_budget']} estimated tokens"
            + (" (truncated)" if payload["truncated"] else "")
        )
        for item in payload["items"]:
            prefix = f"- [{item['type']}/{item['scope']}/{item['review_state']}]"
            lines.append(f"{prefix} {item['statement']}")
            if item["warning"]:
                lines.append(f"  ! {item['warning']}")
        return "\n".join(lines)

    def run(
        self,
        *,
        message: str,
        cwd: str,
        session_id: str | None,
        session_has_context: bool,
        token_budget: int,
        json_output: bool,
        session_source: str | None = None,
        agent: str | None = None,
    ) -> str:
        # token_budget is accepted here so all entry points share one stable CLI
        # contract. The real composition root configures the service with it.
        _ = token_budget
        context = self._repository_inspector.inspect(cwd)
        observation = ContinuityObservation(
            message=message,
            context=context,
            session_id=session_id,
            session_has_context=session_has_context,
            session_source=session_source,
            agent=agent,
        )
        result = self._seamless_service.handle(observation)
        payload = self._payload(result)
        if json_output:
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return self._render_text(payload)


def build_continuity_command(home: str | Path, *, token_budget: int = 1000) -> ContinuityCommand:
    """Compose local Git + SQLite + checkpoint adapters into one CLI command."""
    home = Path(home).expanduser()
    db_path = home / "memory.db"
    state_path = home / "continuity-state.json"

    # Index migration is rebuildable and fail-safe. Existing/missing stores remain
    # readable through the single-index reader's broad/LIKE fallback.
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
