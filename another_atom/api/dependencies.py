from collections.abc import Callable

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from another_atom.agent.tasks import execute_blueprint_background
from another_atom.config import get_settings
from another_atom.domain.errors import AppError
from another_atom.storage.database import get_db
from another_atom.storage.models import User


def get_current_user(
    x_user_id: str = Header(default="demo-user", alias="X-User-ID"),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, x_user_id)
    if user is None:
        if get_settings().environment != "test":
            raise AppError(
                "USER_NOT_FOUND",
                "The requested demo user is not provisioned",
                401,
            )
        user = User(
            id=x_user_id,
            display_name="Demo User",
            plan="demo",
            quota_limit=get_settings().demo_quota_units,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_job_dispatcher() -> Callable[[str], None]:
    # The durable worker polls PostgreSQL. This hook only lets tests wake it synchronously.
    return lambda _job_id: None


def get_blueprint_executor() -> Callable[[str], None]:
    return execute_blueprint_background
