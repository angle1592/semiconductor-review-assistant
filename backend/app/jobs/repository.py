from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from app.jobs.models import DurableJob


def _normalized_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _database_time(value: datetime) -> str:
    return _normalized_time(value).strftime("%Y-%m-%d %H:%M:%S.%f")


def claim_next_job(
    engine,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int,
) -> DurableJob | None:
    timestamp = _database_time(now)
    lease_expires_at = _database_time(now + timedelta(seconds=lease_seconds))
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        connection.exec_driver_sql(
            """
            UPDATE durable_job
            SET status = 'failed',
                worker_id = NULL,
                lease_expires_at = NULL,
                public_error_code = COALESCE(public_error_code, 'LEASE_EXHAUSTED'),
                error_detail = COALESCE(error_detail, 'Worker lease expired after final attempt.'),
                updated_at = ?
            WHERE status = 'running'
              AND lease_expires_at <= ?
              AND attempts >= max_attempts
            """,
            (timestamp, timestamp),
        )
        row = connection.exec_driver_sql(
            """
            SELECT id
            FROM durable_job
            WHERE attempts < max_attempts
              AND (
                (status IN ('queued', 'retry_wait') AND available_at <= ?)
                OR (status = 'running' AND lease_expires_at <= ?)
              )
            ORDER BY available_at ASC, created_at ASC, id ASC
            LIMIT 1
            """,
            (timestamp, timestamp),
        ).first()
        if row is None:
            connection.commit()
            return None
        job_id = int(row[0])
        connection.exec_driver_sql(
            """
            UPDATE durable_job
            SET status = 'running',
                attempts = attempts + 1,
                worker_id = ?,
                lease_expires_at = ?,
                last_heartbeat_at = ?,
                public_error_code = NULL,
                error_detail = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (worker_id, lease_expires_at, timestamp, timestamp, job_id),
        )
        connection.commit()
    with Session(engine) as session:
        return session.get(DurableJob, job_id)


def heartbeat_job(
    engine,
    job_id: int,
    *,
    worker_id: str,
    now: datetime,
    lease_seconds: int,
) -> bool:
    timestamp = _database_time(now)
    lease_expires_at = _database_time(now + timedelta(seconds=lease_seconds))
    with engine.begin() as connection:
        result = connection.exec_driver_sql(
            """
            UPDATE durable_job
            SET lease_expires_at = ?, last_heartbeat_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND worker_id = ?
            """,
            (lease_expires_at, timestamp, timestamp, job_id, worker_id),
        )
    return result.rowcount == 1


def complete_job(
    engine,
    job_id: int,
    *,
    worker_id: str,
    now: datetime,
) -> bool:
    timestamp = _database_time(now)
    with engine.begin() as connection:
        result = connection.exec_driver_sql(
            """
            UPDATE durable_job
            SET status = 'succeeded',
                worker_id = NULL,
                lease_expires_at = NULL,
                updated_at = ?
            WHERE id = ? AND status = 'running' AND worker_id = ?
            """,
            (timestamp, job_id, worker_id),
        )
    return result.rowcount == 1


def retry_or_fail_job(
    engine,
    job_id: int,
    *,
    worker_id: str,
    public_error_code: str,
    error_detail: str,
    now: datetime,
    base_delay_seconds: int,
) -> str:
    timestamp = _database_time(now)
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        row = connection.exec_driver_sql(
            """
            SELECT attempts, max_attempts
            FROM durable_job
            WHERE id = ? AND status = 'running' AND worker_id = ?
            """,
            (job_id, worker_id),
        ).first()
        if row is None:
            connection.commit()
            return "lease_lost"
        attempts, max_attempts = int(row[0]), int(row[1])
        if attempts >= max_attempts:
            status = "failed"
            available_at = timestamp
        else:
            status = "retry_wait"
            delay = base_delay_seconds * (2 ** max(0, attempts - 1))
            available_at = _database_time(now + timedelta(seconds=delay))
        connection.exec_driver_sql(
            """
            UPDATE durable_job
            SET status = ?,
                available_at = ?,
                worker_id = NULL,
                lease_expires_at = NULL,
                public_error_code = ?,
                error_detail = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, available_at, public_error_code, error_detail[:1000], timestamp, job_id),
        )
        connection.commit()
    return status
