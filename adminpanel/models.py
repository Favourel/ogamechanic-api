import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class AnalyticsDashboard(models.Model):
    """
    Model to store dashboard configurations for different user roles
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('merchant', 'Merchant'),
        ('driver', 'Driver'),
        ('mechanic', 'Mechanic'),
        ('customer', 'Customer'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['role', 'title']
        unique_together = ['role', 'title']
        db_table = 'analytics_analyticsdashboard'

    def __str__(self):
        return f"{self.get_role_display()} - {self.title}"


class AnalyticsWidget(models.Model):
    """
    Model to store widget configurations for dashboards
    """
    WIDGET_TYPES = [
        ('metric', 'Metric Card'),
        ('chart', 'Chart'),
        ('table', 'Data Table'),
        ('list', 'List'),
    ]

    CHART_TYPES = [
        ('line', 'Line Chart'),
        ('bar', 'Bar Chart'),
        ('pie', 'Pie Chart'),
        ('doughnut', 'Doughnut Chart'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dashboard = models.ForeignKey(
        AnalyticsDashboard,
        on_delete=models.CASCADE,
        related_name='widgets'
    )
    title = models.CharField(max_length=200)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    chart_type = models.CharField(
        max_length=20,
        choices=CHART_TYPES,
        blank=True,
        null=True
    )
    data_source = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['dashboard', 'position']
        unique_together = ['dashboard', 'title']
        db_table = 'analytics_analyticswidget'

    def __str__(self):
        return f"{self.dashboard.title} - {self.title}"


class AnalyticsCache(models.Model):
    """
    Model to cache analytics data for performance
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.CharField(max_length=200, unique=True)
    data = models.JSONField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        db_table = 'analytics_analyticscache'
        indexes = [
            models.Index(fields=['key']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"Cache: {self.key}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class UserAnalytics(models.Model):
    """
    Model to store user-specific analytics data
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='analytics'
    )
    data_type = models.CharField(max_length=50)
    data = models.JSONField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        db_table = 'analytics_useranalytics'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['data_type']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.data_type}"


class AnalyticsReport(models.Model):
    """
    Model to store generated analytics reports
    """
    REPORT_TYPES = [
        ('sales', 'Sales Report'),
        ('rides', 'Rides Report'),
        ('couriers', 'Couriers Report'),
        ('mechanics', 'Mechanics Report'),
        ('rentals', 'Rentals Report'),
        ('users', 'Users Report'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    generated_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='generated_reports'
    )
    date_from = models.DateField()
    date_to = models.DateField()
    data = models.JSONField()
    file_path = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'analytics_analyticsreport'
        indexes = [
            models.Index(fields=['report_type']),
            models.Index(fields=['generated_by']),
            models.Index(fields=['date_from', 'date_to']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_report_type_display()})"
