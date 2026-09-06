from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from memcarry.continuity.fingerprint import canonical_repository_id
from memcarry.domain.context import ExecutionContext, RepositoryIdentity


class GitRepositoryInspector:
    """Discover repository, checkout, worktree, branch, and HEAD using local git only."""

    def _git(self, cwd: str, *args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _absolute_git_path(self, cwd: str, value: str | None) -> str | None:
        if not value:
            return None
        path = Path(value)
        if not path.is_absolute():
            path = Path(cwd) / path
        return str(path.resolve())

    def inspect(self, cwd: str) -> ExecutionContext:
        root = self._git(cwd, "rev-parse", "--show-toplevel")
        if not root:
            return ExecutionContext()

        root = str(Path(root).resolve())
        common_dir = self._absolute_git_path(root, self._git(root, "rev-parse", "--git-common-dir"))
        git_dir = self._absolute_git_path(root, self._git(root, "rev-parse", "--git-dir"))
        if not common_dir or not git_dir:
            return ExecutionContext()

        remote = self._git(root, "remote", "get-url", "origin")
        repository = RepositoryIdentity(
            canonical_id=canonical_repository_id(remote=remote, common_dir=common_dir),
            root=root,
            common_dir=common_dir,
            remote=remote,
        )
        checkout_hash = hashlib.sha256(common_dir.encode("utf-8")).hexdigest()[:16]
        worktree_hash = hashlib.sha256(git_dir.encode("utf-8")).hexdigest()[:16]
        branch = self._git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        head_sha = self._git(root, "rev-parse", "HEAD")
        return ExecutionContext(
            repository=repository,
            worktree_id=f"wt:{worktree_hash}",
            branch=branch,
            head_sha=head_sha,
            checkout_id=f"co:{checkout_hash}",
            is_linked_worktree=git_dir != common_dir,
        )
