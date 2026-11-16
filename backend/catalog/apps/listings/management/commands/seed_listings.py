"""Demo data for local runs and load tests: published listings around European cities.

Publishing goes through the normal service, so every listing also reaches Booking
through the outbox. Prints JSON with the host's access token (to set prices in Booking)
and the listing ids.
"""

import json
import random
from argparse import ArgumentParser
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand

from apps.listings import services
from apps.listings.models import Amenity, Listing, ListingStatus, PropertyType
from apps.users.models import User
from apps.users.tokens import issue_token_pair

HOST_EMAIL = "seed-host@example.com"
CITIES = {
    "Lisbon": ("PT", 38.7223, -9.1393),
    "Porto": ("PT", 41.1579, -8.6291),
    "Barcelona": ("ES", 41.3874, 2.1686),
    "Madrid": ("ES", 40.4168, -3.7038),
    "Paris": ("FR", 48.8566, 2.3522),
    "Berlin": ("DE", 52.5200, 13.4050),
    "Rome": ("IT", 41.9028, 12.4964),
    "Amsterdam": ("NL", 52.3676, 4.9041),
}


class Command(BaseCommand):
    help = "Create published demo listings (development and load testing only)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--count", type=int, default=200)
        parser.add_argument("--seed", type=int, default=42, help="Same seed, same data.")

    def handle(self, *args: Any, **options: Any) -> None:
        rng = random.Random(options["seed"])
        host, _ = User.objects.get_or_create(
            email=HOST_EMAIL, defaults={"first_name": "Seed", "last_name": "Host", "is_host": True}
        )
        amenities = list(Amenity.objects.all())
        ids = []
        for n in range(options["count"]):
            city = rng.choice(list(CITIES))
            country, lat, lon = CITIES[city]
            bedrooms = rng.randint(0, 4)
            listing = Listing.objects.create(
                host=host,
                title=f"{rng.choice(['Sunny', 'Quiet', 'Central', 'Cosy', 'Bright'])} "
                f"place in {city} #{n + 1}",
                description="Demo listing for local runs and load tests.",
                property_type=rng.choice(PropertyType.values),
                # Moderation is a human step; demo data skips it, publishing does not.
                status=ListingStatus.PENDING_REVIEW,
                country=country,
                city=city,
                address=f"Demo street {n + 1}",
                latitude=Decimal(str(round(lat + rng.uniform(-0.08, 0.08), 6))),
                longitude=Decimal(str(round(lon + rng.uniform(-0.12, 0.12), 6))),
                max_guests=max(1, bedrooms * 2 + rng.randint(0, 2)),
                bedrooms=bedrooms,
                beds=max(1, bedrooms + rng.randint(0, 1)),
                bathrooms=rng.randint(1, 2),
            )
            listing.amenities.set(rng.sample(amenities, k=min(len(amenities), rng.randint(2, 6))))
            services.listing_publish(listing=listing)
            ids.append(str(listing.id))

        token = issue_token_pair(host)["access"]
        self.stdout.write(json.dumps({"host_token": token, "listing_ids": ids}))
