from rest_framework import status, parsers
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ogamechanic.modules.utils import (
    get_incoming_request_checks,
    incoming_request_checks,
    api_response,
)
from ogamechanic.modules.paginations import CustomLimitOffsetPagination
from .models import ChatRoom, Message, ChatNotification
from .serializers import (
    ChatRoomSerializer,
    ChatRoomListSerializer,
    MessageSerializer,
    ChatNotificationSerializer,
    SupportFileUploadSerializer,
)


class ChatRoomListView(APIView):
    """List and create chat rooms"""

    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List all chat rooms for the authenticated user",
        responses={200: ChatRoomListSerializer(many=True)},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get chat rooms where user is a participant
        chat_rooms = ChatRoom.objects.filter(
            participants=request.user, is_active=True
        ).prefetch_related("participants", "messages")

        # Apply pagination
        paginator = self.pagination_class()
        paginated_rooms = paginator.paginate_queryset(chat_rooms, request)

        serializer = ChatRoomListSerializer(
            paginated_rooms, many=True, context={"request": request}
        )

        return paginator.get_paginated_response(
            api_response(
                message="Chat rooms retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Create a new chat room with participants",
        request_body=ChatRoomSerializer,
        responses={201: ChatRoomSerializer()},
    )
    def post(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Ensure current user is included in participants
        participant_ids = data.get("participant_ids", [])
        if str(request.user.id) not in [str(pid) for pid in participant_ids]:
            participant_ids.append(str(request.user.id))

        # Check if chat room already exists with these participants
        existing_room = ChatRoom.objects.filter(
            participants__id__in=participant_ids, is_active=True
        ).distinct()

        # Filter to rooms that have exactly the same participants
        for room in existing_room:
            room_participants = set(room.participants.values_list("id", flat=True))  # noqa
            requested_participants = set(participant_ids)
            if room_participants == requested_participants:
                serializer = ChatRoomSerializer(room, context={"request": request})  # noqa
                return Response(
                    api_response(
                        message="Chat room already exists.",
                        status=True,
                        data=serializer.data,
                    ),
                    status=status.HTTP_200_OK,
                )

        # Create new chat room
        serializer = ChatRoomSerializer(
            data={"participant_ids": participant_ids}, context={"request": request}  # noqa
        )

        if serializer.is_valid():
            chat_room = serializer.save()
            print(chat_room)
            return Response(
                api_response(
                    message="Chat room created successfully.",
                    status=True,
                    data=serializer.data,
                ),
                status=status.HTTP_201_CREATED,
            )

        return Response(
            api_response(message=serializer.errors, status=False),
            status=status.HTTP_400_BAD_REQUEST,
        )


class ChatRoomDetailView(APIView):
    """Retrieve, update, and delete chat room details"""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get chat room details",
        responses={200: ChatRoomSerializer()},
    )
    def get(self, request, chat_room_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat_room = get_object_or_404(
            ChatRoom, id=chat_room_id, participants=request.user, is_active=True  # noqa
        )

        serializer = ChatRoomSerializer(chat_room, context={"request": request})  # noqa
        return Response(
            api_response(
                message="Chat room details retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Update chat room (mark as inactive)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "is_active": openapi.Schema(
                    type=openapi.TYPE_BOOLEAN,
                    description="Set to false to deactivate chat room",
                )
            },
        ),
        responses={200: ChatRoomSerializer()},
    )
    def patch(self, request, chat_room_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        chat_room = get_object_or_404(
            ChatRoom, id=chat_room_id, participants=request.user
        )

        # Only allow deactivating the chat room
        if "is_active" in data:
            chat_room.is_active = data["is_active"]
            chat_room.save()

        serializer = ChatRoomSerializer(chat_room, context={"request": request})  # noqa
        return Response(
            api_response(
                message="Chat room updated successfully.",
                status=True,
                data=serializer.data,
            )
        )


class MessageListView(APIView):
    """List and create messages in a chat room"""

    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List messages in a chat room",
        manual_parameters=[
            openapi.Parameter(
                "chat_room_id",
                openapi.IN_PATH,
                description="Chat room ID",
                type=openapi.TYPE_STRING,
                required=True,
            )
        ],
        responses={200: MessageSerializer(many=True)},
    )
    def get(self, request, chat_room_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify user is participant in chat room
        chat_room = get_object_or_404(
            ChatRoom, id=chat_room_id, participants=request.user, is_active=True  # noqa
        )

        # Get messages
        messages = Message.objects.filter(
            chat_room=chat_room, is_deleted=False
        ).select_related("sender")

        # Apply pagination
        paginator = self.pagination_class()
        paginated_messages = paginator.paginate_queryset(messages, request)

        serializer = MessageSerializer(paginated_messages, many=True)

        return paginator.get_paginated_response(
            api_response(
                message="Messages retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Send a message in a chat room",
        request_body=MessageSerializer,
        responses={201: MessageSerializer()},
    )
    def post(self, request, chat_room_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify user is participant in chat room
        chat_room = get_object_or_404(
            ChatRoom, id=chat_room_id, participants=request.user, is_active=True  # noqa
        )

        # Add chat room and sender to data
        data["chat_room"] = chat_room_id
        data["sender_id"] = str(request.user.id)

        serializer = MessageSerializer(data=data)
        if serializer.is_valid():
            message = serializer.save()

            print(message)
            # Update chat room's updated_at timestamp
            chat_room.updated_at = timezone.now()
            chat_room.save()

            return Response(
                api_response(
                    message="Message sent successfully.",
                    status=True,
                    data=serializer.data,
                ),
                status=status.HTTP_201_CREATED,
            )

        return Response(
            api_response(
                message=(
                    ", ".join(
                        [
                            f"{field}: {', '.join(errors)}"
                            for field, errors in serializer.errors.items()
                        ]  # noqa
                    )
                    if serializer.errors
                    else "Invalid data"
                ),
                status=False,
                errors=serializer.errors,
            ),
            status=status.HTTP_400_BAD_REQUEST,
        )


class MessageDetailView(APIView):
    """Retrieve, update, and delete individual messages"""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get message details",
        responses={200: MessageSerializer()},
    )
    def get(self, request, chat_room_id, message_id):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = get_object_or_404(
            Message,
            id=message_id,
            chat_room_id=chat_room_id,
            chat_room__participants=request.user,
            is_deleted=False,
        )

        serializer = MessageSerializer(message)
        return Response(
            api_response(
                message="Message details retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Update message content",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "content": openapi.Schema(
                    type=openapi.TYPE_STRING, description="Updated message content"  # noqa
                )
            },
        ),
        responses={200: MessageSerializer()},
    )
    def patch(self, request, chat_room_id, message_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = get_object_or_404(
            Message,
            id=message_id,
            chat_room_id=chat_room_id,
            sender=request.user,
            is_deleted=False,
        )

        # Only allow updating content
        if "content" in data:
            message.content = data["content"]
            message.save()

        serializer = MessageSerializer(message)
        return Response(
            api_response(
                message="Message updated successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Delete a message (soft delete)",
        responses={204: "Message deleted successfully"},
    )
    def delete(self, request, chat_room_id, message_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = get_object_or_404(
            Message,
            id=message_id,
            chat_room_id=chat_room_id,
            sender=request.user,
            is_deleted=False,
        )

        # Soft delete
        message.is_deleted = True
        message.save()

        return Response(
            api_response(message="Message deleted successfully.",
            status=True, data={}),  # noqa
            status=status.HTTP_204_NO_CONTENT,
        )


class MarkMessagesReadView(APIView):
    """Mark messages as read"""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Mark messages as read",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["message_ids"],
            properties={
                "message_ids": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description="List of message IDs to mark as read",
                )
            },
        ),
        responses={200: "Messages marked as read"},
    )
    def post(self, request, chat_room_id):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        message_ids = data.get("message_ids", [])
        if not message_ids:
            return Response(
                api_response(message="No message IDs provided.", status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify user is participant in chat room
        chat_room = get_object_or_404(
            ChatRoom, id=chat_room_id, participants=request.user, is_active=True  # noqa
        )

        # Mark messages as read
        messages = Message.objects.filter(
            id__in=message_ids,
            chat_room=chat_room,
            sender__in=chat_room.participants.exclude(id=request.user.id),
            read_at__isnull=True,
        )

        updated_count = messages.update(read_at=timezone.now())

        return Response(
            api_response(
                message=f"{updated_count} messages marked as read.",
                status=True,
                data={"updated_count": updated_count},
            )
        )


class ChatNotificationListView(APIView):
    """List chat notifications for the authenticated user"""

    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List chat notifications for the user",
        responses={200: ChatNotificationSerializer(many=True)},
    )
    def get(self, request):
        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        notifications = ChatNotification.objects.filter(
            user=request.user
        ).select_related("chat_room", "message", "message__sender")

        # Apply pagination
        paginator = self.pagination_class()
        paginated_notifications = paginator.paginate_queryset(notifications, request)  # noqa

        serializer = ChatNotificationSerializer(paginated_notifications, many=True)  # noqa

        return paginator.get_paginated_response(
            api_response(
                message="Notifications retrieved successfully.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Mark notifications as read",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "notification_ids": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_STRING),
                    description="List of notification IDs to mark as read",
                )
            },
        ),
        responses={200: "Notifications marked as read"},
    )
    def patch(self, request):
        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        notification_ids = data.get("notification_ids", [])
        if notification_ids:
            # Mark specific notifications as read
            notifications = ChatNotification.objects.filter(
                id__in=notification_ids, user=request.user
            )
            updated_count = notifications.update(is_read=True)
        else:
            # Mark all notifications as read
            notifications = ChatNotification.objects.filter(
                user=request.user, is_read=False
            )
            updated_count = notifications.update(is_read=True)

        return Response(
            api_response(
                message=f"{updated_count} notifications marked as read.",
                status=True,
                data={"updated_count": updated_count},
            )
        )


# ═══════════════════════════════════════════════════════════════════════
# Support Chat Views
# ═══════════════════════════════════════════════════════════════════════

class SupportConversationListView(APIView):
    """
    GET  — List support conversations (customers see own, admins see all).
    POST — Customer initiates a new support conversation.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description=(
            "List support conversations. "
            "Customers see only their own; admins see all open/in-progress."
        ),
        manual_parameters=[
            openapi.Parameter(
                "status", openapi.IN_QUERY,
                description="Filter by status (open, in_progress, resolved, closed)",
                type=openapi.TYPE_STRING, required=False,
            ),
        ],
        responses={200: "List of support conversations"},
    )
    def get(self, request):
        from .models import SupportConversation
        from .serializers import SupportConversationListSerializer

        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.is_staff:
            qs = SupportConversation.objects.all()
        else:
            qs = SupportConversation.objects.filter(customer=request.user)

        # Optional status filter
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        qs = qs.select_related("customer", "assigned_admin").order_by(
            "-updated_at"
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)

        serializer = SupportConversationListSerializer(
            page, many=True, context={"request": request}
        )

        return paginator.get_paginated_response(
            api_response(
                message="Support conversations retrieved.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Customer creates a new support conversation.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["subject", "message"],
            properties={
                "subject": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Brief topic of the issue",
                ),
                "message": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="Initial message content",
                ),
                "priority": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="low, medium, high, or urgent",
                ),
            },
        ),
        responses={201: "Conversation created"},
    )
    def post(self, request):
        from .models import SupportConversation, SupportMessage
        from .serializers import (
            SupportConversationCreateSerializer,
            SupportConversationSerializer,
        )

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SupportConversationCreateSerializer(data=data)
        if not serializer.is_valid():
            return Response(
                api_response(message=serializer.errors, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        vd = serializer.validated_data

        conversation = SupportConversation.objects.create(
            customer=request.user,
            subject=vd["subject"],
            priority=vd.get("priority", "medium"),
        )

        SupportMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            content=vd["message"],
        )

        # Notify admin dashboard via channel layer
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "support_admin_dashboard",
                {
                    "type": "new_conversation",
                    "conversation": {
                        "id": str(conversation.id),
                        "subject": conversation.subject,
                        "status": conversation.status,
                        "priority": conversation.priority,
                        "customer": {
                            "id": str(request.user.id),
                            "email": request.user.email,
                            "first_name": request.user.first_name,
                            "last_name": request.user.last_name,
                        },
                    },
                },
            )
        except Exception:
            pass  # Don't fail the API call if channel layer unavailable

        out = SupportConversationSerializer(
            conversation, context={"request": request}
        )

        return Response(
            api_response(
                message="Support conversation created.",
                status=True,
                data=out.data,
            ),
            status=status.HTTP_201_CREATED,
        )


class SupportConversationDetailView(APIView):
    """
    GET   — Retrieve conversation details.
    PATCH — Update status/priority/assigned admin (admin only for most fields).
    """

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Get support conversation details",
        responses={200: "Conversation detail"},
    )
    def get(self, request, conversation_id):
        from .models import SupportConversation
        from .serializers import SupportConversationSerializer

        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.is_staff:
            conversation = get_object_or_404(
                SupportConversation, id=conversation_id
            )
        else:
            conversation = get_object_or_404(
                SupportConversation,
                id=conversation_id,
                customer=request.user,
            )

        serializer = SupportConversationSerializer(
            conversation, context={"request": request}
        )
        return Response(
            api_response(
                message="Conversation retrieved.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Update conversation (admin: status, priority, assign)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "status": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="open, in_progress, resolved, closed",
                ),
                "priority": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="low, medium, high, urgent",
                ),
                "assigned_admin_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="UUID of admin to assign",
                ),
            },
        ),
        responses={200: "Conversation updated"},
    )
    def patch(self, request, conversation_id):
        from .models import SupportConversation
        from .serializers import SupportConversationSerializer
        from django.contrib.auth import get_user_model

        User = get_user_model()

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.is_staff:
            return Response(
                api_response(
                    message="Only admins can update conversations.",
                    status=False,
                ),
                status=status.HTTP_403_FORBIDDEN,
            )

        conversation = get_object_or_404(
            SupportConversation, id=conversation_id
        )

        new_status = data.get("status")
        if new_status:
            valid = ("open", "in_progress", "resolved", "closed")
            if new_status not in valid:
                return Response(
                    api_response(
                        message=f"Invalid status. Choose from {valid}.",
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            conversation.status = new_status
            if new_status == "resolved":
                conversation.resolved_at = timezone.now()

        new_priority = data.get("priority")
        if new_priority:
            valid = ("low", "medium", "high", "urgent")
            if new_priority not in valid:
                return Response(
                    api_response(
                        message=f"Invalid priority. Choose from {valid}.",
                        status=False,
                    ),
                    status=status.HTTP_400_BAD_REQUEST,
                )
            conversation.priority = new_priority

        admin_id = data.get("assigned_admin_id")
        if admin_id:
            try:
                admin = User.objects.get(id=admin_id, is_staff=True)
                conversation.assigned_admin = admin
            except User.DoesNotExist:
                return Response(
                    api_response(
                        message="Admin user not found.",
                        status=False,
                    ),
                    status=status.HTTP_404_NOT_FOUND,
                )

        conversation.save()

        serializer = SupportConversationSerializer(
            conversation, context={"request": request}
        )
        return Response(
            api_response(
                message="Conversation updated.",
                status=True,
                data=serializer.data,
            )
        )


class SupportMessageListView(APIView):
    """
    GET  — List messages in a support conversation (paginated).
    POST — Send a message (REST fallback when WS is unavailable).
    """

    permission_classes = [IsAuthenticated]
    pagination_class = CustomLimitOffsetPagination

    @swagger_auto_schema(
        operation_description="List messages in a support conversation",
        responses={200: "List of messages"},
    )
    def get(self, request, conversation_id):
        from .models import SupportConversation, SupportMessage
        from .serializers import SupportMessageSerializer

        status_, data = get_incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Access control
        if request.user.is_staff:
            conversation = get_object_or_404(
                SupportConversation, id=conversation_id
            )
        else:
            conversation = get_object_or_404(
                SupportConversation,
                id=conversation_id,
                customer=request.user,
            )

        messages = SupportMessage.objects.filter(
            conversation=conversation,
        ).select_related("sender")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(messages, request)

        serializer = SupportMessageSerializer(
            page, many=True, context={"request": request}
        )

        return paginator.get_paginated_response(
            api_response(
                message="Messages retrieved.",
                status=True,
                data=serializer.data,
            )
        )

    @swagger_auto_schema(
        operation_description="Send a message in a support conversation (REST)",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["content"],
            properties={
                "content": openapi.Schema(type=openapi.TYPE_STRING),
                "message_type": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="text, image, file, system",
                ),
            },
        ),
        responses={201: "Message sent"},
    )
    def post(self, request, conversation_id):
        from .models import SupportConversation, SupportMessage
        from .serializers import SupportMessageSerializer

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Access control
        if request.user.is_staff:
            conversation = get_object_or_404(
                SupportConversation, id=conversation_id
            )
        else:
            conversation = get_object_or_404(
                SupportConversation,
                id=conversation_id,
                customer=request.user,
            )

        content = data.get("content", "").strip()
        if not content:
            return Response(
                api_response(message="Content is required.", status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        message_type = data.get("message_type", "text")

        # Auto-assign admin on first reply
        if (
            request.user.is_staff
            and not conversation.assigned_admin
            and conversation.status == "open"
        ):
            conversation.assigned_admin = request.user
            conversation.status = "in_progress"

        conversation.save()  # touch updated_at

        msg = SupportMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
            message_type=message_type,
        )

        # Broadcast via channel layer (best-effort)
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync

            channel_layer = get_channel_layer()
            message_payload = {
                "id": str(msg.id),
                "content": msg.content,
                "message_type": msg.message_type,
                "file_url": None,
                "sender": {
                    "id": str(msg.sender.id),
                    "email": msg.sender.email,
                    "first_name": msg.sender.first_name,
                    "last_name": msg.sender.last_name,
                    "is_staff": msg.sender.is_staff,
                },
                "is_read": msg.is_read,
                "created_at": msg.created_at.isoformat(),
                "conversation_id": str(conversation.id),
            }

            async_to_sync(channel_layer.group_send)(
                f"support_chat_{conversation_id}",
                {"type": "chat_message", "message": message_payload},
            )
            async_to_sync(channel_layer.group_send)(
                "support_admin_dashboard",
                {
                    "type": "conversation_updated",
                    "conversation_id": str(conversation_id),
                    "message": message_payload,
                },
            )
        except Exception:
            pass

        # Trigger push notification
        try:
            from .tasks import send_support_push_notification
            send_support_push_notification.delay(
                conversation_id=str(conversation.id),
                sender_id=str(request.user.id),
                message_preview=content[:100],
            )
        except Exception:
            pass

        serializer = SupportMessageSerializer(
            msg, context={"request": request}
        )
        return Response(
            api_response(
                message="Message sent.",
                status=True,
                data=serializer.data,
            ),
            status=status.HTTP_201_CREATED,
        )


class SupportMarkReadView(APIView):
    """Mark all unread messages in a conversation as read (for current user)."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Mark all messages as read in a support conversation",
        responses={200: "Messages marked as read"},
    )
    def post(self, request, conversation_id):
        from .models import SupportConversation, SupportMessage

        status_, data = incoming_request_checks(request)
        if not status_:
            return Response(
                api_response(message=data, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.is_staff:
            conversation = get_object_or_404(
                SupportConversation, id=conversation_id
            )
        else:
            conversation = get_object_or_404(
                SupportConversation,
                id=conversation_id,
                customer=request.user,
            )

        updated = SupportMessage.objects.filter(
            conversation=conversation,
            is_read=False,
        ).exclude(sender=request.user).update(
            is_read=True,
            read_at=timezone.now(),
        )

        return Response(
            api_response(
                message=f"{updated} messages marked as read.",
                status=True,
                data={"updated_count": updated},
            )
        )


class SupportFileUploadView(APIView):
    """Upload a file attachment for a support message."""

    permission_classes = [IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    @swagger_auto_schema(
        operation_description="Upload a file for a support chat message",
        request_body=SupportFileUploadSerializer,
        responses={201: "File uploaded"},
    )
    def post(self, request):
        from django.core.files.storage import default_storage

        serializer = SupportFileUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                api_response(message=serializer.errors, status=False),
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = serializer.validated_data["file"]
        path = default_storage.save(
            f"support_attachments/{file_obj.name}", file_obj
        )
        url = request.build_absolute_uri(default_storage.url(path))

        return Response(
            api_response(
                message="File uploaded.",
                status=True,
                data={"file_url": url, "file_name": file_obj.name},
            ),
            status=status.HTTP_201_CREATED,
        )
