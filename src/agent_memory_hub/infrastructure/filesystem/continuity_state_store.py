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

    def _read_all(self) -> dict[str, dict[str, str | bool | None]]:
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _decode(self, raw: object) -> StoredContinuityState | None:
        if not isinstance(raw, dict):
            return None
        return StoredContinuityState(
            session_id=raw.get("session_id"),
            head_sha=raw.get("head_sha"),
            agent=raw.get("agent"),
            branch=raw.get("branch"),
            checkout_id=raw.get("checkout_id"),
        )

    def load(self, repository_id: str, worktree_id: str | None) -> StoredContinuityState | None:
        return self._decode(self._read_all().get(self._key(repository_id, worktree_id)))

    def load_compatible_checkout(
        self,
        repository_id: str,
        checkout_id: str,
        head_sha: str,
        branch: str | None,
    ) -> StoredContinuityState | None:
        prefix = f"{repository_id}::"
        for key, raw in self._read_all().items():
            if not key.startswith(prefix) or not isinstance(raw, dict):
                continue
            candidate_checkout = raw.get("checkout_id")
            if not candidate_checkout or candidate_checkout == checkout_id:
                continue
            if raw.get("head_sha") != head_sha:
                continue
            candidate_branch = raw.get("branch")
            if branch and candidate_branch and candidate_branch != branch:
                continue
            return self._decode(raw)
        return None

    def save(self, repository_id: str, worktree_id: str | None, state: StoredContinuityState) -> None:
        data = self._read_all()
        data[self._key(repository_id, worktree_id)] = {
            "session_id": state.session_id,
            "head_sha": state.head_sha,
            "agent": state.agent,
            "branch": state.branch,
            "checkout_id": state.checkout_id,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)
