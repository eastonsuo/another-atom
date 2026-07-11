from collections.abc import Callable

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from another_atom.agent.tasks import execute_blueprint_background
from another_atom.config import get_settings
from another_atom.domain.auth import hash_session_token
from another_atom.domain.errors import AppError
from another_atom.sandbox.client import SandboxClient, get_sandbox_client
from another_atom.storage.database import get_db
from another_atom.storage.models import AuthSession, User, now_utc


def get_current_user(
    request: Request,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    db: Session = Depends(get_db),
) -> User:
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if session_token:
        auth_session = db.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == hash_session_token(session_token),
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now_utc(),
            )
        )
        user = db.get(User, auth_session.user_id) if auth_session else None
        if user is not None:
            return user
    if settings.environment == "test":
        test_user_id = x_user_id or "demo-user"
        user = db.get(User, test_user_id)
        if user is None:
            user = User(
                id=test_user_id,
                display_name="Demo User",
                plan="demo",
                quota_limit=settings.demo_quota_units,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    raise AppError("AUTHENTICATION_REQUIRED", "Sign in to continue", 401)


def get_job_dispatcher() -> Callable[[str], None]:
    # The durable worker polls PostgreSQL. This hook only lets tests wake it synchronously.
    return lambda _job_id: None


def get_blueprint_executor() -> Callable[[str], None]:
    return execute_blueprint_background


def get_sandbox() -> Callable[[], SandboxClient]:
    return get_sandbox_client
