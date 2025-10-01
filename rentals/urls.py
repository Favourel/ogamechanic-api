from django.urls import path
from . import views

app_name = 'rentals'

urlpatterns = [
    # Rental Bookings
    path('bookings/', views.RentalBookingListView.as_view(), name='rental-booking-list'),
    path('bookings/<uuid:booking_id>/', views.RentalBookingDetailView.as_view(), name='rental-booking-detail'),
    
    # Available Rentals
    path('available/', views.AvailableRentalsView.as_view(), name='available-rentals'),
    
    # Rental Reviews
    path('bookings/<uuid:booking_id>/reviews/', views.RentalReviewListView.as_view(), name='rental-reviews'),
    
    # Rental Periods
    path('products/<uuid:product_id>/periods/', views.RentalPeriodListView.as_view(), name='rental-periods'),
] 