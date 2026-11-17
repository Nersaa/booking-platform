from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.favorites.models import Favorite
from apps.favorites.serializers import FavoriteSerializer
from apps.listings import selectors
from apps.listings.models import ListingPhoto, ListingStatus, PhotoStatus
from apps.users.auth import authenticated_user


@extend_schema(tags=["favorites"])
class FavoriteListView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: FavoriteSerializer(many=True)}, summary="Saved listings")
    def get(self, request: Request) -> Response:
        ready_photos = ListingPhoto.objects.filter(status=PhotoStatus.READY)
        favorites = (
            Favorite.objects.filter(
                user=authenticated_user(request), listing__status=ListingStatus.PUBLISHED
            )
            .select_related("listing")
            .prefetch_related(Prefetch("listing__photos", queryset=ready_photos))
        )
        return Response(FavoriteSerializer(favorites, many=True).data)


@extend_schema(tags=["favorites"])
class FavoriteDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={204: None}, summary="Save a listing")
    def put(self, request: Request, listing_id: str) -> Response:
        listing = get_object_or_404(selectors.published_listings(), pk=listing_id)
        # Saving twice is fine: the result is the same.
        Favorite.objects.get_or_create(user=authenticated_user(request), listing=listing)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses={204: None}, summary="Remove a saved listing")
    def delete(self, request: Request, listing_id: str) -> Response:
        Favorite.objects.filter(user=authenticated_user(request), listing_id=listing_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
