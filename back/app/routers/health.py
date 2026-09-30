from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.errors import DatabaseUnavailable
from app.services.health import check_database

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        check_database(db)
    except DatabaseUnavailable:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
