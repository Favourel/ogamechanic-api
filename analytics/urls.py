from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    
    # Analytics Summary
    path('summary/', views.AnalyticsSummaryView.as_view(), name='summary'),
    
    # Reports
    path('reports/', views.AnalyticsReportView.as_view(), name='reports'),
    
    # Real-time Analytics
    path('realtime/', views.RealTimeAnalyticsView.as_view(), name='realtime'),
    
    # Analytics Cache
    path('cache/', views.AnalyticsCacheView.as_view(), name='cache'),
] 