from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.listings import views

router = SimpleRouter(trailing_slash=False)
router.register("host/listings", views.HostListingViewSet, basename="host-listings")

urlpatterns = [
    path("amenities", views.AmenityListView.as_view(), name="amenities"),
    path("listings/<uuid:pk>", views.PublicListingDetailView.as_view(), name="listing-detail"),
    path(
        "host/listings/<uuid:listing_id>/photos",
        views.HostListingPhotosView.as_view(),
        name="host-listing-photos",
    ),
    path(
        "host/listings/<uuid:listing_id>/photos/<uuid:photo_id>",
        views.HostListingPhotoDetailView.as_view(),
        name="host-listing-photo",
    ),
    path(
        "host/listings/<uuid:listing_id>/photos/<uuid:photo_id>/complete",
        views.HostListingPhotoCompleteView.as_view(),
        name="host-listing-photo-complete",
    ),
    *router.urls,
]
