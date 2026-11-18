"""Photos for demo listings, from `demo/photos/` (free Unsplash photos, see CREDITS.md).

Each file goes through the same `render_variants` as a host's upload, once, and its
variants are stored for every listing that gets it. Development and demo data only.
"""

import random
from functools import cache
from pathlib import Path

from django.conf import settings

from apps.common import storage
from apps.listings import images
from apps.listings.models import Listing, ListingPhoto, PhotoStatus

PHOTO_DIR = Path(settings.BASE_DIR) / "demo" / "photos"


def photo_files() -> tuple[list[Path], list[Path]]:
    """Rooms to start a listing with (living, kitchen, dining), and bedrooms."""
    files = sorted(PHOTO_DIR.glob("*.jpg"))
    bedrooms = [f for f in files if f.name.startswith("bedroom")]
    return [f for f in files if f not in bedrooms], bedrooms


@cache
def _variants(path: Path) -> list[images.Variant]:
    return images.render_variants(path.read_bytes())


def add_demo_photos(listing: Listing, rng: random.Random) -> int:
    """Gives the listing 3 to 5 ready photos: a main room first, then bedrooms and more."""
    rooms, bedrooms = photo_files()
    picked = rng.sample(rooms, k=1) + rng.sample(bedrooms, k=min(len(bedrooms), rng.randint(1, 2)))
    extra = [room for room in rooms if room not in picked]
    picked += rng.sample(extra, k=min(len(extra), rng.randint(1, 2)))

    for position, path in enumerate(picked):
        variants = {v.name: v for v in _variants(path)}
        photo = ListingPhoto(
            listing=listing,
            content_type="image/jpeg",
            status=PhotoStatus.READY,
            position=position,
            width=variants["large"].width,
            height=variants["large"].height,
        )
        # Files first, then the row: a ready photo never points to a missing file.
        storage.upload(photo.large_key, variants["large"].data, content_type="image/webp")
        storage.upload(photo.thumb_key, variants["thumb"].data, content_type="image/webp")
        photo.save()
    return len(picked)
