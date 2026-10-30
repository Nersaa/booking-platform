from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.users import services
from apps.users.auth import authenticated_user
from apps.users.keys import jwks
from apps.users.models import User
from apps.users.serializers import (
    BecomeHostResponseSerializer,
    RegisterSerializer,
    UserSerializer,
)
from apps.users.tokens import issue_token_pair


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth"

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer}, tags=["auth"])
    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.user_register(**serializer.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    throttle_classes = (ScopedRateThrottle,)
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    http_method_names = ["get", "patch"]

    def get_object(self) -> User:
        return authenticated_user(self.request)


class BecomeHostView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: BecomeHostResponseSerializer}, tags=["users"])
    def post(self, request: Request) -> Response:
        """Grant the host role and return tokens that already carry it."""
        user = services.user_become_host(user=authenticated_user(request))
        return Response({"user": UserSerializer(user).data, **issue_token_pair(user)})


@extend_schema(exclude=True)
class JWKSView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def get(self, request: Request) -> Response:
        response = Response(jwks())
        response["Cache-Control"] = "public, max-age=300"
        return response
