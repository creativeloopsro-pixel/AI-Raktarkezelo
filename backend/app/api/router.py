from fastapi import APIRouter

from app.api import (
    ai_settings,
    auth,
    backups,
    documents,
    email_intake,
    goods_receipts,
    identity,
    inventory,
    plugins,
    products,
    reports,
    review_tasks,
    stock,
    system,
    uploads,
    vrp,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(ai_settings.router)
api_router.include_router(backups.router)
api_router.include_router(identity.router)
api_router.include_router(products.router)
api_router.include_router(stock.router)
api_router.include_router(inventory.router)
api_router.include_router(reports.router)
api_router.include_router(documents.router)
api_router.include_router(uploads.router)
api_router.include_router(review_tasks.router)
api_router.include_router(goods_receipts.router)
api_router.include_router(vrp.router)
api_router.include_router(email_intake.router)
api_router.include_router(plugins.router)
