from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (TokenObtainPairView, TokenRefreshView, TokenBlacklistView)

router = DefaultRouter()
router.register('schedules', views.ScheduleViewSet, basename='schedule')

urlpatterns = [
    path('test/', views.test, name='test_api'),
    path('signup/', views.sign_up, name='signup_api'),
    path('login/', TokenObtainPairView.as_view(), name='login_api'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh_api'),
    path('logout/', TokenBlacklistView.as_view(), name='logout_api'),
    path('schedules/<int:schedule_pk>/shifts/',
         views.ShiftViewSet.as_view({'get': 'list', 'post': 'create'}), name='shift-list'),
    path('schedules/<int:schedule_pk>/shifts/<int:pk>/', views.ShiftViewSet.as_view(
        {'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}),
        name='shift-detail'),
] + router.urls
