from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    AnalyticsDashboard, AnalyticsWidget, AnalyticsCache,
    UserAnalytics, AnalyticsReport
)

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer for nested representations"""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']
        ref_name = "AdminPanelUserSerializer"


class AnalyticsDashboardSerializer(serializers.ModelSerializer):
    widgets_count = serializers.SerializerMethodField()

    class Meta:
        model = AnalyticsDashboard
        fields = [
            'id', 'role', 'title', 'description', 'is_active',
            'created_at', 'updated_at', 'widgets_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_widgets_count(self, obj):
        return obj.widgets.filter(is_active=True).count()


class AnalyticsWidgetSerializer(serializers.ModelSerializer):
    dashboard = AnalyticsDashboardSerializer(read_only=True)

    class Meta:
        model = AnalyticsWidget
        fields = [
            'id', 'dashboard', 'title', 'widget_type', 'chart_type',
            'data_source', 'position', 'is_active', 'config',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AnalyticsWidgetListSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsWidget
        fields = [
            'id', 'title', 'widget_type', 'chart_type',
            'data_source', 'position', 'is_active'
        ]


class AnalyticsCacheSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsCache
        fields = [
            'id', 'key', 'data', 'expires_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserAnalyticsSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = UserAnalytics
        fields = [
            'id', 'user', 'data_type', 'data', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class AnalyticsReportSerializer(serializers.ModelSerializer):
    generated_by = UserSerializer(read_only=True)

    class Meta:
        model = AnalyticsReport
        fields = [
            'id', 'title', 'report_type', 'generated_by', 'date_from',
            'date_to', 'data', 'file_path', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AnalyticsReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticsReport
        fields = [
            'title', 'report_type', 'date_from', 'date_to'
        ]


class DashboardDataSerializer(serializers.Serializer):
    """Serializer for dashboard data responses"""
    dashboard = AnalyticsDashboardSerializer()
    widgets = AnalyticsWidgetListSerializer(many=True)
    data = serializers.JSONField()


class AnalyticsSummarySerializer(serializers.Serializer):
    """Serializer for analytics summary data"""
    total_users = serializers.IntegerField()
    total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_rides = serializers.IntegerField()
    total_couriers = serializers.IntegerField()
    total_rentals = serializers.IntegerField()
    total_mechanics = serializers.IntegerField()
    revenue_by_month = serializers.JSONField()
    top_merchants = serializers.ListField(child=serializers.CharField())
    top_drivers = serializers.ListField(child=serializers.CharField())
