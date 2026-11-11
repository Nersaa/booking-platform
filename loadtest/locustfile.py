"""Load profile of the platform: many guests browsing, a few booking and paying.

Browsers search the map with and without dates, open listing pages, calendars and quotes.
Bookers register, book a place found by search and pay on the provider's page; under
load many of them race for the same nights, so 409 "dates taken" is an expected answer.

See docs/load-testing.md for how to run it and the results.
"""

import os
import random
import uuid
from datetime import UTC, datetime, timedelta

from locust import HttpUser, between, task

# Same cities as `manage.py seed_listings`.
CITIES = {
    "Lisbon": (38.7223, -9.1393),
    "Porto": (41.1579, -8.6291),
    "Barcelona": (41.3874, 2.1686),
    "Madrid": (40.4168, -3.7038),
    "Paris": (48.8566, 2.3522),
    "Berlin": (52.5200, 13.4050),
    "Rome": (41.9028, 12.4964),
    "Amsterdam": (52.3676, 4.9041),
}
# The guest opens the checkout page in a browser; from the load generator the provider
# is reached inside the Docker network instead.
CHECKOUT_PUBLIC_URL = os.environ.get("CHECKOUT_PUBLIC_URL", "http://localhost:8090")
CHECKOUT_URL = os.environ.get("CHECKOUT_URL", "http://payment-mock:8000")


def popular_stay() -> tuple[str, str]:
    """Most people search the same few weekends: realistic contention and cache hits."""
    today = datetime.now(UTC).date()
    friday = today + timedelta(days=(4 - today.weekday()) % 7 + 7 * random.randint(3, 10))
    check_out = friday + timedelta(days=random.choice((2, 3, 7)))
    return str(friday), str(check_out)


def map_area() -> dict[str, str]:
    lat, lon = CITIES[random.choice(list(CITIES))]
    return {"bbox": f"{lon - 0.15:.2f},{lat - 0.1:.2f},{lon + 0.15:.2f},{lat + 0.1:.2f}"}


class Browser(HttpUser):
    weight = 9
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.seen: list[str] = []

    def search(self, params: dict[str, str | int], name: str) -> None:
        response = self.client.get("/api/v1/listings", params=params, name=name)
        if response.ok:
            self.seen = [item["id"] for item in response.json()["items"]] or self.seen

    @task(4)
    def search_map(self) -> None:
        self.search(map_area(), "/api/v1/listings [map]")

    @task(4)
    def search_map_with_dates(self) -> None:
        check_in, check_out = popular_stay()
        params = {**map_area(), "check_in": check_in, "check_out": check_out, "guests": 2}
        self.search(params, "/api/v1/listings [map + dates]")

    @task(1)
    def search_nearby(self) -> None:
        lat, lon = CITIES[random.choice(list(CITIES))]
        params = {"lat": lat, "lon": lon, "radius_km": 10, "sort": "distance"}
        self.search(params, "/api/v1/listings [nearby]")

    @task(4)
    def open_listing(self) -> None:
        if self.seen:
            listing = random.choice(self.seen)
            self.client.get(f"/api/v1/listings/{listing}", name="/api/v1/listings/{id}")

    @task(2)
    def calendar(self) -> None:
        if self.seen:
            listing = random.choice(self.seen)
            self.client.get(
                f"/api/v1/listings/{listing}/calendar", name="/api/v1/listings/{id}/calendar"
            )

    @task(2)
    def quote(self) -> None:
        if self.seen:
            check_in, check_out = popular_stay()
            with self.client.get(
                f"/api/v1/listings/{random.choice(self.seen)}/quote",
                params={"check_in": check_in, "check_out": check_out},
                name="/api/v1/listings/{id}/quote",
                catch_response=True,
            ) as response:
                # Busy dates or a stay shorter than the host allows are normal answers.
                if response.status_code in (400, 409):
                    response.success()


class Booker(HttpUser):
    weight = 1
    wait_time = between(2, 5)

    def on_start(self) -> None:
        email = f"load-{uuid.uuid4().hex[:12]}@example.com"
        password = f"Load-{uuid.uuid4().hex}"
        self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "first_name": "Load", "last_name": "Test"},
            name="/api/v1/auth/register",
        )
        tokens = self.client.post(
            "/api/v1/auth/token", json={"email": email, "password": password}
        ).json()
        self.client.headers["Authorization"] = f"Bearer {tokens['access']}"

    @task
    def book_and_pay(self) -> None:
        check_in, check_out = popular_stay()
        found = self.client.get(
            "/api/v1/listings",
            params={**map_area(), "check_in": check_in, "check_out": check_out, "guests": 2},
            name="/api/v1/listings [map + dates]",
        )
        items = found.json()["items"] if found.ok else []
        if not items:
            return

        listing = random.choice(items[:5])  # everyone likes the top results
        with self.client.post(
            "/api/v1/bookings",
            json={
                "listing_id": listing["id"],
                "check_in": check_in,
                "check_out": check_out,
                "guests": 2,
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
            catch_response=True,
        ) as response:
            if response.status_code == 409:
                response.success()  # someone was faster: the guarantee working, not a failure
                return
            if response.status_code != 201:
                return
            booking = response.json()

        payment = self.client.post(
            f"/api/v1/bookings/{booking['id']}/payments",
            headers={"Idempotency-Key": str(uuid.uuid4())},
            name="/api/v1/bookings/{id}/payments",
        )
        if payment.ok:
            checkout = payment.json()["checkout_url"].replace(CHECKOUT_PUBLIC_URL, CHECKOUT_URL)
            self.client.post(f"{checkout}/pay", name="provider: pay")

    @task
    def my_bookings(self) -> None:
        self.client.get("/api/v1/bookings", params={"limit": 20})
