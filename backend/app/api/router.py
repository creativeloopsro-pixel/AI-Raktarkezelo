from fastapi import APIRouter

from app.api import auth, documents, goods_receipts, products, review_tasks, stock, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(stock.router)
api_router.include_router(documents.router)
api_router.include_router(review_tasks.router)
api_router.include_router(goods_receipts.router)
