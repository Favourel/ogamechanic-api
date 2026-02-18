import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ChatRoom(models.Model):
    """
    Chat room model for 1-on-1 conversations between users
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    participants = models.ManyToManyField(User, related_name="chat_rooms")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        participant_names = [user.email for user in self.participants.all()]
        return f"Chat between {', '.join(participant_names)}"

    @property
    def last_message(self):
        """Get the last message in this chat room"""
        return self.messages.order_by("-created_at").first()

    @property
    def unread_count(self, user):
        """Get unread message count for a specific user"""
        return self.messages.filter(
            sender__in=self.participants.exclude(id=user.id),
            read_at__isnull=True
        ).count()


class Message(models.Model):
    """
    Individual message model within a chat room
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat_room = models.ForeignKey(
        ChatRoom, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_messages"
    )
    content = models.TextField()
    message_type = models.CharField(
        max_length=20,
        choices=[
            ("text", "Text"),
            ("image", "Image"),
            ("file", "File"),
            ("system", "System Message"),
        ],
        default="text",
    )
    file_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    read_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender.email}: {self.content[:50]}..."

    def mark_as_read(self, user):
        """Mark message as read by a specific user"""
        if self.sender != user and not self.read_at:
            self.read_at = timezone.now()
            self.save()

    @property
    def is_read(self):
        """Check if message has been read"""
        return self.read_at is not None


class ChatNotification(models.Model):
    """
    Notification model for chat-related notifications
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="chat_notifications"
    )
    chat_room = models.ForeignKey(
        ChatRoom, on_delete=models.CASCADE, related_name="notifications"
    )
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="notifications"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["user", "message"]

    def __str__(self):
        return (
            f"Notification for {self.user.email} - " f"{self.message.content[:30]}..." # noqa
        )


class CallSession(models.Model):
    """
    Model for tracking VoIP call sessions and signaling
    """

    STATUS_CHOICES = [
        ("ringing", "Ringing"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("ended", "Ended"),
        ("missed", "Missed"),
        ("busy", "Busy"),
        ("failed", "Failed"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    caller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="calls_made"
    )
    callee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="calls_received"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default="ringing")
    signaling_data = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Call {self.id} from {self.caller.email} to {self.callee.email} ({self.status})" # noqa

    @property
    def duration(self):
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
