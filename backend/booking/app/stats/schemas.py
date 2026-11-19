from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field


class MonthStats(BaseModel):
    month: date = Field(description="The first day of the month.")
    bookings: int = Field(description="Paid bookings with check-in in this month.")
    revenue: int = Field(description="Their total, in minor units.")
    nights: int = Field(description="Booked nights that fall in this month.")
    occupancy_percent: float


class TopListing(BaseModel):
    listing_id: UUID
    title: str
    bookings: int
    revenue: int


class HostStatsOut(BaseModel):
    year: int
    currency: str = Field(description="Money below is in this currency only.")
    currencies: list[str] = Field(description="Currencies of the host's bookings that year.")
    listed_places: int
    revenue: int
    bookings: int
    average_booking: int
    nights: int
    occupancy_percent: float
    months: list[MonthStats]
    top_listings: list[TopListing]
