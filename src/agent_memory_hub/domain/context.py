from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ScopeLevel(str, Enum):
    GLOBAL = "global"
    USER = "user"
    PROJECT = "project"
    REPOSITORY = "repository"
    WORKTREE = "worktree"
    BRANCH = "branch"
    TASK = "task"
    AGENT = "agent"
    SESSION = "session"


@dataclass(frozen=True, slots=True)
class RepositoryIdentity:
    canonical_id: str
    root: str
    common_dir: str
    remote: Optional[str] = None


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    repository: Optional[RepositoryIdentity] = None
    worktree_id: Optional[str] = None
    branch: Optional[str] = None
    head_sha: Optional[str] = None
    task: Optional[str] = None
