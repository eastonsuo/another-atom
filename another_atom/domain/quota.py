from sqlalchemy import select
from sqlalchemy.orm import Session

from another_atom.agent.provider import ProviderUsage
from another_atom.domain.errors import AppError
from another_atom.storage.models import Run, UsageLedger, User


def reserve_quota(db: Session, user_id: str, run: Run, stage: str, units: int) -> None:
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
            stage=stage,
            units=units,
            entry_type="reserve",
        )
    )


def settle_quota(
    db: Session,
    run: Run,
    stage: str,
    reserved_units: int,
    usage: ProviderUsage,
) -> None:
    user = db.scalar(select(User).where(User.id == run.user_id).with_for_update())
    if user is None:
        return
    spent_units = usage.request_count
    user.quota_reserved = max(0, user.quota_reserved - reserved_units)
    run.quota_reserved = max(0, run.quota_reserved - reserved_units)
    user.quota_used += spent_units
    run.quota_spent += spent_units
    db.add(
        UsageLedger(
            user_id=run.user_id,
            run_id=run.id,
            stage=stage,
            units=spent_units,
            entry_type="settle",
            request_count=usage.request_count,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
    )
    unused = max(0, reserved_units - spent_units)
    if unused:
        db.add(
            UsageLedger(
                user_id=run.user_id,
                run_id=run.id,
                stage=stage,
                units=unused,
                entry_type="release",
            )
        )


def release_quota(db: Session, run: Run, stage: str, units: int | None = None) -> None:
    released = min(units if units is not None else run.quota_reserved, run.quota_reserved)
    if released == 0:
        return
    user = db.scalar(select(User).where(User.id == run.user_id).with_for_update())
    if user is None:
        return
    user.quota_reserved = max(0, user.quota_reserved - released)
    run.quota_reserved = max(0, run.quota_reserved - released)
    db.add(
        UsageLedger(
            user_id=run.user_id,
            run_id=run.id,
            stage=stage,
            units=released,
            entry_type="release",
        )
    )
