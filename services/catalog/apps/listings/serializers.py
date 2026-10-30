from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from apps.common import storage
from apps.listings.models import Amenity, Listing, ListingPhoto, PhotoStatus
from apps.listings.services import ALLOWED_PHOTO_TYPES


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ("code", "name")


class PhotoSerializer(serializers.ModelSerializer):
    large_url = serializers.SerializerMethodField()
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = ListingPhoto
        fields = ("id", "status", "position", "width", "height", "large_url", "thumb_url")

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_large_url(self, photo: ListingPhoto) -> str | None:
        return storage.public_url(photo.large_key) if photo.status == PhotoStatus.READY else None

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumb_url(self, photo: ListingPhoto) -> str | None:
        return storage.public_url(photo.thumb_key) if photo.status == PhotoStatus.READY else None


class ListingWriteSerializer(serializers.ModelSerializer):
    amenities = serializers.SlugRelatedField(
        slug_field="code", queryset=Amenity.objects.all(), many=True, required=False
    )

    class Meta:
        model = Listing
        fields = (
            "title",
            "description",
            "property_type",
            "country",
            "city",
            "address",
            "latitude",
            "longitude",
            "max_guests",
            "bedrooms",
            "beds",
            "bathrooms",
            "amenities",
        )

    def validate_country(self, value: str) -> str:
        if len(value) != 2 or not value.isalpha():
            raise serializers.ValidationError("Use an ISO 3166-1 alpha-2 country code.")
        return value.upper()


class HostListingSerializer(serializers.ModelSerializer):
    amenities = AmenitySerializer(many=True)
    photos = PhotoSerializer(many=True)

    class Meta:
        model = Listing
        fields = (
            "id",
            "status",
            "rejection_reason",
            *ListingWriteSerializer.Meta.fields,
            "photos",
            "published_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class HostSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    first_name = serializers.CharField()


class PublicListingSerializer(serializers.ModelSerializer):
    host = HostSummarySerializer()
    amenities = AmenitySerializer(many=True)
    photos = PhotoSerializer(many=True)

    class Meta:
        model = Listing
        fields = (
            "id",
            "host",
            *ListingWriteSerializer.Meta.fields,
            "photos",
            "published_at",
        )
        read_only_fields = fields


class PhotoUploadRequestSerializer(serializers.Serializer):
    content_type = serializers.ChoiceField(choices=ALLOWED_PHOTO_TYPES)


class PhotoUploadResponseSerializer(serializers.Serializer):
    photo = PhotoSerializer()
    # Built inline: a declared field called `fields` would shadow Serializer.fields.
    upload = inline_serializer(
        name="PresignedUpload",
        fields={
            "url": serializers.URLField(),
            "fields": serializers.DictField(child=serializers.CharField()),
            "expires_in": serializers.IntegerField(),
        },
    )
