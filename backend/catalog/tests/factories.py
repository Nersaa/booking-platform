import io
from decimal import Decimal
from typing import Any

import factory
from factory.django import DjangoModelFactory
from PIL import Image

from apps.listings.models import Listing, ListingPhoto, ListingStatus, PhotoStatus, PropertyType
from apps.users.models import User

DEFAULT_PASSWORD = "Str0ng-passw0rd!"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Alex"
    last_name = "Smith"

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        password = kwargs.pop("password", DEFAULT_PASSWORD)
        return model_class.objects.create_user(password=password, **kwargs)


class HostFactory(UserFactory):
    is_host = True


class ListingFactory(DjangoModelFactory):
    class Meta:
        model = Listing

    host = factory.SubFactory(HostFactory)
    title = factory.Sequence(lambda n: f"Sunny apartment #{n}")
    description = "Bright two-room apartment near the old town."
    property_type = PropertyType.APARTMENT
    status = ListingStatus.DRAFT
    country = "PT"
    city = "Lisbon"
    address = "Rua Augusta 100"
    latitude = Decimal("38.710000")
    longitude = Decimal("-9.137000")
    max_guests = 4
    bedrooms = 2
    beds = 2
    bathrooms = 1


class PhotoFactory(DjangoModelFactory):
    class Meta:
        model = ListingPhoto

    listing = factory.SubFactory(ListingFactory)
    content_type = "image/jpeg"
    status = PhotoStatus.READY
    width = 1600
    height = 1200


def make_image(size: tuple[int, int] = (1200, 900), fmt: str = "JPEG") -> bytes:
    image = Image.new("RGB", size, color=(30, 120, 200))
    exif = Image.Exif()
    exif[0x010F] = "TestCamera"  # Make
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, exif=exif)
    return buffer.getvalue()
