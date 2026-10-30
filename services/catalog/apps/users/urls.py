from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from apps.users import views

urlpatterns = [
    path("auth/register", views.RegisterView.as_view(), name="auth-register"),
    path("auth/token", views.LoginView.as_view(), name="auth-token"),
    path("auth/token/refresh", TokenRefreshView.as_view(), name="auth-token-refresh"),
    path("auth/logout", TokenBlacklistView.as_view(), name="auth-logout"),
    path("users/me", views.MeView.as_view(), name="users-me"),
    path("users/me/host", views.BecomeHostView.as_view(), name="users-me-host"),
]
