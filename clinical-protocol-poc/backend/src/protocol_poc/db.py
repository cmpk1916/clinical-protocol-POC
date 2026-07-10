from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from protocol_poc.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def create_database_engine(settings: Settings | None = None) -> Engine:
    configured = settings or get_settings()
    return create_engine(configured.database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory.begin() as session:
        yield session
