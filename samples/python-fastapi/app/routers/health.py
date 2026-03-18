from fastapi import APIRouter

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/")
async def health_check() -> dict:
    return {"status": "ok"}
