from datetime import date, datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.availability.models import AvailabilityBlock, SeasonalRate, period_bounds
from app.availability.pricing import Discount

MAX_PERIOD_NIGHTS = 366

Money = Annotated[
    int, Field(gt=0, le=100_000_000, description="Amount in minor units, e.g. cents.")
]
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$", description="ISO 4217 code.")]
Percent = Annotated[int, Field(ge=0, le=90)]
Nights = Annotated[int, Field(ge=1, le=365)]


class PricingIn(BaseModel):
    currency: Currency
    nightly_price: Money
    weekend_price: Money | None = Field(None, description="Friday and Saturday nights.")
    cleaning_fee: int = Field(0, ge=0, le=100_000_000)
    min_nights: Nights = 1
    max_nights: Nights = 365
    weekly_discount_percent: Percent = Field(0, description="Stays of 7 nights or more.")
    monthly_discount_percent: Percent = Field(0, description="Stays of 28 nights or more.")
    instant_book: bool = Field(
        True, description="False: the host accepts or declines every booking first."
    )

    @model_validator(mode="after")
    def check_nights(self) -> Self:
        if self.max_nights < self.min_nights:
            raise ValueError("max_nights must not be less than min_nights")
        return self


class PricingOut(PricingIn):
    model_config = ConfigDict(from_attributes=True)

    listing_id: UUID
    updated_at: datetime


class Period(BaseModel):
    start_date: date
    end_date: date = Field(description="Exclusive, like a check-out day.")

    @model_validator(mode="after")
    def check_period(self) -> Self:
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if (self.end_date - self.start_date).days > MAX_PERIOD_NIGHTS:
            raise ValueError(f"A period cannot be longer than {MAX_PERIOD_NIGHTS} nights")
        return self


class SeasonalRateIn(Period):
    nightly_price: Money


class SeasonalRateOut(SeasonalRateIn):
    id: UUID

    @classmethod
    def from_model(cls, rate: SeasonalRate) -> Self:
        start, end = period_bounds(rate.period)
        return cls(id=rate.id, start_date=start, end_date=end, nightly_price=rate.nightly_price)


class BlockIn(Period):
    note: str = Field("", max_length=200)


class BlockOut(BlockIn):
    id: UUID

    @classmethod
    def from_model(cls, block: AvailabilityBlock) -> Self:
        start, end = period_bounds(block.period)
        return cls(id=block.id, start_date=start, end_date=end, note=block.note)


class CalendarDay(BaseModel):
    date: date
    available: bool
    nightly_price: int


class CalendarOut(BaseModel):
    listing_id: UUID
    currency: str
    min_nights: int
    max_nights: int
    instant_book: bool
    days: list[CalendarDay]


class QuoteNight(BaseModel):
    date: date
    price: int


class QuoteOut(BaseModel):
    listing_id: UUID
    check_in: date
    check_out: date
    guests: int
    currency: str
    nights: list[QuoteNight]
    subtotal: int
    discount: int
    discount_type: Discount | None
    cleaning_fee: int
    total: int
