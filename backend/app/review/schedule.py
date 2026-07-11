from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class ReviewOutcome(StrEnum):
    MASTERED = "mastered"
    SHAKY = "shaky"
    UNMASTERED = "unmastered"


@dataclass(frozen=True)
class ReviewSchedule:
    stage: int
    due_at: datetime | None
    status: str


STAGE_DELAYS = (0, 2, 7, 21, 60)


def schedule_next(*, stage: int, outcome: ReviewOutcome, now: datetime) -> ReviewSchedule:
    if outcome is ReviewOutcome.MASTERED:
        if stage == len(STAGE_DELAYS) - 1:
            return ReviewSchedule(stage=stage, due_at=None, status="stable")
        next_stage = stage + 1
        return ReviewSchedule(
            stage=next_stage,
            due_at=now + timedelta(days=STAGE_DELAYS[next_stage]),
            status="learning",
        )

    next_stage = stage if outcome is ReviewOutcome.SHAKY else max(0, stage - 1)
    return ReviewSchedule(
        stage=next_stage,
        due_at=now + timedelta(days=1),
        status="learning",
    )
