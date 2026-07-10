from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from another_atom.config import get_settings


class Base(DeclarativeBase):
    pass


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def _enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


engine = create_database_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_database(target_engine: Engine | None = None) -> None:
    from another_atom.storage import models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
