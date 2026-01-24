"""Pydantic schemas for API request/response validation.

Note: Enums (PriceType, ListingType) are defined in models.py as the single source of truth.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


# --- User Schemas ---


class UserCreate(BaseModel):
    """Schema for creating a new user (registration)."""
    fio_username: str
    fio_api_key: str


class UserPublic(BaseModel):
    """Public user info (no sensitive data)."""
    id: int
    fio_username: str
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Listing Schemas ---


class ListingCreate(BaseModel):
    """Schema for creating a new listing."""
    material_ticker: str = Field(..., max_length=10)
    quantity: Optional[int] = Field(None, ge=0)
    price_type: str = "contact_me"
    price_value: Optional[float] = None
    price_exchange: Optional[str] = Field(None, max_length=10)
    location: Optional[str] = Field(None, max_length=50)
    listing_type: str = "standing"
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class ListingPublic(BaseModel):
    """Public listing info."""
    id: int
    user_id: int
    material_ticker: str
    quantity: Optional[int]
    price_type: str
    price_value: Optional[float]
    price_exchange: Optional[str]
    location: Optional[str]
    listing_type: str
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
