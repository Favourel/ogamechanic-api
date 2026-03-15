from rest_framework import serializers
from .models import (
    ChatRoom, Message, ChatNotification,
    SupportConversation, SupportMessage,
)
from users.serializers import UserSerializer


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model"""

    sender = UserSerializer(read_only=True)
    sender_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "chat_room",
            "sender",
            "sender_id",
            "content",
            "message_type",
            "file_url",
            "created_at",
            "updated_at",
            "read_at",
            "is_deleted",
            "is_read",
        ]
        read_only_fields = ["id", "sender",
                            "created_at", "updated_at", "is_read"]

    def create(self, validated_data):
        sender_id = validated_data.pop("sender_id")
        validated_data["sender_id"] = sender_id
        return super().create(validated_data)


class ChatRoomSerializer(serializers.ModelSerializer):
    """Serializer for ChatRoom model"""

    participants = UserSerializer(many=True, read_only=True)
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True
    )
    last_message = serializers.PrimaryKeyRelatedField(read_only=True)
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id",
            "participants",
            "participant_ids",
            "created_at",
            "updated_at",
            "is_active",
            "last_message",
            "unread_count",
        ]
        read_only_fields = ["id", "participants", "created_at", "updated_at"]

    def get_unread_count(self, obj):
        """Get unread count for the current user"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.unread_count(request.user)
        return 0

    def create(self, validated_data):
        participant_ids = validated_data.pop("participant_ids")
        chat_room = ChatRoom.objects.create(**validated_data)
        chat_room.participants.set(participant_ids)
        return chat_room


class ChatNotificationSerializer(serializers.ModelSerializer):
    """Serializer for ChatNotification model"""

    message = serializers.PrimaryKeyRelatedField(read_only=True)
    chat_room = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = ChatNotification
        fields = ["id", "user", "chat_room",
                  "message", "is_read", "created_at"]
        read_only_fields = ["id", "user", "chat_room", "message", "created_at"]


class ChatRoomListSerializer(serializers.ModelSerializer):
    """Simplified serializer for chat room list"""

    participants = UserSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    other_participant = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id",
            "participants",
            "other_participant",
            "created_at",
            "updated_at",
            "is_active",
            "last_message",
            "unread_count",
        ]

    def get_last_message(self, obj):
        """Get last message preview"""
        last_msg = obj.last_message
        if last_msg:
            return {
                "content": (
                    last_msg.content[:50] + "..."
                    if len(last_msg.content) > 50
                    else last_msg.content
                ),
                "sender_email": last_msg.sender.email,
                "created_at": last_msg.created_at,
                "message_type": last_msg.message_type,
            }
        return None

    def get_unread_count(self, obj):
        """Get unread count for the current user"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.unread_count(request.user)
        return 0

    def get_other_participant(self, obj):
        """Get the other participant in the chat (not the current user)"""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            other_participants = obj.participants.exclude(id=request.user.id)
            if other_participants.exists():
                return UserSerializer(other_participants.first()).data
        return None


# ═══════════════════════════════════════════════════════════════════
# Support Chat Serializers
# ═══════════════════════════════════════════════════════════════════

class SupportMessageSenderSerializer(serializers.Serializer):
    """Lightweight sender representation for messages."""
    id = serializers.UUIDField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    is_staff = serializers.BooleanField()


class SupportMessageSerializer(serializers.ModelSerializer):
    """Serializer for SupportMessage model."""

    sender = SupportMessageSenderSerializer(read_only=True)
    file_attachment_url = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage
        fields = [
            "id",
            "conversation",
            "sender",
            "content",
            "message_type",
            "file_attachment",
            "file_attachment_url",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = [
            "id", "sender", "is_read", "read_at", "created_at",
            "file_attachment_url",
        ]

    def get_file_attachment_url(self, obj):
        if obj.file_attachment:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file_attachment.url)
            return obj.file_attachment.url
        return None


class SupportConversationSerializer(serializers.ModelSerializer):
    """Full detail serializer for SupportConversation."""

    customer = SupportMessageSenderSerializer(read_only=True)
    assigned_admin = SupportMessageSenderSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = SupportConversation
        fields = [
            "id",
            "customer",
            "assigned_admin",
            "subject",
            "status",
            "priority",
            "created_at",
            "updated_at",
            "resolved_at",
            "last_message",
            "unread_count",
        ]
        read_only_fields = [
            "id", "customer", "assigned_admin", "created_at",
            "updated_at", "resolved_at",
        ]

    def get_last_message(self, obj):
        msg = obj.last_message
        if msg:
            return {
                "content": (
                    msg.content[:80] + "..."
                    if len(msg.content) > 80
                    else msg.content
                ),
                "sender_email": msg.sender.email,
                "sender_is_staff": msg.sender.is_staff,
                "message_type": msg.message_type,
                "created_at": msg.created_at.isoformat(),
            }
        return None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.unread_count_for(request.user)
        return 0


class SupportConversationListSerializer(serializers.ModelSerializer):
    """Compact list serializer for support conversations."""

    customer = SupportMessageSenderSerializer(read_only=True)
    assigned_admin = SupportMessageSenderSerializer(
        read_only=True, allow_null=True
    )
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = SupportConversation
        fields = [
            "id",
            "customer",
            "assigned_admin",
            "subject",
            "status",
            "priority",
            "created_at",
            "updated_at",
            "last_message",
            "unread_count",
        ]

    def get_last_message(self, obj):
        msg = obj.last_message
        if msg:
            return {
                "content": (
                    msg.content[:50] + "..."
                    if len(msg.content) > 50
                    else msg.content
                ),
                "sender_email": msg.sender.email,
                "created_at": msg.created_at.isoformat(),
            }
        return None

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.unread_count_for(request.user)
        return 0


class SupportConversationCreateSerializer(serializers.Serializer):
    """Serializer for creating a new support conversation."""

    subject = serializers.CharField(max_length=255)
    message = serializers.CharField(help_text="Initial message content.")
    priority = serializers.ChoiceField(
        choices=["low", "medium", "high", "urgent"],
        default="medium",
    )


class SupportFileUploadSerializer(serializers.Serializer):
    """Serializer for file upload validation."""

    file = serializers.FileField()

    def validate_file(self, value):
        # 10 MB limit
        max_size = 10 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                "File size exceeds 10 MB limit."
            )

        allowed_types = [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(
                "Unsupported file type. Allowed: JPEG, PNG, GIF, WebP, PDF, DOC, DOCX."  # noqa
            )
        return value
