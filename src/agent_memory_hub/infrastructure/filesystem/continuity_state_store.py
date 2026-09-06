from __future__ import annotations

import json
from pathlib import Path

from agent_memory_hub.ports.continuity_state import StoredContinuityState


class JsonContinuityStateStore:
    """Tiny local continuity checkpoint store keyed by repository/worktree."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _key(self, repository_id: str, worktree_id: str | None) -> str:
        return f"{repository_id}::{worktree_id or '-'}"

    def _read_all(self) -> dict[str, dict[str, str | None]]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def load(self, repository_id: str, worktree_id: str | None) -> StoredContinuityState | None:
        raw = self._read_all().get(self._key(repository_id, worktree_id))
        if not isinstance(raw, dict):
            return None
        return StoredContinuityState(
            session_id=raw.get("session_id"),
            head_sha=raw.get("head_sha"),
            agent=raw.get("agent"),
        )

    def save(self, repository_id: str, worktree_id: str | None, state: StoredContinuityState) -> None:
        data = self._read_all()
        data[self._key(repository_id, worktree_id)] = {
            "session_id": state.session_id,
            "head_sha": state.head_sha,
            "agent": state.agent,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)
