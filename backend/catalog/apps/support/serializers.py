from rest_framework import serializers

from apps.support.models import Message, Ticket, TicketTopic


class MessageSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.first_name", read_only=True)

    class Meta:
        model = Message
        fields = ("id", "text", "from_support", "author_name", "created_at")
        read_only_fields = fields


TICKET_FIELDS = ["id", "topic", "subject", "booking_id", "status", "created_at", "updated_at"]


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = TICKET_FIELDS
        read_only_fields = TICKET_FIELDS


class TicketDetailSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [*TICKET_FIELDS, "messages"]
        read_only_fields = fields


class TicketCreateSerializer(serializers.Serializer):
    topic = serializers.ChoiceField(choices=TicketTopic.choices)
    subject = serializers.CharField(max_length=150)
    text = serializers.CharField(max_length=5000)
    booking_id = serializers.UUIDField(required=False, allow_null=True)


class MessageCreateSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=5000)
