from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.availability.schemas import Currency

Sort = Literal["distance", "price", "rating"]
MAX_STAY_NIGHTS = 365


class SearchParams(BaseModel):
    """Every filter is optional; combine them freely."""

    bbox: str | None = Field(
        None,
        description="Map viewport `min_lon,min_lat,max_lon,max_lat`.",
        examples=["-9.25,38.68,-9.08,38.80"],
    )
    lat: float | None = Field(None, ge=-90, le=90, description="Search around a point.")
    lon: float | None = Field(None, ge=-180, le=180)
    radius_km: float = Field(25, gt=0, le=200, description="Used with `lat` and `lon`.")
    country: str | None = Field(None, pattern=r"^[A-Za-z]{2}$", description="ISO 3166-1 alpha-2.")
    city: str | None = Field(None, min_length=1, max_length=100)

    check_in: date | None = Field(None, description="With `check_out`: free on these dates.")
    check_out: date | None = None
    guests: int = Field(1, ge=1, le=50)

    property_type: list[Annotated[str, Field(max_length=20)]] = Field(
        default_factory=list, max_length=10, description="Any of these types."
    )
    amenities: list[Annotated[str, Field(max_length=50)]] = Field(
        default_factory=list, max_length=20, description="All of these amenities."
    )
    min_bedrooms: int | None = Field(None, ge=0, le=50)
    currency: Currency | None = Field(None, description="Required for price filters and sort.")
    min_price: int | None = Field(None, ge=0, description="Base nightly price, minor units.")
    max_price: int | None = Field(None, ge=0)
    min_rating: Decimal | None = Field(None, ge=1, le=5)

    sort: Sort | None = Field(
        None, description="Defaults to `distance` around a point, else `rating`."
    )
    limit: int = Field(20, ge=1, le=50)
    cursor: str | None = Field(None, max_length=500)

    @field_validator("property_type", "amenities")
    @classmethod
    def canonical_set(cls, values: list[str]) -> list[str]:
        # Order does not matter for the result, so it must not matter for the cache key.
        return sorted(set(values))

    @field_validator("country")
    @classmethod
    def upper(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def check_combinations(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon go together")
        if self.bbox is not None:
            if self.lat is not None:
                raise ValueError("Use either bbox or lat/lon, not both")
            self.bounds  # noqa: B018 - validates the format
        if (self.check_in is None) != (self.check_out is None):
            raise ValueError("check_in and check_out go together")
        if self.check_in and self.check_out:
            nights = (self.check_out - self.check_in).days
            if not 1 <= nights <= MAX_STAY_NIGHTS:
                raise ValueError(f"A stay is 1 to {MAX_STAY_NIGHTS} nights")
        if (self.min_price is not None or self.max_price is not None) and not self.currency:
            raise ValueError("Price filters need a currency")
        low, high = self.min_price, self.max_price
        if low is not None and high is not None and low > high:
            raise ValueError("min_price must not exceed max_price")
        if self.sort == "distance" and self.lat is None:
            raise ValueError("Sorting by distance needs lat and lon")
        if self.sort == "price" and not self.currency:
            raise ValueError("Sorting by price needs a currency")
        return self

    @property
    def bounds(self) -> tuple[float, float, float, float] | None:
        if self.bbox is None:
            return None
        try:
            min_lon, min_lat, max_lon, max_lat = (float(part) for part in self.bbox.split(","))
        except ValueError as exc:
            raise ValueError("bbox is min_lon,min_lat,max_lon,max_lat") from exc
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90):
            raise ValueError("bbox corners are out of range or in the wrong order")
        return min_lon, min_lat, max_lon, max_lat

    @property
    def effective_sort(self) -> Sort:
        return self.sort or ("distance" if self.lat is not None else "rating")


class SearchResult(BaseModel):
    id: UUID
    title: str
    property_type: str
    country: str
    city: str
    latitude: Decimal
    longitude: Decimal
    max_guests: int
    bedrooms: int
    beds: int
    bathrooms: int
    amenities: list[str]
    cover_photo_url: str | None
    rating: Decimal | None
    review_count: int
    currency: str
    nightly_price: int = Field(description="Base nightly price, minor units.")
    distance_km: float | None = Field(None, description="From the searched point.")
    stay_total: int | None = Field(
        None, description="For the searched dates: seasons, discounts and cleaning included."
    )
