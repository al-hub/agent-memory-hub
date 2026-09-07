from __future__ import annotations

import hashlib
import re
import sqlite3
import time
import uuid
from pathlib import Path

from memcarry.domain.l1_evidence import L1Evidence
from memcarry.domain.l1_governance import (
    EvidenceStrength,
    GovernedClaim,
    IncomingClaim,
    ReconciliationAction,
    ReconciliationPolicy,
)
from memcarry.domain.l1_ingestion import L1Record


def _now() -> int:
    return int(time.time())


def _id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalized_hash(statement: str) -> str:
    normalized = re.sub(r"\s+", " ", statement.strip().lower())
    return _hash(normalized)


def _confidence(strength: EvidenceStrength) -> float:
    return {
        EvidenceStrength.STRONG: 0.80,
        EvidenceStrength.MEDIUM: 0.60,
        EvidenceStrength.WEAK: 0.40,
    }[strength]


class SQLiteGovernedL1Store:
    """Persist candidate L1 claims into the existing governed L2 schema.

    `l1_claim_index` is deliberately auxiliary: the canonical prompt-facing rows
    remain `memories` + `evidence`, while ingestion-specific semantic matching
    can evolve without changing the continuity hot path.
    """

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._policy = ReconciliationPolicy()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _ensure_schema(self) -> None:
        con = self._connect()
        try:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories(
                    id TEXT PRIMARY KEY,
                    statement TEXT NOT NULL,
                    normalized_hash TEXT NOT NULL,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    context_quality TEXT NOT NULL,
                    source_agent TEXT,
                    source_type TEXT,
                    source_pointer TEXT,
                    source_hash TEXT,
                    evidence_group TEXT,
                    valid_from TEXT,
                    valid_until TEXT,
                    superseded_by TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    lifecycle TEXT,
                    review_state TEXT,
                    scope TEXT,
                    scope_ref TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_hash ON memories(normalized_hash);

                CREATE TABLE IF NOT EXISTS evidence(
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    raw_source_id TEXT,
                    source_agent TEXT,
                    source_type TEXT,
                    source_pointer TEXT,
                    source_hash TEXT,
                    evidence_group TEXT,
                    excerpt TEXT,
                    confidence REAL,
                    created_at INTEGER NOT NULL,
                    UNIQUE(memory_id, source_hash, source_pointer),
                    FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_memory ON evidence(memory_id);

                CREATE TABLE IF NOT EXISTS l1_claim_index(
                    memory_id TEXT PRIMARY KEY,
                    repository_id TEXT,
                    semantic_key TEXT NOT NULL,
                    value_hash TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    head_sha TEXT,
                    evidence_strength TEXT NOT NULL,
                    FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_l1_claim_lookup
                    ON l1_claim_index(repository_id, semantic_key);
                """
            )
            con.commit()
        finally:
            con.close()

    def is_empty(self) -> bool:
        con = self._connect()
        try:
            row = con.execute(
                "SELECT 1 FROM memories WHERE COALESCE(lifecycle, 'candidate') != 'quarantined' LIMIT 1"
            ).fetchone()
            return row is None
        finally:
            con.close()

    def has_repository(self, repository_id: str) -> bool:
        con = self._connect()
        try:
            row = con.execute(
                """
                SELECT 1 FROM memories
                WHERE COALESCE(lifecycle, 'candidate') != 'quarantined'
                  AND scope='repository' AND scope_ref=?
                LIMIT 1
                """,
                (repository_id,),
            ).fetchone()
            return row is not None
        finally:
            con.close()

    def ingest_record(self, record: L1Record, *, current_head: str | None) -> ReconciliationAction | None:
        if record.repository_id is None:
            return None
        evidence = L1Evidence.from_record(record)
        incoming = IncomingClaim(
            semantic_key=record.effective_semantic_key,
            value_hash=_normalized_hash(record.content),
            memory_type=record.memory_type,
            repository_id=record.repository_id,
            observed_at=record.observed_at,
            head_sha=record.head_sha,
            evidence_strength=evidence.strength,
        )

        con = self._connect()
        try:
            existing_row = con.execute(
                """
                SELECT i.*, m.review_state
                FROM l1_claim_index i
                JOIN memories m ON m.id=i.memory_id
                WHERE i.repository_id=? AND i.semantic_key=?
                  AND COALESCE(m.lifecycle, 'candidate') != 'quarantined'
                ORDER BY i.observed_at DESC
                LIMIT 1
                """,
                (record.repository_id, incoming.semantic_key),
            ).fetchone()

            if existing_row is None:
                review_state = "needs_review" if (
                    current_head and record.head_sha and record.head_sha != current_head
                ) else "unverified"
                memory_id = self._insert_candidate(con, record, evidence, incoming, review_state=review_state)
                self._attach_evidence(con, memory_id, record, evidence)
                con.commit()
                return ReconciliationAction.MARK_STALE if review_state == "needs_review" else None

            existing = GovernedClaim(
                semantic_key=existing_row["semantic_key"],
                value_hash=existing_row["value_hash"],
                memory_type=existing_row["memory_type"],
                repository_id=existing_row["repository_id"],
                observed_at=existing_row["observed_at"],
                head_sha=existing_row["head_sha"],
                review_state=existing_row["review_state"] or "unverified",
                evidence_strength=EvidenceStrength(existing_row["evidence_strength"]),
            )
            outcome = self._policy.reconcile(existing, incoming, current_head=current_head)
            existing_id = existing_row["memory_id"]

            if outcome.action == ReconciliationAction.ATTACH_EVIDENCE:
                self._attach_evidence(con, existing_id, record, evidence)
            elif outcome.action == ReconciliationAction.SUPERSEDE:
                new_id = self._insert_candidate(con, record, evidence, incoming, review_state=outcome.incoming_review_state)
                self._attach_evidence(con, new_id, record, evidence)
                con.execute(
                    "UPDATE memories SET lifecycle='superseded', status='superseded', superseded_by=?, updated_at=? WHERE id=?",
                    (new_id, _now(), existing_id),
                )
            elif outcome.action == ReconciliationAction.RECORD_CONFLICT:
                con.execute(
                    "UPDATE memories SET review_state='conflict', status='conflict', updated_at=? WHERE id=?",
                    (_now(), existing_id),
                )
                new_id = self._insert_candidate(con, record, evidence, incoming, review_state="conflict")
                self._attach_evidence(con, new_id, record, evidence)
            elif outcome.action in {ReconciliationAction.RECORD_CONTRADICTION, ReconciliationAction.MARK_STALE}:
                self._attach_evidence(con, existing_id, record, evidence)
            elif outcome.action == ReconciliationAction.KEEP_SEPARATE:
                new_id = self._insert_candidate(con, record, evidence, incoming, review_state=outcome.incoming_review_state)
                self._attach_evidence(con, new_id, record, evidence)

            con.commit()
            return outcome.action
        finally:
            con.close()

    def _insert_candidate(
        self,
        con: sqlite3.Connection,
        record: L1Record,
        evidence: L1Evidence,
        incoming: IncomingClaim,
        *,
        review_state: str,
    ) -> str:
        memory_id = _id("mem_")
        ts = _now()
        status = "needs_review" if review_state == "needs_review" else ("conflict" if review_state == "conflict" else "candidate")
        con.execute(
            """
            INSERT INTO memories(
                id, statement, normalized_hash, type, status, confidence,
                context_quality, source_agent, source_type, source_pointer,
                source_hash, evidence_group, valid_from, valid_until,
                superseded_by, created_at, updated_at, lifecycle, review_state,
                scope, scope_ref
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                memory_id,
                record.content,
                incoming.value_hash,
                record.memory_type,
                status,
                _confidence(evidence.strength),
                "partial",
                record.source_agent,
                record.kind,
                record.source_path,
                _hash(record.provenance_key),
                evidence.evidence_group,
                record.observed_at,
                None,
                None,
                ts,
                ts,
                "candidate",
                review_state,
                "repository",
                record.repository_id,
            ),
        )
        con.execute(
            """
            INSERT INTO l1_claim_index(
                memory_id, repository_id, semantic_key, value_hash, memory_type,
                observed_at, head_sha, evidence_strength
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                memory_id,
                record.repository_id,
                incoming.semantic_key,
                incoming.value_hash,
                record.memory_type,
                record.observed_at,
                record.head_sha,
                evidence.strength.value,
            ),
        )
        return memory_id

    def _attach_evidence(self, con: sqlite3.Connection, memory_id: str, record: L1Record, evidence: L1Evidence) -> None:
        source_hash = _hash(record.provenance_key)
        con.execute(
            """
            INSERT OR IGNORE INTO evidence(
                id, memory_id, raw_source_id, source_agent, source_type,
                source_pointer, source_hash, evidence_group, excerpt,
                confidence, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                _id("ev_"),
                memory_id,
                None,
                evidence.source_agent,
                evidence.source_type,
                evidence.source_pointer,
                source_hash,
                evidence.evidence_group,
                record.content,
                _confidence(evidence.strength),
                _now(),
            ),
        )

    def insert_seed_memory(self, repository_id: str, statement: str) -> str:
        con = self._connect()
        try:
            memory_id = _id("mem_")
            ts = _now()
            con.execute(
                """
                INSERT INTO memories(
                    id, statement, normalized_hash, type, status, confidence,
                    context_quality, created_at, updated_at, lifecycle,
                    review_state, scope, scope_ref
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    memory_id,
                    statement,
                    _normalized_hash(statement),
                    "fact",
                    "confirmed",
                    1.0,
                    "clear",
                    ts,
                    ts,
                    "active",
                    "verified",
                    "repository",
                    repository_id,
                ),
            )
            con.commit()
            return memory_id
        finally:
            con.close()

    def count_memories(self) -> int:
        con = self._connect()
        try:
            row = con.execute("SELECT COUNT(*) FROM memories").fetchone()
            return int(row[0])
        finally:
            con.close()

    def count_evidence(self) -> int:
        con = self._connect()
        try:
            row = con.execute("SELECT COUNT(*) FROM evidence").fetchone()
            return int(row[0])
        finally:
            con.close()

    def list_memories(self, repository_id: str | None = None) -> list[sqlite3.Row]:
        con = self._connect()
        try:
            if repository_id is None:
                rows = con.execute("SELECT * FROM memories ORDER BY created_at, id").fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM memories WHERE scope='repository' AND scope_ref=? ORDER BY created_at, id",
                    (repository_id,),
                ).fetchall()
            return rows
        finally:
            con.close()
