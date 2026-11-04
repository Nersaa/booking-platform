from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Computed, DateTime, Index, Numeric, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db import Base


class Geography(UserDefinedType[str]):
    """PostGIS point on the WGS 84 sphere; distances come out in metres."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "geography(Point,4326)"


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
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int] = mapped_column(server_default=text("0"))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Derived by PostgreSQL from the coordinates, so it can never disagree with them.
    # Only used inside queries (never loaded), hence deferred.
    location: Mapped[str] = mapped_column(
        Geography(),
        Computed(
            "(ST_SetSRID(ST_MakePoint(longitude::double precision, "
            "latitude::double precision), 4326))::geography",
            persisted=True,
        ),
        deferred=True,
    )

    __table_args__ = (
        Index("ix_listings_location", "location", postgresql_using="gist"),
        Index("ix_listings_amenities", "amenities", postgresql_using="gin"),
    )
