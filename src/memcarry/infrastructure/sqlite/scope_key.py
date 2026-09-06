from __future__ import annotations

import hashlib


def scope_fts_token(scope: str, scope_ref: str | None) -> str:
    """Return a tokenizer-safe stable key for one governed memory scope."""
    raw = f"{scope}\0{scope_ref or ''}".encode("utf-8")
    return "s" + hashlib.sha256(raw).hexdigest()[:24]
