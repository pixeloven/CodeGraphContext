from fastapi import APIRouter, HTTPException

from app.models import Order, OrderCreate
from app.services.order_service import OrderService
from app.repositories.order_repository import OrderRepository

order_router = APIRouter(prefix="/api/orders", tags=["orders"])

_DB_PATH = "orders.db"
_repository = OrderRepository(db_path=_DB_PATH)
_service = OrderService(repository=_repository)


@order_router.get("", response_model=list[Order])
async def list_orders() -> list[dict]:
    return await _service.list_orders()


@order_router.post("", response_model=Order, status_code=201)
async def create_order(data: OrderCreate) -> dict:
    try:
        return await _service.create_order(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
