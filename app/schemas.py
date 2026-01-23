from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class PriceType(str, Enum):
    ABSOLUTE = "absolute"
    CX_RELATIVE = "cx_relative"
    CONTACT_ME = "contact_me"


class ListingType(str, Enum):
    STANDING = "standing"
    SPECIAL = "special"


# --- User Schemas ---


class UserBase(BaseModel):
    fio_username: str
    company_code: Optional[str] = None
    company_name: Optional[str] = None
    discord_id: Optional[str] = None


class UserCreate(BaseModel):
    fio_username: str
    fio_api_key: str


class UserPublic(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithListings(UserPublic):
    listings: list["ListingPublic"] = []

    class Config:
        from_attributes = True


# --- Listing Schemas ---


class ListingBase(BaseModel):
    material_ticker: str = Field(..., max_length=10)
    quantity: Optional[int] = Field(None, ge=0)
    price_type: PriceType = PriceType.CONTACT_ME
    price_value: Optional[float] = None
    price_exchange: Optional[str] = Field(None, max_length=10)
    location: Optional[str] = Field(None, max_length=50)
    listing_type: ListingType = ListingType.STANDING
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class ListingCreate(ListingBase):
    pass


class ListingUpdate(BaseModel):
    material_ticker: Optional[str] = Field(None, max_length=10)
    quantity: Optional[int] = Field(None, ge=0)
    price_type: Optional[PriceType] = None
    price_value: Optional[float] = None
    price_exchange: Optional[str] = Field(None, max_length=10)
    location: Optional[str] = Field(None, max_length=50)
    listing_type: Optional[ListingType] = None
    notes: Optional[str] = None
    expires_at: Optional[datetime] = None


class ListingPublic(ListingBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ListingWithUser(ListingPublic):
    user: UserPublic

    class Config:
        from_attributes = True


# --- Community Schemas ---


class CommunityBase(BaseModel):
    name: str
    slug: str


class CommunityPublic(CommunityBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- FIO Data Schemas ---


class FIOBuilding(BaseModel):
    ticker: str
    name: str
    planet_id: Optional[str] = None
    planet_name: Optional[str] = None


class FIOProductionCapability(BaseModel):
    material_ticker: str
    material_name: str
    building_ticker: str
    building_name: str
    location: Optional[str] = None


class FIOUserData(BaseModel):
    username: str
    company_code: str
    company_name: str
    buildings: list[FIOBuilding] = []
    production_capabilities: list[FIOProductionCapability] = []


# Resolve forward references
UserWithListings.model_rebuild()
