from pydantic import BaseModel


class OrderCreate(BaseModel):
    name: str
    quantity: int


class Order(BaseModel):
    id: int
    name: str
    quantity: int
    created_at: str
