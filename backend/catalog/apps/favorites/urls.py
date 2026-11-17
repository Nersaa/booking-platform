from django.urls import path

from apps.favorites import views

urlpatterns = [
    path("favorites", views.FavoriteListView.as_view(), name="favorites"),
    path("favorites/<uuid:listing_id>", views.FavoriteDetailView.as_view(), name="favorite"),
]
