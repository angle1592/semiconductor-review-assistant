from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from app.jobs.repository import cancel_job, claim_next_job, complete_job, retry_or_fail_job
from app.jobs.service import redact_error_detail
from app.runtime.paths import AppPaths
from app.shared.errors import AppError
from app.shared.database import create_database


JobHandler = Callable[[dict[str, object]], None]


class DurableWorker:
    def __init__(
        self,
        engine,
        handlers: Mapping[str, JobHandler],
        *,
        worker_id: str | None = None,
        lease_seconds: int = 60,
        retry_base_seconds: int = 5,
    ):
        self.engine = engine
        self.handlers = handlers
        self.worker_id = worker_id or f"worker-{uuid4().hex}"
        self.lease_seconds = lease_seconds
        self.retry_base_seconds = retry_base_seconds

    def run_once(self, *, now: datetime | None = None) -> bool:
        timestamp = now or datetime.now(UTC)
        job = claim_next_job(
            self.engine,
            worker_id=self.worker_id,
            now=timestamp,
            lease_seconds=self.lease_seconds,
        )
        if job is None:
            return False
        try:
            handler = self.handlers[job.kind]
            payload = json.loads(job.payload_json)
            result = handler(payload)
        except Exception as error:
            error_code = error.code if isinstance(error, AppError) else "JOB_HANDLER_FAILED"
            detail = redact_error_detail(error)
            state = retry_or_fail_job(
                self.engine,
                job.id,
                worker_id=self.worker_id,
                public_error_code=error_code,
                error_detail=detail,
                now=timestamp,
                base_delay_seconds=self.retry_base_seconds,
            )
            if state == "failed":
                terminal_handler = getattr(handler, "on_terminal_failure", None)
                if terminal_handler is not None:
                    terminal_handler(payload, error_code, detail)
            return True
        if result == "cancelled":
            cancel_job(self.engine, job.id, worker_id=self.worker_id, now=timestamp)
        else:
            complete_job(self.engine, job.id, worker_id=self.worker_id, now=timestamp)
        return True


def main() -> None:
    from app.analysis.worker_handler import AnalysisWorkerHandler
    from app.providers.credentials import WindowsKeyringSecretStore
    from app.providers.service import default_adapter_factory
    from app.study.worker_handler import ArtifactWorkerHandler

    paths = AppPaths.discover()
    paths.ensure_directories()
    engine = create_database(paths.data)
    analysis_handler = AnalysisWorkerHandler(
        engine,
        paths.runtime,
        WindowsKeyringSecretStore(),
        default_adapter_factory,
        data_dir=paths.data,
    )
    artifact_handler = ArtifactWorkerHandler(
        engine,
        paths.runtime,
        WindowsKeyringSecretStore(),
        default_adapter_factory,
    )
    worker = DurableWorker(
        engine,
        {"analysis_run": analysis_handler, "artifact_generation": artifact_handler},
    )
    stop_file_value = os.getenv("SHIYAO_WORKER_STOP_FILE", "")
    stop_file = Path(stop_file_value).resolve() if stop_file_value else None
    poll_seconds = float(os.getenv("SHIYAO_WORKER_POLL_SECONDS", "0.5"))
    try:
        while stop_file is None or not stop_file.exists():
            if not worker.run_once():
                time.sleep(poll_seconds)
    finally:
        engine.dispose()
        if stop_file is not None:
            stop_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
