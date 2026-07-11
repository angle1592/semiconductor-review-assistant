from datetime import UTC, datetime, timedelta

from app.review.schedule import ReviewOutcome, schedule_next


NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def test_mastered_advances_from_new_to_two_days():
    result = schedule_next(stage=0, outcome=ReviewOutcome.MASTERED, now=NOW)

    assert result.stage == 1
    assert result.due_at == NOW + timedelta(days=2)
    assert result.status == "learning"


def test_shaky_stays_at_stage_and_returns_tomorrow():
    result = schedule_next(stage=2, outcome=ReviewOutcome.SHAKY, now=NOW)

    assert result.stage == 2
    assert result.due_at == NOW + timedelta(days=1)


def test_unmastered_steps_back_and_returns_tomorrow():
    result = schedule_next(stage=3, outcome=ReviewOutcome.UNMASTERED, now=NOW)

    assert result.stage == 2
    assert result.due_at == NOW + timedelta(days=1)


def test_passing_sixty_day_stage_archives_item():
    result = schedule_next(stage=4, outcome=ReviewOutcome.MASTERED, now=NOW)

    assert result.stage == 4
    assert result.status == "stable"
    assert result.due_at is None
