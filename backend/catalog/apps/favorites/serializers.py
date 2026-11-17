from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common import storage
from apps.favorites.models import Favorite


class FavoriteSerializer(serializers.ModelSerializer):
    """The saved listing, with what a card needs. Prices live in Booking."""

    id = serializers.UUIDField(source="listing.id")
    title = serializers.CharField(source="listing.title")
    city = serializers.CharField(source="listing.city")
    country = serializers.CharField(source="listing.country")
    property_type = serializers.CharField(source="listing.property_type")
    rating = serializers.DecimalField(
        source="listing.rating", max_digits=3, decimal_places=2, allow_null=True
    )
    review_count = serializers.IntegerField(source="listing.review_count")
    cover_url = serializers.SerializerMethodField()
    saved_at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = Favorite
        fields = (
            "id",
            "title",
            "city",
            "country",
            "property_type",
            "rating",
            "review_count",
            "cover_url",
            "saved_at",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_cover_url(self, favorite: Favorite) -> str | None:
        photos = favorite.listing.photos.all()  # only ready photos are prefetched
        return storage.public_url(photos[0].thumb_key) if photos else None
