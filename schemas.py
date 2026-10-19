import re
from decimal import Decimal
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Currency = Literal["SYP", "USD"]
Condition = Literal["new", "used"]


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(pattern=r"^09\d{8}$")
    password: str = Field(min_length=10, max_length=128)
    shop: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=80)
    region: str | None = Field(default=None, max_length=80)


class LoginIn(BaseModel):
    phone: str = Field(pattern=r"^09\d{8}$")
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    role: str
    shop: str | None
    city: str | None
    region: str | None


class ListingCreate(BaseModel):
    brand: str = Field(min_length=1, max_length=60)
    model: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: Currency
    city: str = Field(min_length=1, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    condition: Condition
    description: str = Field(default="", max_length=5000)
    seller_name: str = Field(min_length=1, max_length=120)
    contact_phone: str = Field(pattern=r"^09\d{8}$")
    storage_gb: int = Field(default=128, ge=1, le=2048)
    ram_gb: int | None = Field(default=None, ge=1, le=128)

    @field_validator("brand", "model", "city", "seller_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ListingUpdate(BaseModel):
    brand: str | None = Field(default=None, min_length=1, max_length=60)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: Currency | None = None
    city: str | None = Field(default=None, min_length=1, max_length=80)
    region: str | None = Field(default=None, max_length=80)
    condition: Condition | None = None
    description: str | None = Field(default=None, max_length=5000)
    seller_name: str | None = Field(default=None, min_length=1, max_length=120)
    contact_phone: str | None = Field(default=None, pattern=r"^09\d{8}$")
    storage_gb: int | None = Field(default=None, ge=1, le=2048)
    ram_gb: int | None = Field(default=None, ge=1, le=128)

    @field_validator("brand", "model", "city", "seller_name")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("must not be null")
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("price", "currency", "condition", "description", "contact_phone", "storage_gb")
    @classmethod
    def reject_null_for_required_columns(cls, value):
        if value is None:
            raise ValueError("must not be null")
        return value


class ListingOut(BaseModel):
    id: int
    owner_id: int
    title: str
    brand: str
    model: str
    price: str
    currency: Currency
    city: str
    region: str | None
    condition: Condition
    description: str
    seller_name: str
    contact_phone: str
    storage_gb: int
    ram_gb: int | None
    is_sold: bool
    views: int
    created_at: datetime
    updated_at: datetime
    images: list[str]


class ReportCreate(BaseModel):
    listing_id: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=80)
    details: str = Field(default="", max_length=2000)