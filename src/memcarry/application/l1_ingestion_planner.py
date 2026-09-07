from __future__ import annotations

from dataclasses import dataclass

from memcarry.application.l1_ingestion_state_detector import L1IngestionStateDetector
from memcarry.domain.l1_ingestion import IngestionMode, IngestionObservation
from memcarry.domain.l1_source import L1SourceFingerprint
from memcarry.ports.l1_source_state import L1SourceStateStore


@dataclass(frozen=True, slots=True)
class L1IngestionPlan:
    mode: IngestionMode
    after_cursor: str | None


class L1IngestionPlanner:
    def __init__(self, state_store: L1SourceStateStore):
        self._state_store = state_store
        self._detector = L1IngestionStateDetector()

    def plan(
        self,
        fingerprint: L1SourceFingerprint,
        *,
        repository_id: str | None,
        store_empty: bool,
        repository_known: bool,
    ) -> L1IngestionPlan:
        previous = self._state_store.load(fingerprint.source_id)
        after_cursor = previous.fingerprint.cursor if previous else None
        interrupted = previous is not None and not previous.complete
        source_changed = fingerprint.changed_from(previous.fingerprint if previous else None)

        mode = self._detector.detect(
            IngestionObservation(
                repository_id=repository_id,
                store_empty=store_empty,
                repository_known=repository_known,
                source_changed=source_changed,
                interrupted=interrupted,
            )
        )
        return L1IngestionPlan(mode=mode, after_cursor=after_cursor)
