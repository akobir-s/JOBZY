from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    AdminDashboardView,
    AdminLogViewSet,
    AvailabilitySlotViewSet,
    BookingViewSet,
    DashboardView,
    LoginUserView,
    LogoutUserView,
    MessageViewSet,
    MyProfessionalView,
    NotificationViewSet,
    PaymentViewSet,
    ProfessionalProfileViewSet,
    ProfessionalSearchDetailView,
    ProfessionalSearchView,
    ProfessionalServiceDetailView,
    ProfessionalServiceViewSet,
    PublicServiceDetailView,
    PublicServiceListView,
    RegisterUserView,
    ReviewViewSet,
    ServiceCategoryViewSet,
    UpdateAvatarView,
    UserProfileView,
)

schema_view = get_schema_view(
    openapi.Info(
        title='JOBZY API',
        default_version='v1',
        description=(
            'REST API for the JOBZY services marketplace.\n\n'
            'Authenticate with `POST /login/` or `POST /api/token/`, then click '
            '**Authorize** and enter `Bearer <access_token>`.'
        ),
        contact=openapi.Contact(email='akobirsafarzoda@gmail.com'),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

router = DefaultRouter()
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
    # API docs
    re_path(r'^swagger(?P<format>\.json|\.yaml)$',
            schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0),
            name='schema-swagger-ui'),
    re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    # Auth
    path('register/', RegisterUserView.as_view(), name='register'),
    path('login/', LoginUserView.as_view(), name='login'),
    path('logout/', LogoutUserView.as_view(), name='logout'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Current user
    path('user-profile/', UserProfileView.as_view(), name='user-profile'),
    path('update-avatar/', UpdateAvatarView.as_view(), name='update-avatar'),
    path('my-profile/', MyProfessionalView.as_view(), name='my-professional-profile'),
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    # Public search & catalogue
    path('search/professionals/', ProfessionalSearchView.as_view(), name='professional-search'),
    path('search/professionals/<int:id>/', ProfessionalSearchDetailView.as_view(),
         name='professional-search-detail'),
    path('public-services/', PublicServiceListView.as_view(), name='public-service-list'),
    path('public-services/<int:id>/', PublicServiceDetailView.as_view(),
         name='public-service-detail'),
    # Kept on a distinct prefix: `services/<pk>/` is owned by the router above.
    path('service-info/<int:pk>/', ProfessionalServiceDetailView.as_view(),
         name='service-info-detail'),

    # Admin
    path('admin-dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),

    # Router-managed resources (registered last so explicit paths above win)
    path('', include(router.urls)),
]
