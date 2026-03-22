from __future__ import annotations

from app.models import OrderCreate
from app.repositories.order_repository import OrderRepository


class OrderService:
    """Business-logic layer sitting between routers and the repository."""

    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def list_orders(self) -> list[dict]:
        """Retrieve all orders from the repository."""
        return await self._repository.find_all()

    async def create_order(self, data: OrderCreate) -> dict:
        """Validate and persist a new order."""
        if data.quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        return await self._repository.create(data.model_dump())
