from typing import Any

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt import serializers as jwt_serializers

from apps.users.models import User
from apps.users.tokens import RefreshToken


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "is_host", "date_joined")
        read_only_fields = ("id", "email", "is_host", "date_joined")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, required=False, default="")

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        candidate = User(email=attrs["email"], first_name=attrs["first_name"])
        validate_password(attrs["password"], user=candidate)
        return attrs


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class BecomeHostResponseSerializer(TokenPairSerializer):
    user = UserSerializer()


class TokenObtainPairSerializer(jwt_serializers.TokenObtainPairSerializer):
    token_class = RefreshToken


class TokenRefreshSerializer(jwt_serializers.TokenRefreshSerializer):
    token_class = RefreshToken


class TokenBlacklistSerializer(jwt_serializers.TokenBlacklistSerializer):
    token_class = RefreshToken
