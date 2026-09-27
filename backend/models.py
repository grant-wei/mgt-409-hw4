from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    current_page: str = Field(default="/", max_length=512)


class ChatProductCard(BaseModel):
    product_id: str
    name: str
    description: str
    price: float
    image_path: str


class ProductComparisonItem(BaseModel):
    product_id: str
    name: str
    price: float
    colors: list[str]
    available_sizes: list[str]


class ChatResponse(BaseModel):
    reply: str
    products: list[ChatProductCard] = Field(default_factory=list)
    comparison: list[ProductComparisonItem] = Field(default_factory=list, max_length=2)


class AgentChatResult(BaseModel):
    reply: str
    product_ids: list[str] = Field(default_factory=list, max_length=8)
    comparison_product_ids: list[str] = Field(default_factory=list, max_length=2)


class SizeStock(BaseModel):
    size: str
    quantity: int = Field(ge=0)
    in_stock: bool

    @model_validator(mode="after")
    def validate_stock_status(self) -> "SizeStock":
        if self.in_stock != (self.quantity > 0):
            raise ValueError("in_stock must match the database quantity")
        return self


class ProductSummary(BaseModel):
    product_id: str
    name: str
    garment_type: str
    description: str
    price: float
    image_path: str
    colors: list[str]
    search_tags: list[str]
    sizes: list[SizeStock]


class ChatDependencies(BaseModel):
    database_path: str
    shopper_name: str | None = None
    shopper_email: str | None = None
    current_page: str = "/"
    current_product: ProductSummary | None = None


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    products: list[ChatProductCard] = Field(default_factory=list)
    comparison: list[ProductComparisonItem] = Field(default_factory=list, max_length=2)


class ChatHistoryResponse(BaseModel):
    messages: list[ChatHistoryMessage]
