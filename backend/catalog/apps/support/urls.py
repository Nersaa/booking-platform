from django.urls import path

from apps.support import views

urlpatterns = [
    path("support/tickets", views.TicketListView.as_view(), name="support-tickets"),
    path(
        "support/tickets/<uuid:ticket_id>",
        views.TicketDetailView.as_view(),
        name="support-ticket",
    ),
    path(
        "support/tickets/<uuid:ticket_id>/messages",
        views.TicketMessagesView.as_view(),
        name="support-ticket-messages",
    ),
    path(
        "support/tickets/<uuid:ticket_id>/close",
        views.TicketCloseView.as_view(),
        name="support-ticket-close",
    ),
]
