from fastapi import APIRouter

from app.api import (
    auth,
    documents,
    email_intake,
    goods_receipts,
    inventory,
    plugins,
    products,
    review_tasks,
    stock,
    system,
    vrp,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(stock.router)
api_router.include_router(inventory.router)
api_router.include_router(documents.router)
api_router.include_router(review_tasks.router)
api_router.include_router(goods_receipts.router)
api_router.include_router(vrp.router)
api_router.include_router(email_intake.router)
api_router.include_router(plugins.router)
