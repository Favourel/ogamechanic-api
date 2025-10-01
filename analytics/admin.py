from django.contrib import admin
from .models import (
    AnalyticsDashboard, AnalyticsWidget, AnalyticsCache,
    UserAnalytics, AnalyticsReport
)


@admin.register(AnalyticsDashboard)
class AnalyticsDashboardAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'role', 'title', 'is_active', 'created_at'
    ]
    list_filter = [
        'role', 'is_active', 'created_at'
    ]
    search_fields = [
        'title', 'description'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'role', 'title', 'description', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AnalyticsWidget)
class AnalyticsWidgetAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'dashboard', 'title', 'widget_type', 'chart_type',
        'position', 'is_active'
    ]
    list_filter = [
        'dashboard__role', 'widget_type', 'chart_type', 'is_active',
        'created_at'
    ]
    search_fields = [
        'title', 'data_source', 'dashboard__title'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'dashboard', 'title', 'widget_type', 'chart_type')
        }),
        ('Configuration', {
            'fields': ('data_source', 'position', 'is_active', 'config')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AnalyticsCache)
class AnalyticsCacheAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'key', 'expires_at', 'is_expired', 'created_at'
    ]
    list_filter = [
        'expires_at', 'created_at'
    ]
    search_fields = [
        'key'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'is_expired'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'key', 'data', 'expires_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserAnalytics)
class UserAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'data_type', 'timestamp'
    ]
    list_filter = [
        'data_type', 'timestamp'
    ]
    search_fields = [
        'user__email', 'data_type'
    ]
    readonly_fields = [
        'id', 'timestamp'
    ]
    date_hierarchy = 'timestamp'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'user', 'data_type', 'data')
        }),
        ('Timestamps', {
            'fields': ('timestamp',),
            'classes': ('collapse',)
        }),
    )


@admin.register(AnalyticsReport)
class AnalyticsReportAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'title', 'report_type', 'generated_by', 'date_from',
        'date_to', 'created_at'
    ]
    list_filter = [
        'report_type', 'date_from', 'date_to', 'created_at'
    ]
    search_fields = [
        'title', 'generated_by__email'
    ]
    readonly_fields = [
        'id', 'created_at'
    ]
    date_hierarchy = 'created_at'
    list_per_page = 25

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'title', 'report_type', 'generated_by')
        }),
        ('Date Range', {
            'fields': ('date_from', 'date_to')
        }),
        ('Report Data', {
            'fields': ('data', 'file_path'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
