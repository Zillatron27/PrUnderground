from datetime import datetime, date
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
import enum

from .database import Base


class PriceType(enum.Enum):
    ABSOLUTE = "absolute"
    CX_RELATIVE = "cx_relative"
    CONTACT_ME = "contact_me"


class ListingType(enum.Enum):
    STANDING = "standing"
    SPECIAL = "special"


class BundleStockMode(enum.Enum):
    MANUAL = "manual"
    UNLIMITED = "unlimited"
    MADE_TO_ORDER = "made_to_order"
    FIO_SYNC = "fio_sync"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    fio_username = Column(String(50), unique=True, index=True, nullable=False)
    company_code = Column(String(10), index=True)
    company_name = Column(String(100))
    discord_id = Column(String(50), unique=True, nullable=True)
    fio_api_key = Column(String(256), nullable=True)  # Encrypted with Fernet (see encryption.py)
    fio_last_synced = Column(DateTime, nullable=True)  # When FIO data was last pulled
    managing_director = Column(String(100), nullable=True)  # In-game MD name for contracts
    discord_username = Column(String(32), nullable=True)  # Discord username for out-of-game contact
    discord_template = Column(Text, nullable=True)  # Custom Discord copy format template
    color_palette = Column(String(20), nullable=True)  # Theme color palette preference
    tile_style = Column(String(20), nullable=True)  # Tile style preference (filled/lite)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    listings = relationship("Listing", back_populates="user", cascade="all, delete-orphan")
    bundles = relationship("Bundle", back_populates="user", cascade="all, delete-orphan")
    community_memberships = relationship(
        "CommunityMembership", back_populates="user", cascade="all, delete-orphan"
    )


# --- Future: Multi-community support (roadmap item) ---


class Community(Base):
    __tablename__ = "communities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    slug = Column(String(50), unique=True, nullable=False, index=True)
    discord_guild_id = Column(String(50), unique=True, nullable=True)
    discord_channel_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    memberships = relationship(
        "CommunityMembership", back_populates="community", cascade="all, delete-orphan"
    )


class CommunityMembership(Base):
    __tablename__ = "community_memberships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    community_id = Column(Integer, ForeignKey("communities.id"), nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="community_memberships")
    community = relationship("Community", back_populates="memberships")


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    material_ticker = Column(String(10), nullable=False, index=True)
    quantity = Column(Integer, nullable=True)  # None = standing offer, no specific qty
    price_type = Column(SQLEnum(PriceType), nullable=False, default=PriceType.CONTACT_ME)
    price_value = Column(Float, nullable=True)  # Absolute price or CX offset percentage/amount
    price_exchange = Column(String(10), nullable=True)  # e.g., "NC1" for CX-relative
    price_cx_is_absolute = Column(Boolean, default=False)  # True = absolute offset, False = percentage
    location = Column(String(50), nullable=True)  # Planet or station
    listing_type = Column(SQLEnum(ListingType), nullable=False, default=ListingType.STANDING)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    # Live inventory tracking from FIO storage
    storage_id = Column(String(100), nullable=True)  # FIO AddressableId
    storage_name = Column(String(100), nullable=True)  # Human-readable name (cached)
    reserve_quantity = Column(Integer, nullable=True, default=0)  # Amount to keep in stock
    available_quantity = Column(Integer, nullable=True)  # Computed: actual FIO stock - reserve
    low_stock_threshold = Column(Integer, nullable=True, default=10)  # Custom low stock threshold

    user = relationship("User", back_populates="listings")


class Bundle(Base):
    """A bundle is a collection of multiple items sold together at a single price."""

    __tablename__ = "bundles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=True)  # How many bundles available (None = unlimited)
    price = Column(Float, nullable=True)  # Total bundle price (None = contact me)
    currency = Column(String(10), nullable=True)  # AIC, CIS, NCC, ICA
    location = Column(String(50), nullable=True)  # Pickup location
    listing_type = Column(SQLEnum(ListingType), nullable=False, default=ListingType.STANDING)
    expires_at = Column(DateTime, nullable=True)  # For special listings
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Stock mode and inventory tracking
    stock_mode = Column(SQLEnum(BundleStockMode), nullable=False, default=BundleStockMode.MANUAL)
    storage_id = Column(String(100), nullable=True)      # FIO AddressableId for FIO_SYNC mode
    storage_name = Column(String(100), nullable=True)    # Cached human-readable name
    available_quantity = Column(Integer, nullable=True)  # Computed for FIO_SYNC mode
    ready_quantity = Column(Integer, nullable=True)      # For MADE_TO_ORDER mode
    low_stock_threshold = Column(Integer, nullable=True)  # Optional custom low stock threshold (None = no check)

    user = relationship("User", back_populates="bundles")
    items = relationship("BundleItem", back_populates="bundle", cascade="all, delete-orphan")


class BundleItem(Base):
    """An individual item within a bundle."""

    __tablename__ = "bundle_items"

    id = Column(Integer, primary_key=True, index=True)
    bundle_id = Column(Integer, ForeignKey("bundles.id"), nullable=False)
    material_ticker = Column(String(10), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)

    bundle = relationship("Bundle", back_populates="items")


class Material(Base):
    """Cached material data from FIO API."""

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    category_name = Column(String(50), nullable=True)
    category_id = Column(String(50), nullable=True)
    weight = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Planet(Base):
    """Cached planet/station data from FIO API."""

    __tablename__ = "planets"

    id = Column(Integer, primary_key=True, index=True)
    planet_id = Column(String(50), unique=True, index=True, nullable=False)  # FIO PlanetId
    name = Column(String(100), nullable=False, index=True)  # Human-readable name
    natural_id = Column(String(20), nullable=True)  # e.g., "UV-351a"
    system_name = Column(String(100), nullable=True)
    is_station = Column(Integer, default=0)  # 1 for CX stations, 0 for planets
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Exchange(Base):
    """Cached commodity exchange price data from FIO API."""

    __tablename__ = "exchanges"

    id = Column(Integer, primary_key=True, index=True)
    material_ticker = Column(String(10), index=True, nullable=False)
    exchange_code = Column(String(10), index=True, nullable=False)  # NC1, IC1, CI1, AI1, NC2
    price_ask = Column(Float, nullable=True)  # Lowest ask price
    price_bid = Column(Float, nullable=True)  # Highest bid price
    price_average = Column(Float, nullable=True)  # Average/market price
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('material_ticker', 'exchange_code', name='uix_exchange_material'),
    )


class UsageStats(Base):
    """Anonymous usage statistics for admin dashboard."""

    __tablename__ = "usage_stats"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True, nullable=False)
    metric = Column(String(50), index=True, nullable=False)
    value = Column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint('date', 'metric', name='uix_stats_date_metric'),
    )
