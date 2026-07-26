from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.dependencies import CurrentUser, DbSession, require_permissions
from app.models import Document, InventoryReportSchedule
from app.schemas import (
    DocumentRead,
    InventoryReportScheduleRead,
    InventoryReportScheduleUpdate,
)
from app.services.inventory_reports import InventoryReportService

router = APIRouter(prefix="/reports/inventory", tags=["reports"])
ReportSettingsReader = Annotated[
    object,
    Depends(require_permissions("settings.read", "reports.read")),
]
ReportSettingsWriter = Annotated[
    object,
    Depends(require_permissions("settings.write", "reports.generate")),
]
ReportGenerator = Annotated[
    object,
    Depends(require_permissions("reports.generate")),
]


def _correlation_id(value: str | None) -> str:
    return value or str(uuid4())


@router.get("/schedule", response_model=InventoryReportScheduleRead)
def get_inventory_report_schedule(
    session: DbSession,
    user: CurrentUser,
    _: ReportSettingsReader,
) -> InventoryReportSchedule:
    return InventoryReportService(session).get_schedule(user.organization_id)


@router.put("/schedule", response_model=InventoryReportScheduleRead)
def update_inventory_report_schedule(
    payload: InventoryReportScheduleUpdate,
    session: DbSession,
    user: CurrentUser,
    _: ReportSettingsWriter,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> InventoryReportSchedule:
    try:
        return InventoryReportService(session).update_schedule(
            user=user,
            correlation_id=_correlation_id(correlation_header),
            **payload.model_dump(),
        )
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_schedule", "message": str(exc)},
        ) from exc


@router.post(
    "/generate",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def generate_inventory_report(
    session: DbSession,
    user: CurrentUser,
    _: ReportGenerator,
    correlation_header: Annotated[str | None, Header(alias="X-Correlation-ID")] = None,
) -> Document:
    return InventoryReportService(session).generate_now(
        user=user,
        correlation_id=_correlation_id(correlation_header),
    )
