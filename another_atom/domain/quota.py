from sqlalchemy import select
from sqlalchemy.orm import Session

from another_atom.domain.errors import AppError
from another_atom.storage.models import Run, UsageLedger, User

TEAM_RESERVATION = 4
ENGINEER_RESERVATION = 3


def reservation_for_mode(mode: str) -> int:
    return TEAM_RESERVATION if mode == "team" else ENGINEER_RESERVATION


def reserve_quota(db: Session, user_id: str, run: Run, units: int) -> None:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        raise AppError("USER_NOT_FOUND", "User does not exist", 404)
    remaining = user.quota_limit - user.quota_used - user.quota_reserved
    if remaining < units:
        raise AppError(
            "QUOTA_EXCEEDED",
            "Demo quota is exhausted. Reset the demo account quota before starting another run.",
            409,
        )
    user.quota_reserved += units
    run.quota_reserved += units
    db.add(
        UsageLedger(
            user_id=user_id,
            run_id=run.id,
            stage="run",
            units=units,
            entry_type="reserve",
        )
    )


def settle_quota(db: Session, run: Run, spent_units: int) -> None:
    user = db.scalar(select(User).where(User.id == run.user_id).with_for_update())
    if user is None:
        return
    released = run.quota_reserved
    user.quota_reserved = max(0, user.quota_reserved - released)
    user.quota_used += spent_units
    run.quota_reserved = 0
    run.quota_spent += spent_units
    db.add(
        UsageLedger(
            user_id=run.user_id,
            run_id=run.id,
            stage=run.current_stage,
            units=spent_units,
            entry_type="settle",
        )
    )


def release_quota(db: Session, run: Run) -> None:
    if run.quota_reserved == 0:
        return
    user = db.scalar(select(User).where(User.id == run.user_id).with_for_update())
    if user is None:
        return
    released = run.quota_reserved
    user.quota_reserved = max(0, user.quota_reserved - released)
    run.quota_reserved = 0
    db.add(
        UsageLedger(
            user_id=run.user_id,
            run_id=run.id,
            stage=run.current_stage,
            units=released,
            entry_type="release",
        )
    )
