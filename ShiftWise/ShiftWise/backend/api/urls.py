from django.urls import path
from . import compat_views, role_views, shift_views, views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (TokenObtainPairView, TokenRefreshView, TokenBlacklistView)

router = DefaultRouter()
router.register('schedules', views.ScheduleViewSet, basename='schedule')
router.register('compatibility', views.CompatibilityScoreViewSet, basename='compatibility')
router.register('compatibility-groups', compat_views.CompatibilityGroupViewSet, basename='compatibility-group')
router.register('availability', views.AvailabilitySlotViewSet, basename='availability')
router.register('time-off', views.TimeOffRequestViewSet, basename='time-off')
router.register('projects', views.ProjectViewSet, basename='project')
router.register('milestones', views.MilestoneViewSet, basename='milestone')
router.register('employees', role_views.EmployeeViewSet, basename='employee')
router.register('departments', role_views.DepartmentViewSet, basename='department')
router.register('join-codes', role_views.JoinCodeViewSet, basename='join-code')
router.register('transfer-requests', role_views.TransferRequestViewSet, basename='transfer-request')
router.register('notifications', role_views.NotificationViewSet, basename='notification')
router.register('shifts', shift_views.ShiftViewSet, basename='shift')
router.register('shift-templates', shift_views.ShiftTemplateViewSet, basename='shift-template')
router.register('shift-requests', shift_views.ShiftRequestViewSet, basename='shift-request')

urlpatterns = [
    path('test/', views.test, name='test_api'),
    path('signup/', role_views.sign_up, name='signup_api'),
    path('join-code-check/', role_views.join_code_check, name='join_code_check'),
    path('me/', role_views.me, name='me'),
    path('company/', shift_views.company, name='company'),
    path('coworkers/', shift_views.coworkers, name='coworkers'),
    path('me/leave/', role_views.me_leave, name='me_leave'),
    path('me/join/', role_views.me_join, name='me_join'),
    path('signup-check/', views.signup_check, name='signup_check'),
    path('login/', TokenObtainPairView.as_view(), name='login_api'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh_api'),
    path('logout/', TokenBlacklistView.as_view(), name='logout_api'),
] + router.urls
