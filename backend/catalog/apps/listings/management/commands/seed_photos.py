"""Adds demo photos to listings that have none, e.g. ones seeded before photos existed."""

import random
from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand

from apps.listings import services
from apps.listings.demo_photos import add_demo_photos
from apps.listings.models import Listing, PhotoStatus


class Command(BaseCommand):
    help = "Give every listing without photos 3 to 5 demo photos (development only)."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--seed", type=int, default=42, help="Same seed, same photos.")

    def handle(self, *args: Any, **options: Any) -> None:
        rng = random.Random(options["seed"])
        without_photos = Listing.objects.exclude(photos__status=PhotoStatus.READY)
        without_photos = without_photos.order_by("created_at")
        done = 0
        for listing in without_photos:
            add_demo_photos(listing, rng)
            services.listing_announce_change(listing=listing)  # new cover in search results
            done += 1
        self.stdout.write(f"Added photos to {done} listing(s).")
