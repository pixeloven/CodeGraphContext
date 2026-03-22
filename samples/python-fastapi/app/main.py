from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.routers.orders import order_router, _repository
from app.routers.health import health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize the SQLite database on startup."""
    await _repository.init_db()
    yield


app = FastAPI(title="CGC Sample — Python/FastAPI", lifespan=lifespan)
app.include_router(order_router)
app.include_router(health_router)
