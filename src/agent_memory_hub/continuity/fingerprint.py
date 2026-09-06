from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse


def normalize_git_remote(remote: str) -> str:
    """Normalize common Git remote forms into a stable host/owner/repo identity."""
    value = remote.strip()
    if not value:
        raise ValueError("remote must not be empty")

    scp_like = re.match(r"^(?:[^@]+@)?([^:]+):(.+)$", value)
    if scp_like and "://" not in value:
        host, path = scp_like.groups()
    else:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https", "ssh", "git"}:
            host, path = parsed.hostname or "", parsed.path
        else:
            raise ValueError(f"unsupported git remote: {remote}")

    host = host.lower().strip()
    path = path.strip().lstrip("/").rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not host or not path:
        raise ValueError(f"invalid git remote: {remote}")
    return f"{host}/{path}"


def canonical_repository_id(*, remote: str | None, common_dir: str) -> str:
    """Prefer normalized remote identity; fall back to a stable local common-dir hash."""
    if remote:
        try:
            return normalize_git_remote(remote)
        except ValueError:
            pass
    canonical_common_dir = str(Path(common_dir).expanduser().resolve())
    suffix = hashlib.sha256(canonical_common_dir.encode("utf-8")).hexdigest()[:16]
    return f"local:{suffix}"
