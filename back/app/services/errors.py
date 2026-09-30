import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    """Storage failed; never expose the underlying SQL or connection details."""


@contextmanager
def storage_operation(db: Session) -> Iterator[None]:
    try:
        yield
    except SQLAlchemyError as exc:
        # Exception text/tracebacks can contain SQL, parameters and credentials.
        logger.error("Database operation failed (%s)", type(exc).__name__)
        try:
            db.rollback()
        except SQLAlchemyError as rollback_exc:
            logger.error("Database rollback failed (%s)", type(rollback_exc).__name__)
        raise DatabaseUnavailable from None
