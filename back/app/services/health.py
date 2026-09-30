from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.errors import storage_operation


def check_database(db: Session) -> None:
    with storage_operation(db):
        db.execute(text("SELECT 1"))
