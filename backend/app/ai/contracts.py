from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExtractedGoodsReceiptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    barcode: str | None = Field(default=None, min_length=3, max_length=128)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit: str = Field(min_length=1, max_length=80)
    confidence: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    source_page: int = Field(ge=1, le=500)

    @field_validator("barcode", mode="before")
    @classmethod
    def empty_barcode_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value


class GoodsReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["goods_receipt"]
    document_number: str | None = Field(default=None, max_length=120)
    document_date: date | None = None
    items: list[ExtractedGoodsReceiptItem] = Field(min_length=1, max_length=500)

    @field_validator("document_number", mode="before")
    @classmethod
    def empty_document_number_is_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value
