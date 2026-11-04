from django.urls import path

from apps.reviews import views

urlpatterns = [
    path(
        "listings/<uuid:listing_id>/reviews",
        views.ListingReviewsView.as_view(),
        name="listing-reviews",
    ),
    path("reviews", views.ReviewCreateView.as_view(), name="reviews"),
    path("reviews/pending", views.PendingReviewsView.as_view(), name="reviews-pending"),
    path(
        "host/reviews/<uuid:review_id>/reply",
        views.HostReviewReplyView.as_view(),
        name="host-review-reply",
    ),
]
