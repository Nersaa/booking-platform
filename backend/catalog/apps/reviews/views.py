from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination
from apps.listings.models import Listing, ListingStatus
from apps.listings.permissions import IsHost
from apps.reviews import services
from apps.reviews.models import Review, ReviewableStay
from apps.reviews.serializers import (
    PendingReviewSerializer,
    ReviewCreateSerializer,
    ReviewReplySerializer,
    ReviewSerializer,
)
from apps.users.auth import authenticated_user


@extend_schema(tags=["reviews"])
class ListingReviewsView(generics.ListAPIView):
    """Reviews of a published listing, newest first."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    serializer_class = ReviewSerializer
    pagination_class = StandardPagination

    def get_queryset(self) -> QuerySet[Review]:
        if getattr(self, "swagger_fake_view", False):
            return Review.objects.none()
        listing = get_object_or_404(
            Listing, pk=self.kwargs["listing_id"], status=ListingStatus.PUBLISHED
        )
        return listing.reviews.select_related("author")


@extend_schema(tags=["reviews"])
class PendingReviewsView(generics.ListAPIView):
    """The user's finished stays that can still be reviewed."""

    permission_classes = (IsAuthenticated,)
    serializer_class = PendingReviewSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[ReviewableStay]:
        if getattr(self, "swagger_fake_view", False):
            return ReviewableStay.objects.none()
        return (
            ReviewableStay.objects.filter(
                guest=authenticated_user(self.request),
                review__isnull=True,
                review_deadline__gte=timezone.localdate(),
            )
            .select_related("listing")
            .order_by("review_deadline")
        )


@extend_schema(tags=["reviews"])
class ReviewCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=ReviewCreateSerializer,
        responses={201: ReviewSerializer},
        summary="Review a finished stay",
    )
    def post(self, request: Request) -> Response:
        serializer = ReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Someone else's booking looks exactly like a missing one.
        stay = get_object_or_404(
            ReviewableStay, pk=data["booking_id"], guest=authenticated_user(request)
        )
        review = services.review_create(stay=stay, rating=data["rating"], text=data["text"])
        return Response(ReviewSerializer(review).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["host listings"])
class HostReviewReplyView(APIView):
    permission_classes = (IsAuthenticated, IsHost)

    @extend_schema(
        request=ReviewReplySerializer,
        responses={200: ReviewSerializer},
        summary="Reply publicly to a review",
    )
    def post(self, request: Request, review_id: str) -> Response:
        serializer = ReviewReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = get_object_or_404(
            Review.objects.select_related("author"),
            pk=review_id,
            listing__host=authenticated_user(request),
        )
        review = services.review_reply(review=review, text=serializer.validated_data["text"])
        return Response(ReviewSerializer(review).data)
