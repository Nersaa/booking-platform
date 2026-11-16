"""Stay price calculation. Pure functions: no I/O, all amounts in minor units."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

FRIDAY, SATURDAY = 4, 5
WEEKLY_STAY_NIGHTS = 7
MONTHLY_STAY_NIGHTS = 28


@dataclass(frozen=True, slots=True)
class PriceRules:
    nightly_price: int
    weekend_price: int | None
    cleaning_fee: int
    weekly_discount_percent: int
    monthly_discount_percent: int


@dataclass(frozen=True, slots=True)
class Season:
    start: date
    end: date  # exclusive
    nightly_price: int

    def covers(self, night: date) -> bool:
        return self.start <= night < self.end


class Discount(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class NightPrice:
    night: date
    price: int


@dataclass(frozen=True, slots=True)
class StayPrice:
    nights: tuple[NightPrice, ...]
    subtotal: int
    discount: int
    discount_type: Discount | None
    cleaning_fee: int

    @property
    def total(self) -> int:
        return self.subtotal - self.discount + self.cleaning_fee


def nights_between(start: date, end: date) -> Iterator[date]:
    for offset in range((end - start).days):
        yield start + timedelta(days=offset)


def night_price(rules: PriceRules, seasons: Sequence[Season], night: date) -> int:
    """A seasonal rate wins over the weekend price, which wins over the regular one."""
    for season in seasons:
        if season.covers(night):
            return season.nightly_price
    if rules.weekend_price is not None and night.weekday() in (FRIDAY, SATURDAY):
        return rules.weekend_price
    return rules.nightly_price


def price_stay(
    rules: PriceRules, seasons: Sequence[Season], check_in: date, check_out: date
) -> StayPrice:
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")

    nights = tuple(
        NightPrice(night, night_price(rules, seasons, night))
        for night in nights_between(check_in, check_out)
    )
    subtotal = sum(night.price for night in nights)

    discount_type: Discount | None = None
    percent = 0
    if len(nights) >= MONTHLY_STAY_NIGHTS and rules.monthly_discount_percent:
        discount_type, percent = Discount.MONTHLY, rules.monthly_discount_percent
    elif len(nights) >= WEEKLY_STAY_NIGHTS and rules.weekly_discount_percent:
        discount_type, percent = Discount.WEEKLY, rules.weekly_discount_percent

    return StayPrice(
        nights=nights,
        subtotal=subtotal,
        # Rounded down to a whole minor unit.
        discount=subtotal * percent // 100,
        discount_type=discount_type,
        cleaning_fee=rules.cleaning_fee,
    )
