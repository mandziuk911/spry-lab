from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import health, meetings
from app.services.errors import DatabaseUnavailable

app = FastAPI(
    title="Meetings API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(DatabaseUnavailable)
def handle_database_unavailable(_: Request, exc: DatabaseUnavailable) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


app.include_router(health.router, prefix="/api")
app.include_router(meetings.router, prefix="/api")
