from django.contrib import admin
from .models import (
    ChatRoom, Message, ChatNotification, CallSession,
    SupportConversation, SupportMessage,
)


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "updated_at",
                    "is_active", "participant_count"]
    list_filter = ["is_active", "created_at", "updated_at"]
    search_fields = [
        "participants__email",
        "participants__first_name",
        "participants__last_name",
    ]
    readonly_fields = ["id", "created_at", "updated_at"]
    filter_horizontal = ["participants"]

    def participant_count(self, obj):
        return obj.participants.count()

    participant_count.short_description = "Participants"


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = [
        "sender",
        "chat_room",
        "message_type",
        "content_preview",
        "created_at",
        "is_read",
        "is_deleted",
    ]
    list_filter = ["message_type", "created_at", "read_at", "is_deleted"]
    search_fields = ["sender__email", "content", "chat_room__id"]
    readonly_fields = ["id", "created_at", "updated_at"]
    date_hierarchy = "created_at"
    autocomplete_fields = ("sender",)
    list_per_page = 15

    def content_preview(self, obj):
        return (
            obj.content[:50] + "..."
            if len(obj.content) > 50
            else obj.content
        )

    content_preview.short_description = "Content Preview"


@admin.register(ChatNotification)
class ChatNotificationAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user",
        "chat_room",
        "message_preview",
        "is_read",
        "created_at",
    ]
    list_filter = ["is_read", "created_at"]
    search_fields = ["user__email", "message__content"]
    readonly_fields = ["id", "created_at"]
    date_hierarchy = "created_at"

    def message_preview(self, obj):
        return (
            obj.message.content[:30] + "..."
            if len(obj.message.content) > 30
            else obj.message.content
        )

    message_preview.short_description = "Message Preview"


@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'caller', 'callee', 'status', 'started_at', 'ended_at', 'duration'
    ]
    list_filter = ['status', 'started_at', 'ended_at']
    search_fields = ['caller__email', 'callee__email', 'id']
    readonly_fields = ['id', 'started_at', 'ended_at', 'duration']
    date_hierarchy = 'started_at'
    list_per_page = 25

    def duration(self, obj):
        return obj.duration
    duration.short_description = 'Duration (s)'


@admin.register(SupportConversation)
class SupportConversationAdmin(admin.ModelAdmin):
    list_display = [
        "id", "subject", "customer", "assigned_admin",
        "status", "priority", "created_at", "updated_at",
    ]
    list_filter = ["status", "priority", "created_at"]
    search_fields = [
        "subject", "customer__email", "customer__first_name",
        "assigned_admin__email",
    ]
    readonly_fields = ["id", "created_at", "updated_at", "resolved_at"]
    autocomplete_fields = ("customer", "assigned_admin")
    list_per_page = 25
    date_hierarchy = "created_at"


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = [
        "id", "conversation_subject", "sender", "message_type",
        "content_preview", "is_read", "created_at",
    ]
    list_filter = ["message_type", "is_read", "created_at"]
    search_fields = ["sender__email", "content", "conversation__subject"]
    readonly_fields = ["id", "created_at", "read_at"]
    autocomplete_fields = ("sender", "conversation")
    list_per_page = 25
    date_hierarchy = "created_at"

    def conversation_subject(self, obj):
        return obj.conversation.subject[:40]
    conversation_subject.short_description = "Conversation"

    def content_preview(self, obj):
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content
    content_preview.short_description = "Content"
