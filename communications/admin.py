from django.contrib import admin
from .models import ChatRoom, Message, ChatNotification, CallSession


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
