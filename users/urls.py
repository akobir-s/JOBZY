from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *
from django.urls import path, re_path
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
   openapi.Info(
      title="My API",
      default_version='v1',
      description="API for my project",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="akobirsafarzoda@gmail.com"),
      license=openapi.License(name="BSD License"),
   ),
     public=True,
   permission_classes=[permissions.AllowAny],
   authentication_classes=[],
)





router = DefaultRouter()
# router.register(r'profiles', MyProfessionalProfileViewSet, basename='profiles')
router.register(r'professionals', ProfessionalProfileViewSet)
router.register(r'categories', ServiceCategoryViewSet)
router.register(r'admin-logs', AdminLogViewSet)

router.register(r'services', ProfessionalServiceViewSet, basename='service')
router.register(r'slots', AvailabilitySlotViewSet, basename='slot')
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'messages', MessageViewSet, basename='message')
router.register(r'notifications', NotificationViewSet, basename='notification')



urlpatterns = [
    path('', include(router.urls)),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('search/professionals/', ProfessionalSearchView.as_view(), name='professional-search'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterUserView.as_view(), name='register'),
    path('login/', LoginUserView.as_view(), name= 'login'),
    path('logout/', LogoutUserView.as_view(), name = 'loguot'),
    path('my-profile/', MyProfessionalView.as_view(), name='my-profile'),
    path('public-services/', PublicServiceListView.as_view(), name='public-services'),
    path('user-profile/', UserProfileView.as_view(), name= 'user-profile'),
    path('services/<int:pk>/', ProfessionalServiceDetailView.as_view(), name='service-detail'),
    path('update-avatar/', UpdateAvatarView.as_view(), name='update-avatar'),
]
