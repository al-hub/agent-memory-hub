from __future__ import annotations

from memcarry.domain.l1_ingestion import IngestionMode, IngestionObservation


class L1IngestionStateDetector:
    def detect(self, observation: IngestionObservation) -> IngestionMode:
        if observation.repository_id is None:
            return IngestionMode.NONE
        if observation.interrupted:
            return IngestionMode.RESUME_INGEST
        if observation.store_empty:
            return IngestionMode.BOOTSTRAP
        if not observation.repository_known:
            return IngestionMode.ONBOARD
        if observation.source_changed:
            return IngestionMode.RECONCILE
        return IngestionMode.NONE
