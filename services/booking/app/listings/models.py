from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import DateTime, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Listing(Base):
    """Read model of a Catalog listing, kept up to date by listing events.

    Booking never writes these columns itself; Catalog is the source of truth.
    """

    __tablename__ = "listings"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    version: Mapped[int]
    host_id: Mapped[UUID] = mapped_column(index=True)
    is_listed: Mapped[bool]
    title: Mapped[str] = mapped_column(String(120))
    property_type: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2))
    city: Mapped[str] = mapped_column(String(100))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    max_guests: Mapped[int] = mapped_column(SmallInteger)
    bedrooms: Mapped[int] = mapped_column(SmallInteger)
    beds: Mapped[int] = mapped_column(SmallInteger)
    bathrooms: Mapped[int] = mapped_column(SmallInteger)
    amenities: Mapped[list[str]] = mapped_column(ARRAY(String(50)))
    cover_photo_url: Mapped[str | None] = mapped_column(String(500))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
