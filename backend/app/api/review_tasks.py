from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import ReviewTask
from app.schemas import ReviewTaskRead, ReviewTaskResolve
from app.services.documents import (
    DocumentService,
    ReviewTaskNotFoundError,
)

router = APIRouter(prefix="/review-tasks", tags=["review tasks"])


@router.get("", response_model=list[ReviewTaskRead])
def list_review_tasks(
    session: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require_permissions("reviews.read"))],
    task_status: str = Query(default="OPEN", alias="status", max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ReviewTask]:
    return list(
        session.scalars(
            select(ReviewTask)
            .where(
                ReviewTask.organization_id == user.organization_id,
                ReviewTask.status == task_status.upper(),
            )
            .order_by(ReviewTask.created_at.desc())
            .limit(limit)
        )
    )


@router.post("/{task_id}/resolve", response_model=ReviewTaskRead)
def resolve_review_task(
    task_id: str,
    payload: ReviewTaskResolve,
    session: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require_permissions("reviews.resolve"))],
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> ReviewTask:
    try:
        return DocumentService(session).resolve_review_task(
            user=user,
            task_id=task_id,
            resolution_note=payload.resolution_note,
            correlation_id=correlation_header or str(uuid4()),
        )
    except ReviewTaskNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": exc.code, "message": "Az ellenőrzési feladat nem található."},
        ) from exc
