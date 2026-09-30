from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Bound connection acquisition, server work and detection of a black-holed TCP connection.
DB_CONNECT_ARGS = {
    "connect_timeout": 3,
    "options": "-c statement_timeout=3000 -c lock_timeout=2000",
    "keepalives": 1,
    "keepalives_idle": 2,
    "keepalives_interval": 1,
    "keepalives_count": 2,
    "tcp_user_timeout": 5000,
}
engine = create_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_timeout=3,
    connect_args=DB_CONNECT_ARGS,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
