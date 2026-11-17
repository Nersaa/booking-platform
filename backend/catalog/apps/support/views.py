from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.pagination import StandardPagination
from apps.support import services
from apps.support.models import Ticket
from apps.support.serializers import (
    MessageCreateSerializer,
    MessageSerializer,
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketSerializer,
)
from apps.users.auth import authenticated_user


def _own_ticket(request: Request, ticket_id: str) -> Ticket:
    # Someone else's ticket looks exactly like a missing one.
    return get_object_or_404(
        Ticket.objects.prefetch_related("messages__author"),
        pk=ticket_id,
        user=authenticated_user(request),
    )


@extend_schema(tags=["support"])
class TicketListView(ListAPIView):
    """The user's support requests, recently updated first."""

    permission_classes = (IsAuthenticated,)
    serializer_class = TicketSerializer
    pagination_class = StandardPagination

    def get_queryset(self) -> QuerySet[Ticket]:
        if getattr(self, "swagger_fake_view", False):
            return Ticket.objects.none()
        return Ticket.objects.filter(user=authenticated_user(self.request))

    @extend_schema(
        request=TicketCreateSerializer,
        responses={201: TicketDetailSerializer},
        summary="Open a support request",
    )
    def post(self, request: Request) -> Response:
        serializer = TicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = services.ticket_open(user=authenticated_user(request), **serializer.validated_data)
        return Response(TicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["support"])
class TicketDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(responses={200: TicketDetailSerializer}, summary="A request with its messages")
    def get(self, request: Request, ticket_id: str) -> Response:
        return Response(TicketDetailSerializer(_own_ticket(request, ticket_id)).data)


@extend_schema(tags=["support"])
class TicketMessagesView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        request=MessageCreateSerializer,
        responses={201: MessageSerializer},
        summary="Write to support",
    )
    def post(self, request: Request, ticket_id: str) -> Response:
        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = services.ticket_add_message(
            ticket=_own_ticket(request, ticket_id),
            user=authenticated_user(request),
            text=serializer.validated_data["text"],
        )
        return Response(MessageSerializer(message).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["support"])
class TicketCloseView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(request=None, responses={200: TicketSerializer}, summary="Close a request")
    def post(self, request: Request, ticket_id: str) -> Response:
        ticket = services.ticket_close(ticket=_own_ticket(request, ticket_id))
        return Response(TicketSerializer(ticket).data)
