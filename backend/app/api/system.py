from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.dependencies import DbSession
from app.schemas import HealthResponse, VersionResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/version", response_model=VersionResponse)
def version() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(
        name=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get("/health", response_model=HealthResponse)
def health(session: DbSession) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "database_unavailable", "message": "Az adatbázis nem elérhető."},
        ) from exc
    return HealthResponse(status="ok", database="ok", version=__version__)
