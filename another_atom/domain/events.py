from typing import Any

from sqlalchemy.orm import Session

from another_atom.storage.models import RunEvent


def record_event(
    db: Session,
    run_id: str,
    event_type: str,
    message: str,
    *,
    stage: str | None = None,
    payload: dict[str, Any] | None = None,
) -> RunEvent:
    event = RunEvent(
        run_id=run_id,
        event_type=event_type,
        stage=stage,
        message=message,
        payload=payload or {},
    )
    db.add(event)
    db.flush()
    return event
