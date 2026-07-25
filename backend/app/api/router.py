from fastapi import APIRouter

from app.api import auth, products, stock, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(stock.router)
