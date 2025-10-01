from django.contrib import admin
from . import models


# Custom admin for key models
@admin.register(models.RepairRequest)
class RepairRequestAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'customer', 'mechanic', 'service_type', 'vehicle_make',
        'vehicle_model', 'status', 'priority', 'requested_at'
    ]
    list_filter = [
        'status', 'priority', 'service_type', 'preferred_time_slot',
        'requested_at', 'accepted_at', 'completed_at'
    ]
    search_fields = [
        'customer__email', 'mechanic__email', 'service_type',
        'vehicle_make', 'vehicle_model', 'problem_description'
    ]
    readonly_fields = [
        'id', 'requested_at', 'accepted_at', 'started_at',
        'completed_at', 'cancelled_at'
    ]
    date_hierarchy = 'requested_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'customer', 'mechanic', 'status', 'priority')
        }),
        ('Vehicle Details', {
            'fields': (
                'service_type', 'vehicle_make', 'vehicle_model',
                'vehicle_year', 'vehicle_registration'
            )
        }),
        ('Problem Description', {
            'fields': ('problem_description', 'symptoms', 'estimated_cost')
        }),
        ('Location & Scheduling', {
            'fields': (
                'service_address', 'service_latitude', 'service_longitude',
                'preferred_date', 'preferred_time_slot'
            )
        }),
        ('Timestamps', {
            'fields': (
                'requested_at', 'accepted_at', 'started_at',
                'completed_at', 'cancelled_at'
            ),
            'classes': ('collapse',)
        }),
        ('Additional Information', {
            'fields': ('notes', 'cancellation_reason', 'actual_cost'),
            'classes': ('collapse',)
        }),
    )


@admin.register(models.TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'title', 'instructor', 'session_type', 'start_date',
        'end_date', 'status', 'cost', 'is_free', 'current_participants_count'
    ]
    list_filter = [
        'status', 'session_type', 'is_free', 'certificate_offered',
        'start_date', 'end_date', 'created_at'
    ]
    search_fields = [
        'title', 'description', 'instructor__email', 'venue',
        'venue_address'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'current_participants_count',
        'is_registration_open', 'is_full', 'available_spots'
    ]
    date_hierarchy = 'start_date'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'title', 'description', 'session_type', 'status')
        }),
        ('Instructor & Capacity', {
            'fields': ('instructor', 'max_participants')
        }),
        ('Scheduling', {
            'fields': ('start_date', 'end_date', 'start_time', 'end_time')
        }),
        ('Location', {
            'fields': ('venue', 'venue_address', 'venue_latitude', 'venue_longitude')  # noqa
        }),
        ('Cost & Registration', {
            'fields': ('cost', 'is_free', 'registration_deadline')
        }),
        ('Additional Information', {
            'fields': ('materials_provided', 'prerequisites', 'certificate_offered'),  # noqa
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(models.TrainingSessionParticipant)
class TrainingSessionParticipantAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'participant', 'session', 'status', 'payment_status',
        'registered_at', 'certificate_issued'
    ]
    list_filter = [
        'status', 'payment_status', 'certificate_issued',
        'registered_at', 'attended_at', 'completed_at'
    ]
    search_fields = [
        'participant__email', 'session__title', 'session__instructor__email'
    ]
    readonly_fields = [
        'id', 'registered_at', 'attended_at', 'completed_at',
        'certificate_issued_at'
    ]
    date_hierarchy = 'registered_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'participant', 'session', 'status')
        }),
        ('Payment', {
            'fields': ('payment_status', 'payment_amount')
        }),
        ('Attendance', {
            'fields': ('registered_at', 'attended_at', 'completed_at')
        }),
        ('Certificate', {
            'fields': ('certificate_issued', 'certificate_issued_at')
        }),
        ('Feedback', {
            'fields': ('rating', 'feedback'),
            'classes': ('collapse',)
        }),
    )


# Register all other models from mechanics app that are not already registered above  # noqa
already_registered = {
    models.RepairRequest,
    models.TrainingSession,
    models.TrainingSessionParticipant,
}

for model in vars(models).values():
    try:
        if (
            isinstance(model, type)
            and issubclass(model, models.models.Model)
            and model not in already_registered
        ):
            admin.site.register(model)
    except Exception:
        continue
