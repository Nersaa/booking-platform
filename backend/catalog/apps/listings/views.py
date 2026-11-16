from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination
from apps.listings import cache, selectors, services
from apps.listings.models import Amenity, Listing, ListingPhoto
from apps.listings.permissions import IsHost
from apps.listings.serializers import (
    AmenitySerializer,
    HostListingSerializer,
    ListingWriteSerializer,
    PhotoSerializer,
    PhotoUploadRequestSerializer,
    PhotoUploadResponseSerializer,
    PublicListingSerializer,
)
from apps.listings.services import UPLOAD_URL_TTL_SECONDS
from apps.users.auth import authenticated_user


class AmenityListView(generics.ListAPIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    serializer_class = AmenitySerializer
    queryset = Amenity.objects.all()
    pagination_class = None


class PublicListingDetailView(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    serializer_class = PublicListingSerializer

    def get_queryset(self) -> QuerySet[Listing]:
        return selectors.published_listings()

    def retrieve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        listing_id = kwargs["pk"]
        data = cache.get_public_listing(listing_id)
        if data is None:
            data = self.get_serializer(self.get_object()).data
            cache.set_public_listing(listing_id, data)
        return Response(data)


@extend_schema(tags=["host listings"])
class HostListingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Listings of the authenticated host. Other hosts' listings are invisible (404)."""

    permission_classes = (IsAuthenticated, IsHost)
    serializer_class = HostListingSerializer
    pagination_class = StandardPagination
    filterset_fields = ("status",)

    def get_queryset(self) -> QuerySet[Listing]:
        if getattr(self, "swagger_fake_view", False):
            return Listing.objects.none()
        return selectors.host_listings(host=authenticated_user(self.request))

    def _render(self, listing: Listing, code: int = status.HTTP_200_OK) -> Response:
        listing = self.get_queryset().get(pk=listing.pk)
        return Response(HostListingSerializer(listing).data, status=code)

    @extend_schema(request=ListingWriteSerializer, responses={201: HostListingSerializer})
    def create(self, request: Request) -> Response:
        serializer = ListingWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = services.listing_create(
            host=authenticated_user(request), **serializer.validated_data
        )
        return self._render(listing, status.HTTP_201_CREATED)

    @extend_schema(request=ListingWriteSerializer, responses={200: HostListingSerializer})
    def partial_update(self, request: Request, pk: str) -> Response:
        serializer = ListingWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        listing = services.listing_update(listing=self.get_object(), **serializer.validated_data)
        return self._render(listing)

    def destroy(self, request: Request, pk: str) -> Response:
        services.listing_delete(listing=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses={200: HostListingSerializer})
    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: str) -> Response:
        listing = services.listing_submit_for_review(listing=self.get_object())
        return self._render(listing)

    @extend_schema(request=None, responses={200: HostListingSerializer})
    @action(detail=True, methods=["post"])
    def archive(self, request: Request, pk: str) -> Response:
        listing = services.listing_archive(listing=self.get_object())
        return Response(HostListingSerializer(listing).data)


@extend_schema(tags=["host listings"])
class HostListingPhotosView(APIView):
    permission_classes = (IsAuthenticated, IsHost)

    @extend_schema(
        request=PhotoUploadRequestSerializer,
        responses={201: PhotoUploadResponseSerializer},
        summary="Start a direct upload to object storage",
    )
    def post(self, request: Request, listing_id: str) -> Response:
        serializer = PhotoUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        listing = get_object_or_404(Listing, pk=listing_id, host=request.user)
        photo, upload = services.photo_request_upload(
            listing=listing, content_type=serializer.validated_data["content_type"]
        )
        body = {
            "photo": PhotoSerializer(photo).data,
            "upload": {**upload, "expires_in": UPLOAD_URL_TTL_SECONDS},
        }
        return Response(body, status=status.HTTP_201_CREATED)


@extend_schema(tags=["host listings"])
class HostListingPhotoDetailView(APIView):
    permission_classes = (IsAuthenticated, IsHost)

    def _get_photo(self, request: Request, listing_id: str, photo_id: str) -> ListingPhoto:
        listing = get_object_or_404(Listing, pk=listing_id, host=request.user)
        return get_object_or_404(listing.photos.select_related("listing"), pk=photo_id)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, listing_id: str, photo_id: str) -> Response:
        services.photo_delete(photo=self._get_photo(request, listing_id, photo_id))
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["host listings"])
class HostListingPhotoCompleteView(HostListingPhotoDetailView):
    @extend_schema(request=None, responses={202: PhotoSerializer}, summary="Confirm the upload")
    def post(self, request: Request, listing_id: str, photo_id: str) -> Response:
        photo = services.photo_confirm_upload(photo=self._get_photo(request, listing_id, photo_id))
        return Response(PhotoSerializer(photo).data, status=status.HTTP_202_ACCEPTED)
