from __future__ import annotations

from dataclasses import dataclass

from memcarry.application.l1_ingestion_planner import L1IngestionPlanner
from memcarry.domain.l1_governance import ReconciliationAction
from memcarry.domain.l1_ingestion import IngestionMode
from memcarry.domain.l1_source import L1SourceFingerprint, ProcessedL1SourceState
from memcarry.ports.governed_l1_store import GovernedL1Store
from memcarry.ports.l1_source import L1SourceAdapter
from memcarry.ports.l1_source_state import L1SourceStateStore


DEFAULT_MAX_RECORDS = 50


@dataclass(frozen=True, slots=True)
class L1IngestionResult:
    mode: IngestionMode
    processed: int
    complete: bool
    actions: tuple[ReconciliationAction, ...] = ()


class L1IngestionPipeline:
    """Bounded orchestration for bootstrap, onboarding and incremental reconciliation."""

    def __init__(self, state_store: L1SourceStateStore, memory_store: GovernedL1Store):
        self._state_store = state_store
        self._memory_store = memory_store
        self._planner = L1IngestionPlanner(state_store)

    def ingest(
        self,
        source: L1SourceAdapter,
        *,
        repository_id: str,
        current_head: str | None,
        max_records: int | None = DEFAULT_MAX_RECORDS,
    ) -> L1IngestionResult:
        if max_records is not None and max_records <= 0:
            raise ValueError("max_records must be positive when provided")

        fingerprint = source.fingerprint()
        plan = self._planner.plan(
            fingerprint,
            repository_id=repository_id,
            store_empty=self._memory_store.is_empty(),
            repository_known=self._memory_store.has_repository(repository_id),
        )
        if plan.mode == IngestionMode.NONE:
            return L1IngestionResult(mode=plan.mode, processed=0, complete=True)

        iterator = iter(source.iter_records(repository_id=repository_id, after_cursor=plan.after_cursor))
        processed = 0
        actions: list[ReconciliationAction] = []
        complete = True
        last_cursor = plan.after_cursor

        while True:
            if max_records is not None and processed >= max_records:
                try:
                    next(iterator)
                except StopIteration:
                    complete = True
                else:
                    complete = False
                break
            try:
                record = next(iterator)
            except StopIteration:
                break

            action = self._memory_store.ingest_record(record, current_head=current_head)
            if action is not None:
                actions.append(action)
            processed += 1
            if record.cursor is not None:
                last_cursor = record.cursor
            elif (last_cursor or "").isdigit():
                last_cursor = str(int(last_cursor or 0) + 1)
            elif last_cursor is None:
                last_cursor = str(processed)

        saved_fingerprint = L1SourceFingerprint(
            source_id=fingerprint.source_id,
            size=fingerprint.size,
            mtime_ns=fingerprint.mtime_ns,
            digest=fingerprint.digest,
            cursor=last_cursor,
        )
        self._state_store.save(
            ProcessedL1SourceState(
                fingerprint=saved_fingerprint,
                repository_id=repository_id,
                complete=complete,
            )
        )

        return L1IngestionResult(
            mode=plan.mode,
            processed=processed,
            complete=complete,
            actions=tuple(actions),
        )
