from rest_framework import serializers

from apps.listings.models import Listing
from apps.reviews.models import Review, ReviewableStay
from apps.users.models import User


class ReviewAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "first_name")


class ReviewSerializer(serializers.ModelSerializer):
    author = ReviewAuthorSerializer()

    class Meta:
        model = Review
        fields = ("id", "rating", "text", "author", "host_reply", "host_replied_at", "created_at")
        read_only_fields = fields


class ReviewCreateSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    text = serializers.CharField(max_length=2000)


class ReviewReplySerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class StayListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ("id", "title", "city")


class PendingReviewSerializer(serializers.ModelSerializer):
    listing = StayListingSerializer()

    class Meta:
        model = ReviewableStay
        fields = ("booking_id", "listing", "check_in", "check_out", "review_deadline")
        read_only_fields = fields
