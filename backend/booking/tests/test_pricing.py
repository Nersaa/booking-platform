from datetime import date, timedelta

import pytest

from app.availability.pricing import Discount, PriceRules, Season, night_price, price_stay

MONDAY = date(2030, 7, 1)
FRIDAY = MONDAY + timedelta(days=4)
SATURDAY = MONDAY + timedelta(days=5)
SUNDAY = MONDAY + timedelta(days=6)

RULES = PriceRules(
    nightly_price=10_000,
    weekend_price=15_000,
    cleaning_fee=3_000,
    weekly_discount_percent=10,
    monthly_discount_percent=25,
)


def test_weekend_price_applies_to_friday_and_saturday_nights() -> None:
    assert night_price(RULES, [], MONDAY) == 10_000
    assert night_price(RULES, [], FRIDAY) == 15_000
    assert night_price(RULES, [], SATURDAY) == 15_000
    assert night_price(RULES, [], SUNDAY) == 10_000


def test_regular_price_when_weekend_price_is_not_set() -> None:
    rules = PriceRules(10_000, None, 0, 0, 0)
    assert night_price(rules, [], SATURDAY) == 10_000


def test_seasonal_rate_overrides_weekend_price() -> None:
    season = Season(start=FRIDAY, end=SUNDAY, nightly_price=20_000)
    assert night_price(RULES, [season], FRIDAY) == 20_000
    assert night_price(RULES, [season], SATURDAY) == 20_000
    assert night_price(RULES, [season], SUNDAY) == 10_000, "end of a season is exclusive"


def test_short_stay_has_no_discount() -> None:
    stay = price_stay(RULES, [], MONDAY, MONDAY + timedelta(days=3))

    assert [n.price for n in stay.nights] == [10_000, 10_000, 10_000]
    assert stay.subtotal == 30_000
    assert stay.discount == 0
    assert stay.discount_type is None
    assert stay.total == 33_000


def test_weekly_discount_from_seven_nights() -> None:
    stay = price_stay(RULES, [], MONDAY, MONDAY + timedelta(days=7))

    assert stay.subtotal == 5 * 10_000 + 2 * 15_000
    assert stay.discount_type is Discount.WEEKLY
    assert stay.discount == 8_000
    assert stay.total == 80_000 - 8_000 + 3_000


def test_monthly_discount_wins_over_weekly() -> None:
    stay = price_stay(RULES, [], MONDAY, MONDAY + timedelta(days=28))

    assert stay.discount_type is Discount.MONTHLY
    assert stay.discount == stay.subtotal * 25 // 100


def test_discount_is_rounded_down_to_a_minor_unit() -> None:
    rules = PriceRules(999, None, 0, 15, 0)
    stay = price_stay(rules, [], MONDAY, MONDAY + timedelta(days=7))

    assert stay.subtotal == 6_993
    assert stay.discount == 1_048  # 1048.95


def test_check_out_must_follow_check_in() -> None:
    with pytest.raises(ValueError, match="after check_in"):
        price_stay(RULES, [], MONDAY, MONDAY)
