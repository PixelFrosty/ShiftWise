from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (TokenObtainPairView, TokenRefreshView, TokenBlacklistView)

router = DefaultRouter()
router.register('schedules', views.ScheduleViewSet, basename='schedule')
router.register('compatibility', views.CompatibilityScoreViewSet, basename='compatibility')
router.register('availability', views.AvailabilitySlotViewSet, basename='availability')
router.register('time-off', views.TimeOffRequestViewSet, basename='time-off')
router.register('projects', views.ProjectViewSet, basename='project')

urlpatterns = [
    path('test/', views.test, name='test_api'),
    path('signup/', views.sign_up, name='signup_api'),
    path('signup-check/', views.signup_check, name='signup_check'),
    path('login/', TokenObtainPairView.as_view(), name='login_api'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh_api'),
    path('logout/', TokenBlacklistView.as_view(), name='logout_api'),
] + router.urls
